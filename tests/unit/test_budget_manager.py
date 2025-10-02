"""Unit tests for BudgetManager"""

import pytest
from core.models.budget_manager import BudgetManager, BudgetExceededError, create_budget_manager


@pytest.fixture
def budget_manager():
    """Create BudgetManager instance"""
    return create_budget_manager(max_tokens=1000, budget_cents=10, timeout_s=30)


class TestBudgetManager:
    """Test suite for BudgetManager"""

    def test_can_afford_initial(self, budget_manager):
        """Test affordability check with no usage"""
        assert budget_manager.can_afford(100, 1.0, 5.0)
        assert budget_manager.can_afford(1000, 10.0, 30.0)

    def test_can_afford_after_usage(self, budget_manager):
        """Test affordability after some usage"""
        budget_manager.record_usage(500, 5.0, 15.0)

        assert budget_manager.can_afford(400, 4.0, 10.0)
        assert not budget_manager.can_afford(600, 6.0, 20.0)  # Would exceed tokens

    def test_record_usage(self, budget_manager):
        """Test usage recording"""
        budget_manager.record_usage(100, 1.0, 5.0)

        assert budget_manager.spent_tokens == 100
        assert budget_manager.spent_cents == 1.0
        assert budget_manager.spent_time_s == 5.0

    def test_get_remaining_budget(self, budget_manager):
        """Test remaining budget calculation"""
        budget_manager.record_usage(500, 5.0, 15.0)

        remaining = budget_manager.get_remaining_budget()

        assert remaining["tokens_pct"] == 50.0  # 500/1000 = 50%
        assert remaining["cost_pct"] == 50.0    # 5/10 = 50%
        assert remaining["time_pct"] == 50.0    # 15/30 = 50%

    def test_should_degrade(self, budget_manager):
        """Test degradation trigger"""
        assert not budget_manager.should_degrade()

        # Use 80% of budget
        budget_manager.record_usage(800, 8.0, 24.0)

        assert budget_manager.should_degrade()  # < 30% remaining

    def test_get_degraded_params_ask(self, budget_manager):
        """Test degradation for /ask command"""
        budget_manager.record_usage(800, 8.0, 24.0)  # Trigger degradation

        degraded = budget_manager.get_degraded_params("/ask", {"depth": 3})

        assert degraded["depth"] == 1
        assert degraded["self_check"] is False
        assert degraded["use_rerank"] is False
        assert len(budget_manager.warnings) > 0

    def test_get_degraded_params_graph(self, budget_manager):
        """Test degradation for /graph command"""
        budget_manager.record_usage(800, 8.0, 24.0)

        degraded = budget_manager.get_degraded_params(
            "/graph",
            {"hop_limit": 3, "max_nodes": 200, "max_edges": 600}
        )

        assert degraded["hop_limit"] == 1
        assert degraded["max_nodes"] == 60
        assert degraded["max_edges"] == 180

    def test_get_degraded_params_events(self, budget_manager):
        """Test degradation for /events command"""
        budget_manager.record_usage(800, 8.0, 24.0)

        degraded = budget_manager.get_degraded_params("/events", {"k_final": 10})

        assert degraded["k_final"] == 5
        assert degraded["include_alternatives"] is False

    def test_get_degraded_params_memory(self, budget_manager):
        """Test degradation for /memory command"""
        budget_manager.record_usage(800, 8.0, 24.0)

        degraded = budget_manager.get_degraded_params("/memory", {})

        assert degraded["operation"] == "recall"

    def test_check_exceeded_tokens(self, budget_manager):
        """Test budget exceeded check for tokens"""
        budget_manager.record_usage(1100, 5.0, 15.0)

        with pytest.raises(BudgetExceededError, match="Token limit exceeded"):
            budget_manager.check_exceeded()

    def test_check_exceeded_cost(self, budget_manager):
        """Test budget exceeded check for cost"""
        budget_manager.record_usage(500, 11.0, 15.0)

        with pytest.raises(BudgetExceededError, match="Cost limit exceeded"):
            budget_manager.check_exceeded()

    def test_check_exceeded_timeout(self, budget_manager):
        """Test budget exceeded check for timeout"""
        budget_manager.record_usage(500, 5.0, 35.0)

        with pytest.raises(BudgetExceededError, match="Timeout exceeded"):
            budget_manager.check_exceeded()

    def test_get_warnings(self, budget_manager):
        """Test warnings accumulation"""
        budget_manager.record_usage(800, 8.0, 24.0)
        budget_manager.get_degraded_params("/ask", {"depth": 3})

        warnings = budget_manager.get_warnings()

        assert len(warnings) > 0
        assert any("degraded" in w.lower() or "iteration" in w.lower() for w in warnings)

    def test_reset(self, budget_manager):
        """Test budget reset"""
        budget_manager.record_usage(500, 5.0, 15.0)
        budget_manager.warnings.append("test warning")

        budget_manager.reset()

        assert budget_manager.spent_tokens == 0
        assert budget_manager.spent_cents == 0.0
        assert budget_manager.spent_time_s == 0.0
        assert len(budget_manager.warnings) == 0

    def test_get_summary(self, budget_manager):
        """Test budget summary"""
        budget_manager.record_usage(500, 5.0, 15.0)

        summary = budget_manager.get_summary()

        assert summary["spent"]["tokens"] == 500
        assert summary["spent"]["cost_cents"] == 5.0
        assert summary["spent"]["time_s"] == 15.0
        assert summary["limits"]["max_tokens"] == 1000
        assert summary["limits"]["budget_cents"] == 10
        assert summary["limits"]["timeout_s"] == 30

    def test_gradual_degradation(self):
        """Test gradual degradation as budget depletes"""
        budget = create_budget_manager(max_tokens=1000, budget_cents=10, timeout_s=30)

        # 40% used - no degradation
        budget.record_usage(400, 4.0, 12.0)
        assert not budget.should_degrade()

        # 75% used - degradation triggered
        budget.record_usage(350, 3.5, 10.5)
        assert budget.should_degrade()

        degraded = budget.get_degraded_params("/ask", {"depth": 3})
        assert degraded["depth"] < 3

    def test_critical_budget(self):
        """Test critical budget scenario"""
        budget = create_budget_manager(max_tokens=1000, budget_cents=10, timeout_s=30)

        # 85% used - critical
        budget.record_usage(850, 8.5, 25.5)

        degraded = budget.get_degraded_params("/ask", {"depth": 3, "k_final": 10})

        # Should apply critical degradation
        assert degraded["k_final"] == 3
        assert "Critical budget" in " ".join(budget.warnings)
