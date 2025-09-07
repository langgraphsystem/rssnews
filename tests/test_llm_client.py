import types
import asyncio


def make_settings():
    s = types.SimpleNamespace()
    g = types.SimpleNamespace(
        api_key=types.SimpleNamespace(get_secret_value=lambda: "test_key"),
        model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com",
        timeout_seconds=1,
        max_retries=2,
        retry_delay_base=0.01,
        retry_delay_max=0.02,
        temperature=0.1,
        top_p=0.9,
        max_output_tokens=64,
        circuit_breaker_threshold=5,
        circuit_breaker_timeout=1,
    )
    rl = types.SimpleNamespace(
        max_llm_calls_per_min=60,
        cost_per_token_input=0.000125,
        cost_per_token_output=0.000375,
    )
    s.chunking = types.SimpleNamespace(target_words=400, max_offset=120)
    s.gemini = g
    s.rate_limit = rl
    return s


def test_llm_client_refine_success(monkeypatch):
    from stage6_hybrid_chunking.src.llm.gemini_client import GeminiClient

    settings = make_settings()
    client = GeminiClient(settings)

    async def fake_call(req):
        return ({
            "action": "keep",
            "offset_adjust": 0,
            "semantic_type": "body",
            "confidence": 0.8,
            "reason": "ok"
        }, 100)

    monkeypatch.setattr(client, "_make_api_call", fake_call)

    async def run():
        res = await client.refine_chunk(
            "text",
            {"chunk_index": 0, "word_count": 1, "char_start": 0, "char_end": 4, "semantic_type": "body"},
            {"title": "t", "source_domain": "example.com", "language": "en", "published_at": ""},
            context=None,
        )
        await client.close()
        return res

    res = asyncio.get_event_loop().run_until_complete(run())
    assert res is not None
    assert res.action in ("keep", "merge_prev", "merge_next", "drop")


def test_llm_client_retry_and_fallback(monkeypatch):
    from stage6_hybrid_chunking.src.llm.gemini_client import GeminiClient, APIErrorType

    settings = make_settings()
    settings.gemini.max_retries = 1
    client = GeminiClient(settings)

    attempts = {"n": 0}

    async def failing_call(req):
        attempts["n"] += 1
        raise Exception("Rate limit exceeded: 429")

    monkeypatch.setattr(client, "_make_api_call", failing_call)

    async def run():
        res = await client.refine_chunk(
            "text",
            {"chunk_index": 0, "word_count": 1, "char_start": 0, "char_end": 4, "semantic_type": "body"},
            {"title": "t", "source_domain": "example.com", "language": "en", "published_at": ""},
            context=None,
        )
        await client.close()
        return res

    res = asyncio.get_event_loop().run_until_complete(run())
    # After retries, it should fallback to None (graceful)
    assert res is None
    assert attempts["n"] == settings.gemini.max_retries + 1
