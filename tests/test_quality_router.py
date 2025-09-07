import types


def make_settings(**overrides):
    # Minimal settings stub for QualityRouter
    s = types.SimpleNamespace()
    s.llm_blacklist_domains = set()
    s.llm_whitelist_domains = set()
    s.chunking = types.SimpleNamespace(target_words=400)
    # Domain decision stub
    def should_use_llm_for_domain(domain: str):
        return None
    s.should_use_llm_for_domain = should_use_llm_for_domain
    s.quality_router_thresholds = {
        "too_short_ratio": 0.5,
        "too_long_ratio": 1.5,
        "sentence_incomplete": 0.8,
        "boilerplate_score": 0.3,
        "quality_score_min": 0.4,
        "language_confidence_min": 0.7,
    }
    rl = types.SimpleNamespace(
        max_llm_calls_per_min=60,
        max_llm_calls_per_batch=10,
        max_llm_percentage_per_batch=0.3,
        daily_cost_limit_usd=10.0,
        cost_per_token_input=0.000125,
        cost_per_token_output=0.000375,
    )
    s.rate_limit = rl
    ff = types.SimpleNamespace(llm_chunk_refine_enabled=True, llm_routing_enabled=True)
    s.features = ff
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_router_short_and_long_chunks_route_llm():
    from stage6_hybrid_chunking.src.chunking.quality_router import QualityRouter
    from stage6_hybrid_chunking.src.chunking.base_chunker import RawChunk, SemanticType

    settings = make_settings()
    # Allow at least one chunk by share cap on a 2-chunk batch
    settings.rate_limit.max_llm_percentage_per_batch = 0.6
    r = QualityRouter(settings)

    short = RawChunk(index=0, text="a b c", text_clean="a b c", word_count=3, char_count=5,
                     char_start=0, char_end=5, semantic_type=SemanticType.BODY,
                     importance_score=0.5, strategy=None, boundaries=[])
    long_text = "word " * 1200
    long = RawChunk(index=1, text=long_text, text_clean=long_text, word_count=1200, char_count=len(long_text),
                    char_start=5, char_end=5+len(long_text), semantic_type=SemanticType.BODY,
                    importance_score=0.5, strategy=None, boundaries=[])

    routed = r.route_chunks([short, long], {"url": "https://example.com"}, batch_context={})
    llm_flags = [d.should_use_llm for _, d in routed]
    assert any(llm_flags), "At least one chunk should be routed to LLM"


def test_router_respects_llm_max_share():
    from stage6_hybrid_chunking.src.chunking.quality_router import QualityRouter
    from stage6_hybrid_chunking.src.chunking.base_chunker import RawChunk, SemanticType

    settings = make_settings()
    settings.rate_limit.max_llm_percentage_per_batch = 0.2  # 20%
    r = QualityRouter(settings)

    chunks = []
    for i in range(10):
        t = "word " * (50 if i % 2 == 0 else 5)  # mix sizes
        chunks.append(RawChunk(index=i, text=t, text_clean=t, word_count=len(t.split()), char_count=len(t),
                               char_start=i*10, char_end=i*10+len(t), semantic_type=SemanticType.BODY,
                               importance_score=0.5, strategy=None, boundaries=[]))
    routed = r.route_chunks(chunks, {"url": "https://example.com"}, batch_context={})
    # Enforce cap post-hoc
    allowed = int(len(chunks) * settings.rate_limit.max_llm_percentage_per_batch)
    actual = sum(1 for _, d in routed if d.should_use_llm)
    assert actual <= allowed
