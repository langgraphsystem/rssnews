"""
Integration tests for /synthesize command (Phase 2)
Tests meta-analysis flow: SynthesisAgent → format → validate
"""

import pytest
from datetime import datetime
from core.orchestrator.orchestrator import Phase1Orchestrator
from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse


@pytest.mark.asyncio
class TestSynthesisFlow:
    """Integration tests for /synthesize command"""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance"""
        return Phase1Orchestrator()

    @pytest.fixture
    def sample_agent_outputs(self):
        """Create sample agent outputs for synthesis"""
        return {
            "topic_modeler": {
                "topics": [
                    {"label": "AI Innovation", "terms": ["AI", "ML", "NLP"], "size": 15, "trend": "rising"},
                    {"label": "Blockchain", "terms": ["crypto", "web3"], "size": 8, "trend": "stable"},
                ],
                "emerging": ["LLMs", "AGI"],
            },
            "sentiment_emotion": {
                "overall": 0.6,
                "emotions": {"joy": 0.7, "fear": 0.1, "anger": 0.05, "sadness": 0.05, "surprise": 0.1},
            },
            "keyphrase_mining": {
                "keyphrases": [
                    {"phrase": "AI revolution", "norm": "ai revolution", "score": 0.9, "ngram": 2, "lang": "en"},
                    {"phrase": "machine learning", "norm": "machine learning", "score": 0.85, "ngram": 2, "lang": "en"},
                ]
            },
            "_docs": [
                {
                    "article_id": "art-1",
                    "title": "AI Innovation Article",
                    "url": "https://example.com/ai-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI is transforming industries",
                },
                {
                    "article_id": "art-2",
                    "title": "Blockchain Article",
                    "url": "https://example.com/crypto-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "Blockchain adoption growing",
                },
            ]
        }

    async def test_synthesize_basic_flow(self, orchestrator, sample_agent_outputs):
        """Test basic /synthesize flow"""
        response = await orchestrator.execute_synthesize(
            agent_outputs=sample_agent_outputs,
            window="24h",
            lang="auto",
            correlation_id="test-synth-1"
        )

        assert isinstance(response, BaseAnalysisResponse)
        assert response.header is not None
        assert len(response.tldr) <= 220
        assert 1 <= len(response.insights) <= 5
        assert len(response.evidence) >= 1

        # Check result structure
        result = response.result
        assert "summary" in result
        assert len(result["summary"]) <= 400
        assert "conflicts" in result
        assert "actions" in result
        assert 1 <= len(result["actions"]) <= 5

        # Validate actions
        for action in result["actions"]:
            assert action["impact"] in ["low", "medium", "high"]
            assert len(action["evidence_refs"]) >= 1

    async def test_synthesize_with_conflicts(self, orchestrator):
        """Test /synthesize detecting conflicts"""
        agent_outputs = {
            "sentiment_emotion": {
                "overall": -0.7,  # Negative sentiment
                "emotions": {"joy": 0.1, "fear": 0.6, "anger": 0.2, "sadness": 0.1, "surprise": 0.0},
            },
            "topic_modeler": {
                "topics": [
                    {"label": "AI Innovation", "terms": ["AI", "ML"], "size": 10, "trend": "rising"}  # Rising trend
                ],
            },
            "_docs": [
                {
                    "article_id": "art-1",
                    "title": "Article",
                    "url": "https://example.com/1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI concerns rising",
                }
            ]
        }

        response = await orchestrator.execute_synthesize(
            agent_outputs=agent_outputs,
            window="24h",
            correlation_id="test-synth-2"
        )

        assert isinstance(response, BaseAnalysisResponse)
        # Should detect conflict between negative sentiment and rising trend
        conflicts = response.result.get("conflicts", [])
        assert len(conflicts) >= 1

        # Should have conflict-type insights
        conflict_insights = [i for i in response.insights if i.type == "conflict"]
        assert len(conflict_insights) >= 1

    async def test_synthesize_minimal_agents(self, orchestrator):
        """Test /synthesize with minimal agent outputs"""
        agent_outputs = {
            "sentiment_emotion": {"overall": 0.5},
            "_docs": [
                {
                    "article_id": "art-1",
                    "title": "Article",
                    "url": "https://example.com/1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "Content",
                }
            ]
        }

        response = await orchestrator.execute_synthesize(
            agent_outputs=agent_outputs,
            window="24h",
            correlation_id="test-synth-3"
        )

        assert isinstance(response, BaseAnalysisResponse)
        # Should still generate at least 1 action
        assert len(response.result["actions"]) >= 1

    async def test_synthesize_metadata(self, orchestrator, sample_agent_outputs):
        """Test /synthesize metadata and correlation tracking"""
        correlation_id = "test-synth-metadata-123"

        response = await orchestrator.execute_synthesize(
            agent_outputs=sample_agent_outputs,
            window="24h",
            correlation_id=correlation_id
        )

        assert isinstance(response, BaseAnalysisResponse)
        assert response.meta.version == "phase2-v1.0"
        assert response.meta.correlation_id == correlation_id
        assert 0.0 <= response.meta.confidence <= 1.0
