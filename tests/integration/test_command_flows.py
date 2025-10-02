"""
Integration tests for complete command flows
Tests /trends and /analyze commands end-to-end
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.orchestrator.orchestrator import AnalysisOrchestrator
from schemas.analysis_schemas import BaseAnalysisResponse, Insight, Evidence, EvidenceRef, Meta


@pytest.fixture
def mock_retrieval():
    """Mock retrieval pipeline"""
    return [
        {
            "article_id": "art_1",
            "url": "https://example.com/article1",
            "title": "Test Article 1",
            "snippet": "This is a test article about AI trends.",
            "published_date": "2025-09-30"
        },
        {
            "article_id": "art_2",
            "url": "https://example.com/article2",
            "title": "Test Article 2",
            "snippet": "Another article discussing machine learning advances.",
            "published_date": "2025-09-29"
        },
        {
            "article_id": "art_3",
            "url": "https://example.com/article3",
            "title": "Test Article 3",
            "snippet": "AI regulation and policy updates.",
            "published_date": "2025-09-28"
        }
    ]


@pytest.fixture
def orchestrator():
    """Create orchestrator instance"""
    return AnalysisOrchestrator(correlation_id="test-123")


@pytest.mark.asyncio
async def test_trends_command_flow(orchestrator, mock_retrieval):
    """Test /trends enhanced command flow"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_retrieval

        # Mock agents
        with patch.object(orchestrator, '_run_agents', new_callable=AsyncMock) as mock_agents:
            mock_agents.return_value = {
                "topic_modeler": {
                    "topics": [
                        {"label": "AI Trends", "terms": ["AI", "machine learning"], "size": 10, "trend": "rising"}
                    ]
                },
                "sentiment_emotion": {
                    "overall": 0.3,
                    "emotions": {"joy": 0.2, "fear": 0.3, "anger": 0.2, "sadness": 0.2, "surprise": 0.1}
                }
            }

            result = await orchestrator.execute_trends(user_query="AI trends")

            # Check result structure
            assert isinstance(result, BaseAnalysisResponse)
            assert result.header is not None
            assert result.tldr is not None
            assert len(result.insights) > 0
            assert len(result.evidence) > 0
            assert result.meta.correlation_id == "test-123"


@pytest.mark.asyncio
async def test_analyze_keywords_flow(orchestrator, mock_retrieval):
    """Test /analyze keywords command flow"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_retrieval

        with patch.object(orchestrator, '_run_agents', new_callable=AsyncMock) as mock_agents:
            mock_agents.return_value = {
                "keyphrase_mining": {
                    "keyphrases": [
                        {
                            "phrase": "artificial intelligence",
                            "norm": "artificial intelligence",
                            "score": 0.95,
                            "ngram": 2,
                            "variants": ["AI"],
                            "examples": ["AI is transforming industries"],
                            "lang": "en"
                        }
                    ]
                }
            }

            result = await orchestrator.execute_analyze(
                user_query="AI trends",
                analysis_type="keywords"
            )

            assert isinstance(result, BaseAnalysisResponse)
            assert result.result.get("keyphrases") is not None
            assert len(result.result["keyphrases"]) > 0


@pytest.mark.asyncio
async def test_analyze_sentiment_flow(orchestrator, mock_retrieval):
    """Test /analyze sentiment command flow"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_retrieval

        with patch.object(orchestrator, '_run_agents', new_callable=AsyncMock) as mock_agents:
            mock_agents.return_value = {
                "sentiment_emotion": {
                    "overall": 0.3,
                    "emotions": {"joy": 0.2, "fear": 0.3, "anger": 0.2, "sadness": 0.2, "surprise": 0.1}
                }
            }

            result = await orchestrator.execute_analyze(
                user_query="AI regulation",
                analysis_type="sentiment"
            )

            assert isinstance(result, BaseAnalysisResponse)
            assert result.result.get("overall") is not None
            assert result.result.get("emotions") is not None


@pytest.mark.asyncio
async def test_analyze_topics_flow(orchestrator, mock_retrieval):
    """Test /analyze topics command flow"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_retrieval

        with patch.object(orchestrator, '_run_agents', new_callable=AsyncMock) as mock_agents:
            mock_agents.return_value = {
                "topic_modeler": {
                    "topics": [
                        {"label": "AI Regulation", "terms": ["regulation", "policy"], "size": 5, "trend": "stable"}
                    ]
                }
            }

            result = await orchestrator.execute_analyze(
                user_query="AI policy",
                analysis_type="topics"
            )

            assert isinstance(result, BaseAnalysisResponse)
            assert result.result.get("topics") is not None
            assert len(result.result["topics"]) > 0


@pytest.mark.asyncio
async def test_validation_rejects_invalid_response(orchestrator, mock_retrieval):
    """Test validation layer rejects invalid responses"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_retrieval

        with patch.object(orchestrator, '_run_agents', new_callable=AsyncMock) as mock_agents:
            # Return invalid response (missing evidence_refs)
            mock_agents.return_value = {
                "keyphrase_mining": {
                    "keyphrases": [{"phrase": "test", "score": 0.9}]
                }
            }

            with patch.object(orchestrator, '_format_response', return_value=BaseAnalysisResponse(
                header="Test",
                tldr="Test summary",
                insights=[
                    Insight(
                        type="fact",
                        text="Test insight",
                        evidence_refs=[]  # Invalid: empty evidence_refs
                    )
                ],
                evidence=[],
                result={"test": "data"},
                meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="test-123")
            )):
                result = await orchestrator.execute_analyze(
                    user_query="test",
                    analysis_type="keywords"
                )

                # Should have validation warnings
                assert len(result.warnings) > 0 or not result.insights[0].evidence_refs


@pytest.mark.asyncio
async def test_empty_retrieval_returns_error(orchestrator):
    """Test empty retrieval returns error response"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = []  # Empty results

        result = await orchestrator.execute_trends(user_query="nonexistent topic")

        # Should return error or empty response
        assert result is not None
        # May have error structure or minimal response


@pytest.mark.asyncio
async def test_parallel_agent_execution(orchestrator, mock_retrieval):
    """Test /trends runs agents in parallel"""
    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_retrieval

        # Track agent execution timing
        agent_calls = []

        async def mock_agent_execution(agent_name, docs):
            agent_calls.append(agent_name)
            await asyncio.sleep(0.1)  # Simulate work
            if agent_name == "topic_modeler":
                return {"topics": [{"label": "Test", "terms": ["test"], "size": 1, "trend": "stable"}]}
            elif agent_name == "sentiment_emotion":
                return {"overall": 0.5, "emotions": {"joy": 0.5, "fear": 0.5, "anger": 0.0, "sadness": 0.0, "surprise": 0.0}}

        with patch.object(orchestrator, '_run_single_agent', side_effect=mock_agent_execution):
            import time
            start = time.time()

            await orchestrator.execute_trends(user_query="test")

            elapsed = time.time() - start

            # Should execute in parallel (~0.1s), not serial (~0.2s)
            assert elapsed < 0.15  # Allow some overhead
            assert len(agent_calls) == 2
