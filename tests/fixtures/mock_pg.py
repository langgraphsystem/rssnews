import types


class FakePgClient:
    def __init__(self):
        self._articles = []
        self._chunks = []
        self._completed = set()
        self._next_id = 1

    # Articles API
    def insert_article(self, article):
        rec = {
            'article_id': article['article_id'],
            'url': article['url'],
            'source': article['source_domain'],
            'title_norm': article['title'],
            'clean_text': article['clean_text'],
            'language': article['language'],
            'category': None,
            'tags_norm': [],
            'published_at': article['published_at'],
            'processing_version': 1,
            'ready_for_chunking': True,
            'chunking_completed': False,
        }
        self._articles.append(rec)

    def get_articles_ready_for_chunking(self, limit=50):
        return [
            {k: r.get(k) for k in (
                'article_id','url','source','title_norm','clean_text','language','category','tags_norm','published_at','processing_version'
            )}
            for r in self._articles if r['ready_for_chunking'] and not r['chunking_completed']
        ][:limit]

    def upsert_article_chunks(self, article_id, processing_version, chunks):
        for c in chunks:
            self._chunks.append({
                'id': self._next_id,
                'article_id': article_id,
                'processing_version': processing_version,
                'chunk_index': c['chunk_index'],
                'text': c['text'],
                'language': c.get('language', 'en'),
                'fts_vector': None,
                'embedding': None,
            })
            self._next_id += 1
        return {"inserted": len(chunks), "updated": 0}

    def mark_chunking_completed(self, article_id, processing_version):
        for r in self._articles:
            if r['article_id'] == article_id:
                r['chunking_completed'] = True
                r['ready_for_chunking'] = False
        self._completed.add((article_id, processing_version))

    # Indexing API
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

