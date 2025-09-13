import sys
import types


class FakePg:
    def __init__(self):
        self.ready_articles = [
            {
                'article_id': 'A1',
                'url': 'https://example.com/x',
                'source': 'example.com',
                'title_norm': 'Title',
                'clean_text': 'Para one with enough words to form chunks. Another sentence.\n\nSecond paragraph continues here.',
                'language': 'en',
                'category': None,
                'tags_norm': [],
                'published_at': None,
                'processing_version': 1,
            }
        ]
        self.completed = set()
        self._chunks = []
        self._next_id = 1

    # Stage 6
    def get_articles_ready_for_chunking(self, limit=50):
        return self.ready_articles[:limit]

    def upsert_article_chunks(self, article_id, processing_version, chunks):
        for c in chunks:
            entry = {
                'id': self._next_id,
                'article_id': article_id,
                'processing_version': processing_version,
                'chunk_index': c['chunk_index'],
                'text': c['text'],
                'language': c.get('language', 'en'),
                'fts_vector': None,
                'embedding': None,
            }
            self._chunks.append(entry)
            self._next_id += 1
        return {"inserted": len(chunks), "updated": 0}

    def mark_chunking_completed(self, article_id, processing_version):
        self.completed.add((article_id, processing_version))

    # Stage 7
    def get_chunks_for_indexing(self, limit=128):
        return self._chunks[:limit]

    def update_chunks_fts(self, ids):
        count = 0
        for ch in self._chunks:
            if ch['id'] in ids and ch['fts_vector'] is None:
                ch['fts_vector'] = 'ts'
                count += 1
        return count

    def update_chunk_embedding(self, chunk_id, embedding):
        for ch in self._chunks:
            if ch['id'] == chunk_id:
                ch['embedding'] = embedding
                return True
        return False

    def close(self):
        return None


def test_chunk_index_e2e(monkeypatch):
    import main as app

    # Env and argv
    monkeypatch.setenv('PG_DSN', 'postgresql://user:pass@localhost:5432/db')

    # Monkeypatch PgClient to use single fake instance
    fake = FakePg()
    import pg_client_new
    # Replace constructors to avoid real pool init
    monkeypatch.setattr(pg_client_new, 'PgClient', lambda: fake)
    monkeypatch.setattr(app, 'PgClient', lambda: fake)

    # Avoid importing heavy settings/LLM in chunk refine
    import stage6_hybrid_chunking.src.stage6.interfaces as interfaces
    monkeypatch.setattr(interfaces, 'refine_boundaries', lambda chunks, meta: chunks)

    # Run chunk command
    monkeypatch.setenv('STAGE6_APPLY_EDITS', 'false')
    monkeypatch.setenv('CHUNK_OVERLAP_TOKENS', '0')
    monkeypatch.setitem(sys.modules, 'argparse', __import__('argparse'))
    sys.argv = ['prog', 'chunk', '--limit', '1']
    rc = app.main()
    assert rc == 0 or rc is None
    # Chunks created
    assert len(fake._chunks) >= 1
    assert ('A1', 1) in fake.completed

    # Prepare embedding settings stub and fake Gemini
    monkeypatch.setenv('EMBEDDING_MODEL', 'gemini-embedding-001')
    monkeypatch.setenv('GEMINI_API_KEY', 'key')

    class FakeGemini:
        def __init__(self, settings):
            pass
        async def embed_texts(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]
        async def close(self):
            return None

    import stage6_hybrid_chunking.src.llm.gemini_client as llm
    monkeypatch.setattr(llm, 'GeminiClient', FakeGemini)

    # Monkeypatch get_settings to avoid Pydantic
    # Inject a fake settings module before import to avoid pydantic dependency in tests
    settings_stub = types.SimpleNamespace(
        gemini=types.SimpleNamespace(embedding_model='gemini-embedding-001'),
        rate_limit=types.SimpleNamespace(embedding_daily_cost_limit_usd=100.0, cost_per_token_input=0.0)
    )
    fake_mod = types.ModuleType('stage6_hybrid_chunking.src.config.settings')
    fake_mod.get_settings = lambda: settings_stub
    sys.modules['stage6_hybrid_chunking.src.config.settings'] = fake_mod

    # Run index command
    sys.argv = ['prog', 'index', '--limit', '10']
    rc = app.main()
    assert rc == 0 or rc is None
    # FTS updated and embeddings set for some
    assert any(ch['fts_vector'] for ch in fake._chunks)
    assert any(isinstance(ch['embedding'], list) and ch['embedding'] for ch in fake._chunks)
