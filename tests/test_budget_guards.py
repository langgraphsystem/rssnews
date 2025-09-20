import sys
import types


def test_llm_daily_budget_guard(monkeypatch):
    # Settings stub: allow LLM routing but cap daily cost very low
    settings_stub = types.SimpleNamespace(
        rate_limit=types.SimpleNamespace(
            max_llm_percentage_per_batch=1.0, 
            daily_cost_limit_usd=0.01,
            max_llm_calls_per_batch=100,
            cost_per_token_input=0.00001,
            cost_per_token_output=0.00003
        ),
        features=types.SimpleNamespace(
            llm_chunk_refine_enabled=True, 
            apply_chunk_edits=False,
            llm_routing_enabled=True
        ),
        chunking=types.SimpleNamespace(target_words=400, max_offset=120),
        gemini=types.SimpleNamespace(api_key=types.SimpleNamespace(get_secret_value=lambda: 'test_key')),
    )
    # Thresholds for router
    settings_stub.quality_router_thresholds = {
        "too_short_ratio": 0.5,
        "too_long_ratio": 1.5,
        "sentence_incomplete": 0.8,
        "boilerplate_score": 0.3,
        "quality_score_min": 0.4,
        "language_confidence_min": 0.7,
    }
    settings_stub.llm_blacklist_domains = set()
    settings_stub.llm_whitelist_domains = set()
    # Add domain method
    settings_stub.should_use_llm_for_domain = lambda domain: True
    fake_mod = types.ModuleType('stage6_hybrid_chunking.src.config.settings')
    fake_mod.get_settings = lambda: settings_stub
    sys.modules['stage6_hybrid_chunking.src.config.settings'] = fake_mod

    # Mock Gemini with per-call cost 0.02 so first consumes budget
    from tests.fixtures.mock_llm import MockGeminiClient
    import stage6_hybrid_chunking.src.llm.gemini_client as llm
    monkeypatch.setattr(llm, 'GeminiClient', MockGeminiClient)

    # Build 3 chunks
    chunks = []
    for i in range(3):
        chunks.append({
            'chunk_index': i,
            'text': ('short text' if i == 0 else 'long ' * 200),
            'char_start': i * 10,
            'char_end': i * 10 + (20 if i == 0 else 800),
            'word_count_chunk': (2 if i == 0 else 200),
            'word_count': (2 if i == 0 else 200),  # Add word_count field
            'semantic_type': 'body',
        })
    import stage6_hybrid_chunking.src.stage6.interfaces as st6
    out = st6.refine_boundaries(chunks, {'title_norm': 't', 'source_domain': 'example.com', 'language': 'en', 'published_at': ''})
    # Expect only first refined (budget used), next ones noop with budget_exceeded
    assert out[0].get('llm_action') in ('noop', 'merge_with_prev', 'merge_with_next', 'split', 'drop')
    assert out[1]['llm_reason'] in ('budget_exceeded', 'not_routed_or_quota')
    assert out[2]['llm_reason'] in ('budget_exceeded', 'not_routed_or_quota')


def test_embeddings_budget_guard(monkeypatch):
    import main as app
    from tests.fixtures.mock_pg import FakePgClient

    # Patch PgClient
    fake = FakePgClient()
    import pg_client_new
    monkeypatch.setattr(pg_client_new, 'PgClient', lambda: fake)
    monkeypatch.setattr(app, 'PgClient', lambda: fake)
    monkeypatch.setenv('PG_DSN', 'postgresql://user:pass@localhost:5432/db')

    # Insert chunks to index
    fake._chunks = [
        {'id': i+1, 'article_id': 'X', 'processing_version': 1, 'chunk_index': i, 'text': 'text' * (50+i), 'language': 'en', 'fts_vector': None, 'embedding': None}
        for i in range(5)
    ]

    # Patch settings with very low daily cap
    settings_stub = types.SimpleNamespace(
        gemini=types.SimpleNamespace(embedding_model='gemini-embedding-001'),
        rate_limit=types.SimpleNamespace(embedding_daily_cost_limit_usd=0.01, cost_per_token_input=1.0)
    )
    fake_mod = types.ModuleType('stage6_hybrid_chunking.src.config.settings')
    fake_mod.get_settings = lambda: settings_stub
    sys.modules['stage6_hybrid_chunking.src.config.settings'] = fake_mod

    # Mock Gemini for embeddings
    from tests.fixtures.mock_llm import MockGeminiClient
    import stage6_hybrid_chunking.src.llm.gemini_client as llm
    monkeypatch.setattr(llm, 'GeminiClient', MockGeminiClient)

    # Run index
    sys.argv = ['prog', 'index', '--limit', '10']
    rc = app.main()
    assert rc == 0 or rc is None
    # Expect not all chunks got embeddings due to budget cap
    embedded = sum(1 for ch in fake._chunks if ch['embedding'])
    assert embedded < len(fake._chunks)

