import pytest

from services.orchestrator import execute_phase3_context
from schemas.analysis_schemas import BaseAnalysisResponse


def _sample_docs():
    return [
        {
            "article_id": f"d{i}",
            "title": f"Article {i} about AI governance and infra",
            "url": f"https://example.com/a{i}",
            "date": "2025-09-2{}".format(i),
            "lang": "en",
            "score": 0.7 + i * 0.02,
            "snippet": "Short snippet {}".format(i)
        }
        for i in range(1, 7)
    ]


@pytest.mark.asyncio
async def test_events_link_integration():
    docs = _sample_docs()
    context = {
        'command': '/events link',
        'params': {'lang': 'en', 'window': '24h', 'k_final': len(docs), 'topic': 'AI'},
        'retrieval': {'docs': docs, 'window': '24h', 'lang': 'en', 'sources': ['example.com'], 'k_final': len(docs), 'rerank_enabled': True},
        'graph': {'enabled': False, 'entities': None, 'relations': None, 'build_policy': 'cached_only', 'hop_limit': 1},
        'memory': {'enabled': False, 'episodic': None, 'semantic_keys': None},
        'models': {'primary': 'gpt-5', 'fallback': ['claude-4.5', 'gemini-2.5-pro']},
        'limits': {'max_tokens': 4096, 'budget_cents': 50, 'timeout_s': 12},
        'telemetry': {'correlation_id': 'it-events', 'version': 'phase3-orchestrator'}
    }
    resp = await execute_phase3_context(context)
    BaseAnalysisResponse.model_validate(resp)
    assert resp['result']['events']
    assert resp['result']['causal_links']


@pytest.mark.asyncio
async def test_graph_query_integration():
    docs = _sample_docs()
    context = {
        'command': '/graph query',
        'params': {'lang': 'en', 'window': '24h', 'k_final': len(docs), 'topic': 'AI'},
        'retrieval': {'docs': docs, 'window': '24h', 'lang': 'en', 'sources': ['example.com'], 'k_final': len(docs), 'rerank_enabled': True},
        'graph': {'enabled': True, 'entities': None, 'relations': None, 'build_policy': 'on_demand', 'hop_limit': 2},
        'memory': {'enabled': False, 'episodic': None, 'semantic_keys': None},
        'models': {'primary': 'claude-4.5', 'fallback': ['gpt-5', 'gemini-2.5-pro']},
        'limits': {'max_tokens': 4096, 'budget_cents': 50, 'timeout_s': 12},
        'telemetry': {'correlation_id': 'it-graph', 'version': 'phase3-orchestrator'}
    }
    resp = await execute_phase3_context(context)
    BaseAnalysisResponse.model_validate(resp)
    assert resp['result']['subgraph']['nodes']
    assert resp['result']['answer']


@pytest.mark.asyncio
async def test_events_degradation_and_ab():
    docs = _sample_docs()
    context = {
        'command': '/events link',
        'params': {'lang': 'en', 'window': '24h', 'k_final': len(docs), 'topic': 'AI'},
        'retrieval': {'docs': docs, 'window': '24h', 'lang': 'en', 'sources': ['example.com'], 'k_final': len(docs), 'rerank_enabled': True},
        'graph': {'enabled': False, 'entities': None, 'relations': None, 'build_policy': 'cached_only', 'hop_limit': 1},
        'memory': {'enabled': False, 'episodic': None, 'semantic_keys': None},
        'models': {'primary': 'gpt-5', 'fallback': ['claude-4.5', 'gemini-2.5-pro']},
        # Tight limits to trigger degradation
        'limits': {'max_tokens': 2048, 'budget_cents': 20, 'timeout_s': 8},
        'telemetry': {'correlation_id': 'it-events-ab', 'version': 'phase3-orchestrator'},
        'ab_test': {'experiment': 'phase3-default', 'arm': 'B'}
    }
    resp = await execute_phase3_context(context)
    BaseAnalysisResponse.model_validate(resp)
    assert resp['warnings']  # expect some degradation warnings
    assert resp['result']['events']
    # arm B should not have more causal links than events (and slightly trimmed)
    assert len(resp['result']['causal_links']) <= len(resp['result']['events'])


@pytest.mark.asyncio
async def test_graph_degradation_and_ab():
    docs = _sample_docs()
    context = {
        'command': '/graph query',
        'params': {'lang': 'en', 'window': '24h', 'k_final': len(docs), 'topic': 'AI'},
        'retrieval': {'docs': docs, 'window': '24h', 'lang': 'en', 'sources': ['example.com'], 'k_final': len(docs), 'rerank_enabled': True},
        'graph': {'enabled': True, 'entities': None, 'relations': None, 'build_policy': 'on_demand', 'hop_limit': 2},
        'memory': {'enabled': False, 'episodic': None, 'semantic_keys': None},
        'models': {'primary': 'claude-4.5', 'fallback': ['gpt-5', 'gemini-2.5-pro']},
        # Tight limits to trigger degradation
        'limits': {'max_tokens': 2048, 'budget_cents': 20, 'timeout_s': 8},
        'telemetry': {'correlation_id': 'it-graph-ab', 'version': 'phase3-orchestrator'},
        'ab_test': {'experiment': 'phase3-default', 'arm': 'B'}
    }
    resp = await execute_phase3_context(context)
    BaseAnalysisResponse.model_validate(resp)
    assert resp['warnings']
    assert resp['result']['subgraph']['nodes']
    # arm B favors shorter paths (<= 3 nodes)
    if resp['result']['paths']:
        for p in resp['result']['paths']:
            assert len(p['nodes']) <= 3
