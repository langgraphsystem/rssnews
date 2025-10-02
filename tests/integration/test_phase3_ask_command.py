"""Integration tests for /ask command (Agentic RAG)"""

import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch

import services.phase3_handlers as phase3_handlers
from services.phase3_handlers import execute_ask_command


@pytest.fixture
def sample_docs():
    """Sample documents for retrieval"""
    return [
        {
            "article_id": "doc1",
            "title": "AI Adoption Accelerates",
            "snippet": "Companies rapidly adopt AI technologies...",
            "date": "2025-01-15",
            "url": "https://techcrunch.com/ai-adoption",
            "score": 0.95
        },
        {
            "article_id": "doc2",
            "title": "Enterprise AI Implementation",
            "snippet": "Enterprise sector shows strong AI deployment...",
            "date": "2025-01-14",
            "url": "https://wired.com/enterprise-ai",
            "score": 0.88
        },
        {
            "article_id": "doc3",
            "title": "AI Regulation Updates",
            "snippet": "New regulations shape AI landscape...",
            "date": "2025-01-13",
            "url": "https://reuters.com/ai-regulation",
            "score": 0.82
        }
    ]


@pytest.fixture
def mock_phase3_builder(sample_docs):
    """Patch context builder and retrieval for Phase 3 tests"""
    with patch('services.phase3_handlers.get_phase3_context_builder') as mock_builder, \
         patch('services.phase3_handlers.get_retrieval_client') as mock_retrieval:
        builder_instance = MagicMock()

        async def fake_build_context(raw_input):
            args = raw_input.get('args', '')
            query_match = re.search(r'query="([^"]+)"', args)
            topic_match = re.search(r'topic="([^"]+)"', args)
            entity_match = re.search(r'entity="([^"]+)"', args)
            query_val = None
            if query_match:
                query_val = query_match.group(1)
            elif topic_match:
                query_val = topic_match.group(1)
            elif entity_match:
                query_val = entity_match.group(1)

            defaults = raw_input.get('env', {}).get('defaults', {})
            lang_val = raw_input.get('user_lang', defaults.get('lang', 'auto'))
            window_val = defaults.get('window', '24h')
            k_val = defaults.get('k_final', len(sample_docs))

            return {
                'command': raw_input.get('raw_command'),
                'params': {
                    'query': query_val,
                    'lang': lang_val,
                    'k_final': k_val,
                },
                'retrieval': {
                    'docs': sample_docs,
                    'window': window_val,
                    'lang': lang_val,
                    'sources': None,
                    'k_final': len(sample_docs),
                    'rerank_enabled': True,
                },
                'models': {'primary': 'gpt-5', 'fallback': ['claude-4.5']},
                'limits': {
                    'max_tokens': defaults.get('max_tokens', 8000),
                    'budget_cents': defaults.get('budget_cents', 50),
                    'timeout_s': defaults.get('timeout_s', 30),
                },
                'telemetry': {'correlation_id': raw_input.get('env', {}).get('version', 'phase3-test')},
            }

        builder_instance.build_context = AsyncMock(side_effect=fake_build_context)
        mock_builder.return_value = builder_instance

        retrieval_instance = MagicMock()
        retrieval_instance.retrieve = AsyncMock(return_value=sample_docs)
        mock_retrieval.return_value = retrieval_instance

        phase3_handlers._phase3_handler_instance = None
        try:
            yield builder_instance, retrieval_instance
        finally:
            phase3_handlers._phase3_handler_instance = None


@pytest.mark.asyncio
async def test_ask_command_basic_execution(sample_docs, mock_phase3_builder):
    """Test basic /ask command execution"""
    _, retrieval_instance = mock_phase3_builder

    with patch('services.phase3_handlers.Phase3Orchestrator') as mock_orch:
        mock_instance = MagicMock()
        mock_instance.execute = AsyncMock(return_value={
            "header": "Deep Dive",
            "tldr": "Iterative analysis completed",
            "insights": [
                {
                    "type": "fact",
                    "text": "AI adoption is accelerating",
                    "evidence_refs": [{"article_id": "doc1", "url": None, "date": "2025-01-15"}]
                }
            ],
            "evidence": [
                {
                    "title": "AI Adoption Accelerates",
                    "article_id": "doc1",
                    "url": "https://techcrunch.com/ai-adoption",
                    "date": "2025-01-15",
                    "snippet": "Companies rapidly adopt..."
                }
            ],
            "result": {
                "steps": [
                    {"iteration": 1, "query": "test query", "n_docs": 3, "reason": "Initial retrieval"}
                ],
                "answer": "AI adoption is accelerating across enterprises.",
                "followups": ["Should we dive deeper into metrics?"]
            },
            "meta": {
                "confidence": 0.78,
                "model": "gpt-5",
                "version": "phase3-v1.0",
                "correlation_id": "test-123",
                "iterations": 1
            },
            "warnings": []
        })
        mock_orch.return_value = mock_instance

        phase3_handlers._phase3_handler_instance = None
        result = await execute_ask_command(
            query="How is AI adoption progressing?",
            depth=3,
            window="24h",
            lang="en",
            k_final=5
        )

        assert "text" in result or "header" in result
        assert "context" in result
        assert result["context"]["command"] == "ask"
        assert result["context"]["depth"] == 3

        retrieval_instance.retrieve.assert_called_once()


@pytest.mark.asyncio
async def test_ask_command_with_depth_1(sample_docs):
    """Test /ask command with depth=1 (single iteration)"""
    with patch('services.phase3_handlers.get_retrieval_client') as mock_retrieval:
        mock_client = MagicMock()
        mock_client.retrieve = AsyncMock(return_value=sample_docs)
        mock_retrieval.return_value = mock_client

        with patch('services.phase3_handlers.Phase3Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value={
                "header": "Quick Analysis",
                "tldr": "Single iteration analysis",
                "insights": [],
                "evidence": [],
                "result": {
                    "steps": [{"iteration": 1, "query": "test", "n_docs": 3, "reason": "Initial"}],
                    "answer": "Brief answer",
                    "followups": []
                },
                "meta": {"confidence": 0.7, "model": "gpt-5", "version": "phase3-v1.0", "correlation_id": "test", "iterations": 1},
                "warnings": []
            })
            mock_orch.return_value = mock_instance

            result = await execute_ask_command(
                query="Quick question?",
                depth=1,
                window="24h",
                lang="en",
                k_final=5
            )

            assert result["context"]["depth"] == 1


@pytest.mark.asyncio
async def test_ask_command_with_budget_constraints(sample_docs):
    """Test /ask command with tight budget constraints"""
    with patch('services.phase3_handlers.get_retrieval_client') as mock_retrieval:
        mock_client = MagicMock()
        mock_client.retrieve = AsyncMock(return_value=sample_docs)
        mock_retrieval.return_value = mock_client

        with patch('services.phase3_handlers.Phase3Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value={
                "header": "Analysis",
                "tldr": "Budget-constrained analysis",
                "insights": [],
                "evidence": [],
                "result": {"steps": [], "answer": "answer", "followups": []},
                "meta": {"confidence": 0.6, "model": "gpt-5", "version": "phase3-v1.0", "correlation_id": "test", "iterations": 1},
                "warnings": ["Degraded to 1 iteration due to budget"]
            })
            mock_orch.return_value = mock_instance

            result = await execute_ask_command(
                query="Test query",
                depth=3,
                max_tokens=1000,  # Low tokens
                budget_cents=5,   # Low budget
                timeout_s=10      # Low timeout
            )

            # Should still complete
            assert "context" in result


@pytest.mark.asyncio
async def test_ask_command_no_documents()):
    """Test /ask command when no documents are retrieved"""
    with patch('services.phase3_handlers.get_retrieval_client') as mock_retrieval:
        mock_client = MagicMock()
        mock_client.retrieve = AsyncMock(return_value=[])  # No docs
        mock_retrieval.return_value = mock_client

        with patch('services.phase3_handlers.Phase3Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value={
                "header": "No Data",
                "tldr": "No supporting documents found",
                "insights": [
                    {
                        "type": "fact",
                        "text": "No sources available",
                        "evidence_refs": [{"article_id": None, "url": None, "date": "2025-01-15"}]
                    }
                ],
                "evidence": [],
                "result": {"steps": [], "answer": "No data", "followups": []},
                "meta": {"confidence": 0.0, "model": "gpt-5", "version": "phase3-v1.0", "correlation_id": "test", "iterations": 0},
                "warnings": []
            })
            mock_orch.return_value = mock_instance

            result = await execute_ask_command(
                query="Obscure query with no matches",
                depth=3
            )

            # Should handle gracefully
            assert "context" in result


@pytest.mark.asyncio
async def test_ask_command_error_handling():
    """Test /ask command error handling"""
    with patch('services.phase3_handlers.get_retrieval_client') as mock_retrieval:
        mock_client = MagicMock()
        mock_client.retrieve = AsyncMock(side_effect=Exception("Retrieval failed"))
        mock_retrieval.return_value = mock_client

        result = await execute_ask_command(
            query="Test query",
            depth=3
        )

        # Should return error payload
        assert "text" in result
        assert "Ошибка" in result["text"] or "error" in result["text"].lower()


@pytest.mark.asyncio
async def test_ask_command_context_building(sample_docs):
    """Test that context is properly built for orchestrator"""
    with patch('services.phase3_handlers.get_retrieval_client') as mock_retrieval:
        mock_client = MagicMock()
        mock_client.retrieve = AsyncMock(return_value=sample_docs)
        mock_retrieval.return_value = mock_client

        with patch('services.phase3_handlers.Phase3Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value={
                "header": "Test",
                "tldr": "Test",
                "insights": [],
                "evidence": [],
                "result": {"steps": [], "answer": "test", "followups": []},
                "meta": {"confidence": 0.7, "model": "gpt-5", "version": "phase3-v1.0", "correlation_id": "test", "iterations": 1},
                "warnings": []
            })
            mock_orch.return_value = mock_instance

            await execute_ask_command(
                query="Test query",
                depth=2,
                window="12h",
                lang="ru",
                sources=["techcrunch.com"],
                k_final=10,
                max_tokens=5000,
                budget_cents=30,
                timeout_s=25
            )

            # Verify execute was called with proper context
            call_args = mock_instance.execute.call_args[0][0]
            assert call_args["command"] == "/ask"
            assert call_args["params"]["depth"] == 2
            assert call_args["params"]["lang"] == "ru"
            assert call_args["retrieval"]["window"] == "12h"
            assert call_args["retrieval"]["k_final"] == 10
            assert call_args["limits"]["max_tokens"] == 5000
            assert call_args["limits"]["budget_cents"] == 30
            assert call_args["limits"]["timeout_s"] == 25
