"""Unit tests for ModelRouter"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.models.model_router import ModelRouter, ModelUnavailableError


@pytest.fixture
def model_router():
    """Create ModelRouter instance"""
    return ModelRouter()


@pytest.fixture
def sample_docs():
    """Sample documents for context"""
    return [
        {
            "title": "AI Advances",
            "snippet": "Major breakthroughs in AI...",
            "date": "2025-01-15",
            "url": "https://example.com/ai"
        },
        {
            "title": "Tech News",
            "snippet": "Latest technology updates...",
            "date": "2025-01-14",
            "url": "https://example.com/tech"
        }
    ]


class TestModelRouter:
    """Test suite for ModelRouter"""

    @pytest.mark.asyncio
    async def test_call_with_fallback_success_primary(self, model_router, sample_docs):
        """Test successful call to primary model"""
        with patch.object(model_router, '_call_model', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ("Test response", 500)

            response, metadata = await model_router.call_with_fallback(
                prompt="Test prompt",
                docs=sample_docs,
                primary="gpt-5",
                fallback=["claude-4.5"],
                timeout_s=10
            )

            assert response["content"] == "Test response"
            assert response["model"] == "gpt-5"
            assert metadata["tokens_used"] == 500
            assert metadata["fallback_used"] is False

    @pytest.mark.asyncio
    async def test_call_with_fallback_uses_fallback(self, model_router, sample_docs):
        """Test fallback chain when primary fails"""
        with patch.object(model_router, '_call_model', new_callable=AsyncMock) as mock_call:
            # Primary fails, fallback succeeds
            mock_call.side_effect = [
                Exception("Primary failed"),
                ("Fallback response", 300)
            ]

            response, metadata = await model_router.call_with_fallback(
                prompt="Test prompt",
                docs=sample_docs,
                primary="gpt-5",
                fallback=["claude-4.5"],
                timeout_s=10
            )

            assert response["content"] == "Fallback response"
            assert response["model"] == "claude-4.5"
            assert metadata["fallback_used"] is True

    @pytest.mark.asyncio
    async def test_call_with_fallback_all_fail(self, model_router, sample_docs):
        """Test ModelUnavailableError when all models fail"""
        with patch.object(model_router, '_call_model', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("All models failed")

            with pytest.raises(ModelUnavailableError):
                await model_router.call_with_fallback(
                    prompt="Test prompt",
                    docs=sample_docs,
                    primary="gpt-5",
                    fallback=["claude-4.5", "gemini-2.5-pro"],
                    timeout_s=10
                )

    def test_build_context(self, model_router, sample_docs):
        """Test context building from documents"""
        context = model_router._build_context(sample_docs, max_docs=2)

        assert "[1] AI Advances" in context
        assert "[2] Tech News" in context
        assert "https://example.com/ai" in context
        assert "2025-01-15" in context

    def test_calculate_cost(self, model_router):
        """Test cost calculation"""
        cost = model_router._calculate_cost("gpt-5", 1000)

        # 1000 tokens: 700 input (0.7¢) + 300 output (0.9¢) = 1.6¢
        assert cost > 0
        assert cost < 2.0

    def test_estimate_tokens(self, model_router):
        """Test token estimation"""
        prompt = "a" * 400  # 400 chars
        response = "b" * 600  # 600 chars

        tokens = model_router._estimate_tokens(prompt, response)

        # ~1000 chars / 4 = 250 tokens
        assert 200 < tokens < 300


@pytest.mark.asyncio
async def test_model_router_timeout(model_router, sample_docs):
    """Test timeout handling"""
    import asyncio

    async def slow_call(*args, **kwargs):
        await asyncio.sleep(2)
        return ("Response", 100)

    with patch.object(model_router, '_call_model', new=slow_call):
        with pytest.raises(ModelUnavailableError):
            await model_router.call_with_fallback(
                prompt="Test",
                docs=sample_docs,
                primary="gpt-5",
                fallback=[],
                timeout_s=1  # 1 second timeout
            )
