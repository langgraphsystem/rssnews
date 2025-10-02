import pytest
from datetime import datetime

from core.orchestrator.phase3_orchestrator import Phase3Orchestrator
from schemas.analysis_schemas import BaseAnalysisResponse


@pytest.fixture()
def sample_docs():
    return [
        {
            "article_id": f"doc-{i}",
            "title": f"Document {i} on AI deployment",
            "url": f"https://example.com/doc{i}",
            "date": "2025-09-2{0}".format(i),
            "lang": "en",
            "score": 0.7 + i * 0.02,
            "snippet": "Insights about governance, infrastructure and policy for article {i}.".format(i=i)
        }
        for i in range(1, 7)
    ]


def build_context(command: str, docs, extra_params=None):
    params = {
        "window": "24h",
        "lang": "en",
        "sources": ["example.com"],
        "k_final": len(docs),
    }
    if extra_params:
        params.update(extra_params)
    return {
        "command": command,
        "params": params,
        "retrieval": {
            "docs": docs,
            "window": "24h",
            "lang": "en",
            "sources": ["example.com"],
            "k_final": len(docs),
            "rerank_enabled": True
        },
        "models": {"primary": "gpt-5", "fallback": ["claude-4.5", "gemini-2.5-pro"]},
        "limits": {"max_tokens": 4096, "budget_cents": 50, "timeout_s": 12},
        "telemetry": {"correlation_id": "test-phase3", "version": "phase3-orchestrator"},
        "ab_test": {"experiment": None, "arm": None}
    }


def validate_response(raw: dict):
    BaseAnalysisResponse.model_validate(raw)


def test_agentic_response(sample_docs):
    orchestrator = Phase3Orchestrator()
    context = build_context("/ask --depth=deep", sample_docs, {"query": "How is AI governance evolving?", "depth": 3})
    raw_response = orchestrator.execute(context)
    validate_response(raw_response)
    assert raw_response["meta"]["iterations"] >= 1
    assert raw_response["result"]["steps"]


def test_graph_response(sample_docs):
    orchestrator = Phase3Orchestrator()
    context = build_context("/graph query", sample_docs, {"topic": "AI governance"})
    raw_response = orchestrator.execute(context)
    validate_response(raw_response)
    assert raw_response["result"]["subgraph"]["nodes"]
    assert raw_response["result"]["answer"]


def test_memory_recall_response(sample_docs):
    orchestrator = Phase3Orchestrator()
    context = build_context("/memory recall", sample_docs)
    raw_response = orchestrator.execute(context)
    validate_response(raw_response)
    assert raw_response["result"]["operation"] == "recall"
    assert raw_response["result"]["records"]
