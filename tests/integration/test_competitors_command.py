"""
Integration tests for /analyze competitors command (Phase 2)
Tests end-to-end flow: retrieval → CompetitorNews → format → validate
"""

import pytest
from datetime import datetime
from core.orchestrator.orchestrator import Phase1Orchestrator
from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse


@pytest.mark.asyncio
class TestCompetitorsCommand:
    """Integration tests for /analyze competitors command"""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance"""
        return Phase1Orchestrator()

    async def test_competitors_basic_flow(self, orchestrator, monkeypatch):
        """Test basic /analyze competitors flow"""
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": "art-1",
                    "title": "TechCrunch AI Article",
                    "url": "https://techcrunch.com/ai-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI machine learning deep learning",
                },
                {
                    "article_id": "art-2",
                    "title": "Wired AI Article",
                    "url": "https://wired.com/ai-2",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI neural networks",
                },
                {
                    "article_id": "art-3",
                    "title": "CoinDesk Crypto Article",
                    "url": "https://coindesk.com/crypto-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "blockchain cryptocurrency",
                },
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_analyze_competitors(
            domains=["techcrunch.com", "wired.com", "coindesk.com"],
            niche=None,
            window="1w",
            k_final=10
        )

        assert isinstance(response, BaseAnalysisResponse)
        assert response.header is not None
        assert len(response.tldr) <= 220
        assert 1 <= len(response.insights) <= 5
        assert len(response.evidence) >= 1

        # Check result structure
        result = response.result
        assert "overlap_matrix" in result
        assert "positioning" in result
        assert "top_domains" in result

        # Validate positioning
        positioning = result["positioning"]
        assert len(positioning) >= 1
        for pos in positioning:
            assert pos["stance"] in ["leader", "fast_follower", "niche"]
            assert len(pos["domain"]) > 0

    async def test_competitors_with_niche(self, orchestrator, monkeypatch):
        """Test /analyze competitors with niche filter"""
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": f"art-{i}",
                    "title": f"AI Article {i}",
                    "url": f"https://example{i}.com/ai",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI machine learning",
                }
                for i in range(10)
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_analyze_competitors(
            domains=None,
            niche="AI",
            window="1w",
            k_final=10
        )

        assert isinstance(response, BaseAnalysisResponse)
        assert len(response.result["top_domains"]) >= 1

    async def test_competitors_gaps_detection(self, orchestrator, monkeypatch):
        """Test competitor gap detection"""
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": "art-1",
                    "title": "AI Article",
                    "url": "https://techcrunch.com/ai",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI ML",
                },
                {
                    "article_id": "art-2",
                    "title": "Blockchain Article",
                    "url": "https://coindesk.com/crypto",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "blockchain crypto",
                },
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_analyze_competitors(
            domains=None,
            niche=None,
            window="1w",
            k_final=10
        )

        assert isinstance(response, BaseAnalysisResponse)
        # Should detect gaps between AI and blockchain coverage
        assert "gaps" in response.result

    async def test_competitors_no_data(self, orchestrator, monkeypatch):
        """Test /analyze competitors with no documents"""
        async def mock_retrieval_node(state):
            state["docs"] = []
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        response = await orchestrator.execute_analyze_competitors(
            domains=["techcrunch.com"],
            niche=None,
            window="1w",
            k_final=10
        )

        assert isinstance(response, ErrorResponse)
        assert response.error.code == "NO_DATA"
