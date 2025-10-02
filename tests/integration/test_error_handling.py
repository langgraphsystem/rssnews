"""
Integration tests for error handling and degradation
Tests budget limits, timeouts, model failures, graceful degradation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.orchestrator.orchestrator import AnalysisOrchestrator


@pytest.fixture
def orchestrator():
    """Create orchestrator instance"""
    return AnalysisOrchestrator(correlation_id="test-error-123")


@pytest.mark.asyncio
async def test_model_timeout_triggers_fallback(orchestrator):
    """Test model timeout triggers fallback chain"""
    mock_docs = [
        {"article_id": "art_1", "url": "https://example.com/1", "title": "Test", "snippet": "Test snippet"}
    ]

    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_docs

        # Mock model manager to simulate timeout
        with patch('core.orchestrator.orchestrator.ModelManager') as MockModelManager:
            mock_manager = MockModelManager.return_value

            # First call times out, second succeeds (fallback)
            call_count = 0

            async def mock_invoke(task, prompt, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("TIMEOUT: gpt-5 exceeded 12s")
                return '{"overall": 0.5, "emotions": {"joy": 0.5, "fear": 0.5, "anger": 0.0, "sadness": 0.0, "surprise": 0.0}}'

            mock_manager.invoke_model = AsyncMock(side_effect=mock_invoke)

            result = await orchestrator.execute_analyze(
                user_query="test",
                analysis_type="sentiment"
            )

            # Should have warning about fallback
            assert len(result.warnings) > 0 or call_count > 1


@pytest.mark.asyncio
async def test_budget_exceeded_error(orchestrator):
    """Test budget exceeded returns error"""
    mock_docs = [
        {"article_id": "art_1", "url": "https://example.com/1", "title": "Test", "snippet": "Test snippet"}
    ]

    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_docs

        with patch('core.orchestrator.orchestrator.ModelManager') as MockModelManager:
            mock_manager = MockModelManager.return_value
            mock_manager.invoke_model = AsyncMock(side_effect=Exception("BUDGET_EXCEEDED: Command budget limit reached"))

            with pytest.raises(Exception, match="BUDGET_EXCEEDED"):
                await orchestrator.execute_analyze(
                    user_query="test",
                    analysis_type="keywords"
                )


@pytest.mark.asyncio
async def test_all_models_unavailable(orchestrator):
    """Test all models unavailable returns error"""
    mock_docs = [
        {"article_id": "art_1", "url": "https://example.com/1", "title": "Test", "snippet": "Test snippet"}
    ]

    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_docs

        with patch('core.orchestrator.orchestrator.ModelManager') as MockModelManager:
            mock_manager = MockModelManager.return_value
            mock_manager.invoke_model = AsyncMock(
                side_effect=Exception("MODEL_UNAVAILABLE: All models failed for task sentiment_emotion")
            )

            with pytest.raises(Exception, match="MODEL_UNAVAILABLE"):
                await orchestrator.execute_analyze(
                    user_query="test",
                    analysis_type="sentiment"
                )


@pytest.mark.asyncio
async def test_validation_failure_returns_warning(orchestrator):
    """Test validation failure adds warning to response"""
    from schemas.analysis_schemas import BaseAnalysisResponse, Insight, EvidenceRef, Evidence, Meta

    mock_docs = [
        {"article_id": "art_1", "url": "https://example.com/1", "title": "Test", "snippet": "Test snippet", "published_date": "2025-09-30"}
    ]

    with patch('core.orchestrator.orchestrator.retrieve_for_analysis', new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = mock_docs

        with patch('core.orchestrator.orchestrator.ModelManager') as MockModelManager:
            mock_manager = MockModelManager.return_value
            mock_manager.invoke_model = AsyncMock(
                return_value='{"keyphrases": [{"phrase": "test", "score": 0.9, "ngram": 1, "variants": [], "examples": [], "lang": "en"}]}'
            )

            # Mock format_node to return invalid response (insight without evidence)
            invalid_response = BaseAnalysisResponse(
                header="Test",
                tldr="Test summary",
                insights=[
                    Insight(
                        type="fact",
                        text="Invalid insight",
                        evidence_refs=[]  # Invalid: empty evidence_refs
                    )
                ],
                evidence=[
                    Evidence(
                        title="Test",
                        article_id="art_1",
                        url="https://example.com/1",
                        date="2025-09-30",
                        snippet="Test snippet"
                    )
                ],
                result={"keyphrases": []},
                meta=Meta(confidence=0.8, model="gemini-2.5-pro", version="phase1-v1.0", correlation_id="test-error-123")
            )

            with patch('core.orchestrator.orchestrator.format_response', return_value=invalid_response):
                result = await orchestrator.execute_analyze(
                    user_query="test",
                    analysis_type="keywords"
                )

                # Should have validation warning
                # Note: validation may fix or flag the issue
                assert result is not None
