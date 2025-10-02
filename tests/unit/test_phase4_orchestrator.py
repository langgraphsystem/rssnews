"""
Unit tests for Phase4Orchestrator
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.orchestrator.phase4_orchestrator import Phase4Orchestrator, create_phase4_orchestrator


@pytest.fixture
def orchestrator():
    """Create Phase4Orchestrator instance"""
    return Phase4Orchestrator()


@pytest.fixture
def mock_context():
    """Create mock Phase 4 context"""
    return {
        "command": "/dashboard live",
        "params": {
            "metrics": ["traffic", "ctr", "conv"],
            "lang": "en"
        },
        "retrieval": {
            "docs": [
                {"title": "Test Article 1", "score": 0.9, "article_id": "1", "url": "http://test.com/1"},
                {"title": "Test Article 2", "score": 0.8, "article_id": "2", "url": "http://test.com/2"}
            ],
            "window": "24h",
            "k_final": 5
        },
        "history": {
            "snapshots": [],
            "metrics": []
        },
        "models": {
            "primary": "claude-4.5",
            "fallback": ["gpt-5"]
        },
        "limits": {
            "max_tokens": 4000,
            "budget_cents": 25,
            "timeout_s": 15
        },
        "ab_test": {},
        "telemetry": {
            "correlation_id": "test-123",
            "version": "phase4-v1.0"
        }
    }


class TestPhase4Orchestrator:
    """Test Phase4Orchestrator functionality"""

    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initializes correctly"""
        assert orchestrator is not None
        assert orchestrator.model_router is not None

    @pytest.mark.asyncio
    async def test_dashboard_command(self, orchestrator, mock_context):
        """Test /dashboard command execution"""
        mock_context["command"] = "/dashboard live"

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert result.get("header") == "Live Dashboard"
        assert "widgets" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_reports_command(self, orchestrator, mock_context):
        """Test /reports generate command"""
        mock_context["command"] = "/reports generate weekly"

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "Weekly Report" in result.get("header", "")
        assert "report" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_schedule_command(self, orchestrator, mock_context):
        """Test /schedule report command"""
        mock_context["command"] = "/schedule report weekly"
        mock_context["params"]["schedule"] = {"cron": "0 9 * * 1"}

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "schedule" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_alerts_command(self, orchestrator, mock_context):
        """Test /alerts setup command"""
        mock_context["command"] = "/alerts setup"

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "alerts" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_optimize_listing_command(self, orchestrator, mock_context):
        """Test /optimize listing command"""
        mock_context["command"] = "/optimize listing"
        mock_context["params"]["goal"] = "ctr"

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "listing" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_optimize_campaign_command(self, orchestrator, mock_context):
        """Test /optimize campaign command"""
        mock_context["command"] = "/optimize campaign"
        mock_context["params"]["channels"] = ["web"]
        mock_context["params"]["metrics"] = ["ctr", "roi"]

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "campaign" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_brief_command(self, orchestrator, mock_context):
        """Test /brief assets command"""
        mock_context["command"] = "/brief assets"
        mock_context["params"]["channels"] = ["social", "web"]

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "briefs" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_pricing_command(self, orchestrator, mock_context):
        """Test /pricing advisor command"""
        mock_context["command"] = "/pricing advisor"
        mock_context["params"]["targets"] = {"roi_min": 2.5}

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        assert "pricing" in result.get("result", {})

    @pytest.mark.asyncio
    async def test_unknown_command(self, orchestrator, mock_context):
        """Test unknown command returns error"""
        mock_context["command"] = "/unknown"

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" in result
        assert result["error"]["code"] == "INTERNAL"

    @pytest.mark.asyncio
    async def test_dashboard_with_custom_metrics(self, orchestrator, mock_context):
        """Test dashboard with custom metrics"""
        mock_context["command"] = "/dashboard custom"
        mock_context["params"]["metrics"] = ["roi", "cac", "ltv"]

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        widgets = result.get("result", {}).get("widgets", [])
        assert len(widgets) >= 3

    @pytest.mark.asyncio
    async def test_dashboard_with_history(self, orchestrator, mock_context):
        """Test dashboard includes history data"""
        mock_context["history"]["metrics"] = [
            {"ts": "2025-01-01T00:00:00Z", "metric": "traffic", "value": 1000.0},
            {"ts": "2025-01-01T01:00:00Z", "metric": "traffic", "value": 1100.0}
        ]

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        widgets = result.get("result", {}).get("widgets", [])
        # Should have timeseries widget
        timeseries_widgets = [w for w in widgets if w.get("type") == "timeseries"]
        assert len(timeseries_widgets) > 0

    @pytest.mark.asyncio
    async def test_reports_with_competitors(self, orchestrator, mock_context):
        """Test reports include competitor analysis"""
        mock_context["command"] = "/reports generate monthly"
        mock_context["history"]["competitors"] = [
            {"domain": "competitor1.com", "overlap_score": 0.8},
            {"domain": "competitor2.com", "overlap_score": 0.6}
        ]

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        report = result.get("result", {}).get("report", {})
        sections = report.get("sections", [])
        # Should have competitor section
        competitor_sections = [s for s in sections if "Competitors" in s.get("title", "")]
        assert len(competitor_sections) > 0

    @pytest.mark.asyncio
    async def test_listing_optimization_with_experiments(self, orchestrator, mock_context):
        """Test listing optimization includes A/B experiments"""
        mock_context["command"] = "/optimize listing"
        mock_context["params"]["goal"] = "conversion"

        result = await orchestrator.execute(mock_context)

        assert result is not None
        assert "error" not in result
        listing = result.get("result", {}).get("listing", {})
        experiments = listing.get("experiments", [])
        assert len(experiments) >= 2

    @pytest.mark.asyncio
    async def test_factory_function(self):
        """Test factory function returns orchestrator"""
        orch = create_phase4_orchestrator()
        assert orch is not None
        assert isinstance(orch, Phase4Orchestrator)

    @pytest.mark.asyncio
    async def test_error_handling(self, orchestrator):
        """Test orchestrator handles errors gracefully"""
        invalid_context = {"command": "/dashboard"}  # Missing required fields

        result = await orchestrator.execute(invalid_context)

        assert result is not None
        assert "error" in result

    @pytest.mark.asyncio
    async def test_insights_generation(self, orchestrator, mock_context):
        """Test insights are generated for dashboard"""
        result = await orchestrator.execute(mock_context)

        assert result is not None
        insights = result.get("insights", [])
        assert len(insights) > 0
        assert all("type" in i for i in insights)
        assert all("text" in i for i in insights)

    @pytest.mark.asyncio
    async def test_evidence_formatting(self, orchestrator, mock_context):
        """Test evidence is properly formatted"""
        result = await orchestrator.execute(mock_context)

        assert result is not None
        evidence = result.get("evidence", [])
        if evidence:
            assert all("title" in e for e in evidence)
            assert all("url" in e for e in evidence)
            assert all("date" in e for e in evidence)

    @pytest.mark.asyncio
    async def test_meta_information(self, orchestrator, mock_context):
        """Test metadata is included in response"""
        result = await orchestrator.execute(mock_context)

        assert result is not None
        meta = result.get("meta", {})
        assert "correlation_id" in meta
        assert meta["correlation_id"] == "test-123"
        assert "version" in meta


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
