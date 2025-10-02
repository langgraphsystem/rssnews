"""
Integration tests for /predict trends command (Phase 2)
Tests end-to-end flow: retrieval → TrendForecaster → format → validate
"""

import pytest
from datetime import datetime, timedelta
from core.orchestrator.orchestrator import Phase1Orchestrator
from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse


@pytest.mark.asyncio
class TestPredictCommand:
    """Integration tests for /predict trends command"""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance"""
        return Phase1Orchestrator()

    @pytest.fixture
    def mock_docs(self):
        """Create mock documents for testing"""
        return [
            {
                "article_id": f"art-{i}",
                "title": f"AI Trends Article {i}",
                "url": f"https://example.com/ai-{i}",
                "date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                "content": "AI and machine learning trends are evolving rapidly. Deep learning innovations continue.",
            }
            for i in range(10)
        ]

    async def test_predict_trends_basic_flow(self, orchestrator, monkeypatch):
        """Test basic /predict trends flow"""
        # Mock retrieval to return test docs
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": f"art-{i}",
                    "title": f"AI Article {i}",
                    "url": f"https://example.com/{i}",
                    "date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                    "content": "AI trends rising",
                }
                for i in range(10)
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_predict_trends(
            topic="AI",
            window="1w",
            k_final=5
        )

        # Should return BaseAnalysisResponse (not ErrorResponse)
        assert isinstance(response, BaseAnalysisResponse)
        assert response.header is not None
        assert len(response.tldr) <= 220
        assert 1 <= len(response.insights) <= 5
        assert len(response.evidence) >= 1

        # Check result structure
        result = response.result
        assert "forecast" in result
        forecast_items = result["forecast"]
        assert len(forecast_items) >= 1

        # Validate forecast item structure
        item = forecast_items[0]
        assert item["topic"] == "AI"
        assert item["direction"] in ["up", "down", "flat"]
        assert len(item["confidence_interval"]) == 2
        assert item["confidence_interval"][0] <= item["confidence_interval"][1]
        assert len(item["drivers"]) >= 1
        assert item["horizon"] == "1w"

    async def test_predict_trends_no_topic(self, orchestrator, monkeypatch):
        """Test /predict trends without topic (general forecast)"""
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": f"art-{i}",
                    "title": f"General Article {i}",
                    "url": f"https://example.com/{i}",
                    "date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                    "content": "General news content",
                }
                for i in range(10)
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_predict_trends(
            topic=None,
            window="1w",
            k_final=5
        )

        assert isinstance(response, BaseAnalysisResponse)
        assert response.result["forecast"][0]["topic"] == "general"

    async def test_predict_trends_no_data(self, orchestrator, monkeypatch):
        """Test /predict trends with no documents"""
        async def mock_retrieval_node(state):
            state["docs"] = []
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_predict_trends(
            topic="AI",
            window="1w",
            k_final=5
        )

        # Should return ErrorResponse with NO_DATA code
        assert isinstance(response, ErrorResponse)
        assert response.error.code == "NO_DATA"

    async def test_predict_trends_metadata(self, orchestrator, monkeypatch):
        """Test /predict trends metadata and correlation tracking"""
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": "art-1",
                    "title": "AI Article",
                    "url": "https://example.com/1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI content",
                }
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_predict_trends(
            topic="AI",
            window="1w",
            k_final=5
        )

        assert isinstance(response, BaseAnalysisResponse)
        assert response.meta.version == "phase2-v1.0"
        assert response.meta.correlation_id is not None
        assert 0.0 <= response.meta.confidence <= 1.0
