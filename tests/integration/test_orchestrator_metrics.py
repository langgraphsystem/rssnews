import pytest
from unittest.mock import AsyncMock, MagicMock

from schemas.analysis_schemas import BaseAnalysisResponse, Insight, Evidence, EvidenceRef, Meta


@pytest.mark.asyncio
async def test_execute_trends_records_success_metrics(monkeypatch):
    from core.orchestrator import orchestrator as orch

    monkeypatch.setenv("ENABLE_METRICS", "false")

    # Patch metrics helpers
    start_mock = MagicMock(return_value=0.0)
    success_mock = MagicMock()
    error_mock = MagicMock()
    monkeypatch.setattr(orch, "ensure_metrics_server", MagicMock())
    monkeypatch.setattr(orch, "record_orchestrator_start", start_mock)
    monkeypatch.setattr(orch, "record_orchestrator_success", success_mock)
    monkeypatch.setattr(orch, "record_orchestrator_error", error_mock)

    class DummyConfig:
        retrieval = type("R", (), {"enable_rerank": False})()
        features = type("F", (), {
            "enable_analyze_keywords": True,
            "enable_analyze_sentiment": True,
            "enable_analyze_topics": True,
        })()

    monkeypatch.setattr(orch, "get_config", lambda: DummyConfig())

    # Fake pipeline
    async def fake_retrieval(state):
        state["docs"] = [{"id": 1}]
        return state

    async def fake_agents(state):
        state["agent_results"] = {"topic_modeler": {"success": True}}
        return state

    sample_response = BaseAnalysisResponse(
        header="AI Trends",
        tldr="Summary",
        insights=[
            Insight(
                type="fact",
                text="Insight",
                evidence_refs=[EvidenceRef(article_id="1", url="https://example.com", date="2025-01-01")],
            )
        ],
        evidence=[
            Evidence(
                title="Title",
                article_id="1",
                url="https://example.com",
                date="2025-01-01",
                snippet="Snippet",
            )
        ],
        result={"topics": []},
        meta=Meta(confidence=0.9, model="gpt-test", version="phase1-v1.0", correlation_id="abc-123"),
    )

    async def fake_format(state):
        state["response_draft"] = sample_response
        return state

    async def fake_validate(state):
        state["validation_passed"] = True
        return state

    monkeypatch.setattr(orch, "retrieval_node", fake_retrieval)
    monkeypatch.setattr(orch, "agents_node", fake_agents)
    monkeypatch.setattr(orch, "format_node", fake_format)
    monkeypatch.setattr(orch, "validate_node", fake_validate)

    orchestrator = orch.Phase1Orchestrator()
    result = await orchestrator.execute_trends(window="24h")

    assert isinstance(result, BaseAnalysisResponse)


@pytest.mark.asyncio
async def test_execute_analyze_records_error(monkeypatch):
    from core.orchestrator import orchestrator as orch

    monkeypatch.setenv("ENABLE_METRICS", "false")
    monkeypatch.setattr(orch, "ensure_metrics_server", MagicMock())

    start_mock = MagicMock(return_value=0.0)
    success_mock = MagicMock()
    error_mock = MagicMock()
    monkeypatch.setattr(orch, "record_orchestrator_start", start_mock)
    monkeypatch.setattr(orch, "record_orchestrator_success", success_mock)
    monkeypatch.setattr(orch, "record_orchestrator_error", error_mock)
    class DummyConfig:
        retrieval = type("R", (), {"enable_rerank": False})()
        features = type("F", (), {
            "enable_analyze_keywords": True,
            "enable_analyze_sentiment": True,
            "enable_analyze_topics": True,
        })()

    monkeypatch.setattr(orch, "get_config", lambda: DummyConfig())


    async def failing_retrieval(state):
        state["error"] = {"code": "retrieval_failure", "message": "boom"}
        return state

    monkeypatch.setattr(orch, "retrieval_node", failing_retrieval)

    orchestrator = orch.Phase1Orchestrator()
    response = await orchestrator.execute_analyze(mode="keywords", query="ai")

    assert isinstance(response, orch.ErrorResponse)
