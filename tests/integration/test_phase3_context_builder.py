"""
Integration tests for Phase3ContextBuilder
"""
import asyncio
import pytest
from core.context.phase3_context_builder import get_phase3_context_builder


@pytest.mark.asyncio
async def test_ask_command_basic():
    """Test /ask command with basic args"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/ask --depth=deep",
        "args": "window=24h lang=en",
        "user_lang": "en",
        "env": {
            "defaults": {
                "window": "24h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    # Should not be error
    assert "error" not in context

    # Check structure
    assert context["command"] == "/ask --depth=deep"
    assert context["params"]["window"] == "24h"
    assert context["params"]["lang"] == "en"
    assert context["params"]["k_final"] >= 5
    assert context["params"]["k_final"] <= 10

    # Check retrieval
    assert "docs" in context["retrieval"]
    assert context["retrieval"]["window"] == "24h"

    # Check models
    assert context["models"]["primary"] == "gpt-5"
    assert "claude-4.5" in context["models"]["fallback"]

    # Check limits
    assert context["limits"]["max_tokens"] >= 2048
    assert context["limits"]["budget_cents"] >= 25
    assert context["limits"]["timeout_s"] >= 8

    print(f"✅ /ask context built: {context['telemetry']['correlation_id']}")


@pytest.mark.asyncio
async def test_events_command():
    """Test /events link command"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/events link",
        "args": "topic=AI window=1w lang=ru",
        "user_lang": "ru",
        "env": {
            "defaults": {
                "window": "24h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    assert "error" not in context
    assert context["command"] == "/events link"
    assert context["params"]["topic"] == "AI"
    assert context["params"]["window"] == "1w"
    assert context["params"]["lang"] == "ru"

    # Check models for /events
    assert context["models"]["primary"] == "gpt-5"

    print(f"✅ /events context built: {context['telemetry']['correlation_id']}")


@pytest.mark.asyncio
async def test_graph_command():
    """Test /graph query command"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/graph query",
        "args": 'query="machine learning trends" window=3d',
        "user_lang": "en",
        "env": {
            "defaults": {
                "window": "24h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    assert "error" not in context
    assert context["command"] == "/graph query"
    assert context["params"]["query"] == "machine learning trends"
    assert context["params"]["window"] == "3d"

    # Check graph context
    assert context["graph"]["enabled"] is True
    assert context["graph"]["build_policy"] == "on_demand"
    assert context["graph"]["hop_limit"] <= 3

    # Check models for /graph
    assert context["models"]["primary"] == "claude-4.5"

    print(f"✅ /graph context built: {context['telemetry']['correlation_id']}")


@pytest.mark.asyncio
async def test_memory_command():
    """Test /memory recall command"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/memory recall",
        "args": "query=AI breakthroughs window=1w",
        "user_lang": "en",
        "env": {
            "defaults": {
                "window": "24h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    assert "error" not in context
    assert context["command"] == "/memory recall"
    assert context["params"]["query"] == "AI breakthroughs"

    # Check memory context
    assert context["memory"]["enabled"] is True
    assert context["memory"]["semantic_keys"] is not None
    assert len(context["memory"]["semantic_keys"]) > 0

    # Check models for /memory
    assert context["models"]["primary"] == "gemini-2.5-pro"

    print(f"✅ /memory context built: {context['telemetry']['correlation_id']}")


@pytest.mark.asyncio
async def test_auto_recovery_window_expansion():
    """Test auto-recovery with window expansion"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/ask --depth=deep",
        "args": "window=6h query=nonexistent_query_12345",  # Very narrow window
        "user_lang": "en",
        "env": {
            "defaults": {
                "window": "6h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    # May expand window or return NO_DATA error
    if "error" in context:
        assert context["error"]["code"] == "NO_DATA"
        assert context["error"]["retryable"] is True
        print(f"⚠️  Auto-recovery failed (expected for nonexistent query)")
    else:
        # Window should be expanded from 6h
        print(f"✅ Auto-recovery succeeded: window={context['retrieval']['window']}")


@pytest.mark.asyncio
async def test_validation_k_final():
    """Test k_final validation and alignment"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/ask --depth=deep",
        "args": "k=8 window=24h",
        "user_lang": "en",
        "env": {
            "defaults": {
                "window": "24h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    assert "error" not in context

    # k_final should match docs length
    assert context["params"]["k_final"] == len(context["retrieval"]["docs"])

    # Should be in valid range
    assert 5 <= context["params"]["k_final"] <= 10

    print(f"✅ k_final validation passed: k={context['params']['k_final']}")


@pytest.mark.asyncio
async def test_invalid_command():
    """Test error handling for invalid command"""
    builder = get_phase3_context_builder()

    raw_input = {
        "raw_command": "/invalid_command",
        "args": "",
        "user_lang": "en",
        "env": {
            "defaults": {
                "window": "24h",
                "k_final": 6,
                "lang": "auto",
                "rerank_enabled": True,
                "timeout_s": 18,
                "budget_cents": 60,
                "max_tokens": 4096
            },
            "feature_flags": {
                "enable_rerank": True,
                "auto_expand_window": True,
                "relax_filters_on_empty": True,
                "fallback_rerank_false_on_empty": True
            },
            "version": "phase3-orchestrator"
        },
        "ab_test": {"experiment": None, "arm": None}
    }

    context = await builder.build_context(raw_input)

    # Should return error
    assert "error" in context
    assert context["error"]["code"] == "VALIDATION_FAILED"
    assert "Unsupported command" in context["error"]["user_message"]

    print(f"✅ Invalid command error handled correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("Phase3ContextBuilder Integration Tests")
    print("=" * 60)

    async def run_all_tests():
        await test_ask_command_basic()
        print()
        await test_events_command()
        print()
        await test_graph_command()
        print()
        await test_memory_command()
        print()
        await test_auto_recovery_window_expansion()
        print()
        await test_validation_k_final()
        print()
        await test_invalid_command()

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)

    asyncio.run(run_all_tests())
