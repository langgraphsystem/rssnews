"""
Unit tests for core/ai_models/model_manager.py
Tests model routing, fallback chains, budget enforcement, telemetry
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from core.ai_models.model_manager import ModelManager, ModelInvocation, BudgetTracker
from infra.config.phase1_config import ModelRoute


class TestModelManager:
    """Test ModelManager class"""

    @pytest.fixture
    def mock_config(self):
        """Mock Phase1Config"""
        config = Mock()
        config.budget.enable_budget_tracking = True
        config.budget.max_tokens_per_command = 8000
        config.budget.max_cost_cents_per_command = 50

        # Model routes
        config.models.keyphrase_mining = ModelRoute(
            primary="gemini-2.5-pro",
            fallback=["claude-4.5", "gpt-5"],
            timeout_seconds=10
        )
        config.models.sentiment_emotion = ModelRoute(
            primary="gpt-5",
            fallback=["claude-4.5"],
            timeout_seconds=12
        )
        config.models.topic_modeler = ModelRoute(
            primary="claude-4.5",
            fallback=["gpt-5", "gemini-2.5-pro"],
            timeout_seconds=15
        )

        return config

    @pytest.fixture
    def manager(self, mock_config):
        """Create ModelManager with mocked config"""
        with patch('core.ai_models.model_manager.get_config', return_value=mock_config):
            manager = ModelManager(correlation_id="test-123")
            return manager

    @pytest.mark.asyncio
    async def test_model_routing_keyphrase_mining(self, manager):
        """Test routing to Gemini for keyphrase_mining"""
        route = manager._get_route("keyphrase_mining")

        assert route is not None
        assert route.primary == "gemini-2.5-pro"
        assert route.fallback == ["claude-4.5", "gpt-5"]
        assert route.timeout_seconds == 10

    @pytest.mark.asyncio
    async def test_model_routing_sentiment(self, manager):
        """Test routing to GPT-5 for sentiment_emotion"""
        route = manager._get_route("sentiment_emotion")

        assert route is not None
        assert route.primary == "gpt-5"
        assert route.fallback == ["claude-4.5"]
        assert route.timeout_seconds == 12

    @pytest.mark.asyncio
    async def test_successful_primary_model(self, manager):
        """Test successful invocation with primary model"""
        mock_client = AsyncMock()
        mock_client.generate_text = AsyncMock(return_value="Test response")

        manager._get_gpt5_client = Mock(return_value=mock_client)

        result, warnings = await manager.invoke_model(
            task="sentiment_emotion",
            prompt="Test prompt",
            max_tokens=500
        )

        assert result == "Test response"
        assert len(warnings) == 0
        assert manager.budget_tracker.invocations[0].success is True

    @pytest.mark.asyncio
    async def test_primary_timeout_triggers_fallback(self, manager):
        """Test timeout on primary triggers fallback"""
        # Mock GPT-5 to timeout
        mock_gpt5 = AsyncMock()
        mock_gpt5.generate_text = AsyncMock(side_effect=asyncio.TimeoutError())

        # Mock Claude to succeed
        mock_claude = AsyncMock()
        mock_claude._make_api_request = AsyncMock(return_value={
            "content": [{"type": "text", "text": "Fallback response"}]
        })

        manager._get_gpt5_client = Mock(return_value=mock_gpt5)
        manager._get_claude_client = Mock(return_value=mock_claude)

        result, warnings = await manager.invoke_model(
            task="sentiment_emotion",
            prompt="Test prompt",
            max_tokens=500
        )

        assert result == "Fallback response"
        assert len(warnings) > 0
        assert "fallback_used" in warnings[0]

    @pytest.mark.asyncio
    async def test_all_models_fail(self, manager):
        """Test all models failing raises exception"""
        # Mock all models to fail
        mock_gpt5 = AsyncMock()
        mock_gpt5.generate_text = AsyncMock(side_effect=Exception("API Error"))

        mock_claude = AsyncMock()
        mock_claude._make_api_request = AsyncMock(side_effect=Exception("API Error"))

        manager._get_gpt5_client = Mock(return_value=mock_gpt5)
        manager._get_claude_client = Mock(return_value=mock_claude)

        with pytest.raises(Exception, match="MODEL_UNAVAILABLE"):
            await manager.invoke_model(
                task="sentiment_emotion",
                prompt="Test prompt",
                max_tokens=500
            )

    def test_cost_estimation(self, manager):
        """Test cost estimation for different models"""
        # GPT-5
        cost_gpt5 = manager._estimate_cost("gpt-5", 1000, 500)
        expected_gpt5 = (1000/1000 * 0.3) + (500/1000 * 0.6)
        assert abs(cost_gpt5 - expected_gpt5) < 0.001

        # Claude 4.5
        cost_claude = manager._estimate_cost("claude-4.5", 1000, 500)
        expected_claude = (1000/1000 * 0.3) + (500/1000 * 1.5)
        assert abs(cost_claude - expected_claude) < 0.001

        # Gemini 2.5 Pro
        cost_gemini = manager._estimate_cost("gemini-2.5-pro", 1000, 500)
        expected_gemini = (1000/1000 * 0.125) + (500/1000 * 0.375)
        assert abs(cost_gemini - expected_gemini) < 0.001

    def test_budget_tracking(self, manager):
        """Test budget tracking after invocation"""
        manager._track_invocation(
            task="keyphrase_mining",
            model="gemini-2.5-pro",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_cents=0.25,
            latency_ms=850,
            success=True
        )

        assert manager.budget_tracker.command_tokens_used == 1500
        assert abs(manager.budget_tracker.command_cost_cents - 0.25) < 0.001
        assert len(manager.budget_tracker.invocations) == 1
        assert manager.budget_tracker.invocations[0].task == "keyphrase_mining"

    def test_budget_enforcement_tokens(self, manager):
        """Test budget cap enforcement for tokens"""
        # Exhaust token budget
        manager.budget_tracker.command_tokens_used = 8001

        assert manager._check_budget_available() is False

    def test_budget_enforcement_cost(self, manager):
        """Test budget cap enforcement for cost"""
        # Exhaust cost budget
        manager.budget_tracker.command_cost_cents = 51

        assert manager._check_budget_available() is False

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises_exception(self, manager):
        """Test budget exceeded raises exception before invocation"""
        # Exhaust budget
        manager.budget_tracker.command_tokens_used = 8001

        with pytest.raises(Exception, match="BUDGET_EXCEEDED"):
            await manager.invoke_model(
                task="keyphrase_mining",
                prompt="Test prompt"
            )

    def test_telemetry_summary(self, manager):
        """Test telemetry summary generation"""
        # Track multiple invocations
        manager._track_invocation(
            task="keyphrase_mining",
            model="gemini-2.5-pro",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_cents=0.25,
            latency_ms=850,
            success=True
        )

        manager._track_invocation(
            task="sentiment_emotion",
            model="gpt-5",
            prompt_tokens=800,
            completion_tokens=400,
            cost_cents=0.48,
            latency_ms=1200,
            success=False,
            error="TIMEOUT"
        )

        summary = manager.get_budget_summary()

        assert summary["tokens_used"] == 2700
        assert abs(summary["cost_cents"] - 0.73) < 0.01
        assert summary["invocations"] == 2
        assert summary["successful"] == 1
        assert summary["failed"] == 1

    def test_telemetry_full(self, manager):
        """Test full telemetry export"""
        manager._track_invocation(
            task="topic_modeler",
            model="claude-4.5",
            prompt_tokens=1200,
            completion_tokens=600,
            cost_cents=1.20,
            latency_ms=2500,
            success=True
        )

        telemetry = manager.get_telemetry()

        assert telemetry["correlation_id"] == "test-123"
        assert telemetry["budget"]["tokens_used"] == 1800
        assert len(telemetry["invocations"]) == 1
        assert telemetry["invocations"][0]["task"] == "topic_modeler"
        assert telemetry["invocations"][0]["model"] == "claude-4.5"
        assert telemetry["invocations"][0]["latency_ms"] == 2500

    @pytest.mark.asyncio
    async def test_unknown_task_raises_error(self, manager, mock_config):
        """Test unknown task raises ValueError"""
        # Make sure unknown_task returns None
        mock_config.models.unknown_task = None

        with pytest.raises(ValueError, match="Unknown task"):
            await manager.invoke_model(
                task="unknown_task",
                prompt="Test prompt"
            )
