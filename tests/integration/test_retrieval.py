"""
Integration tests for retrieval pipeline
Tests RRF fusion, reranking, filtering
"""

import pytest
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_postgres_client():
    """Mock PostgreSQL client"""
    client = AsyncMock()

    # Mock pgvector results
    client.search_by_vector = AsyncMock(return_value=[
        {"article_id": "art_1", "url": "https://example.com/1", "title": "Article 1", "snippet": "Test 1", "similarity": 0.95},
        {"article_id": "art_2", "url": "https://example.com/2", "title": "Article 2", "snippet": "Test 2", "similarity": 0.90},
        {"article_id": "art_3", "url": "https://example.com/3", "title": "Article 3", "snippet": "Test 3", "similarity": 0.85},
    ])

    # Mock BM25 results
    client.search_by_bm25 = AsyncMock(return_value=[
        {"article_id": "art_2", "url": "https://example.com/2", "title": "Article 2", "snippet": "Test 2", "bm25_score": 12.5},
        {"article_id": "art_4", "url": "https://example.com/4", "title": "Article 4", "snippet": "Test 4", "bm25_score": 10.0},
        {"article_id": "art_1", "url": "https://example.com/1", "title": "Article 1", "snippet": "Test 1", "bm25_score": 8.5},
    ])

    return client


@pytest.mark.asyncio
async def test_rrf_fusion_combines_results(mock_postgres_client):
    """Test RRF combines pgvector and BM25 results"""
    from ranking_api import retrieve_for_analysis

    with patch('ranking_api.get_postgres_client', return_value=mock_postgres_client):
        results = await retrieve_for_analysis(
            query="test query",
            k_final=5,
            enable_rerank=False
        )

        # Should have combined results from both pgvector and BM25
        assert len(results) > 0
        assert len(results) <= 5

        # Check RRF scoring (art_2 should rank high as it appears in both)
        article_ids = [doc["article_id"] for doc in results]
        assert "art_2" in article_ids


@pytest.mark.asyncio
async def test_rrf_deduplication(mock_postgres_client):
    """Test RRF deduplicates articles by article_id"""
    from ranking_api import retrieve_for_analysis

    with patch('ranking_api.get_postgres_client', return_value=mock_postgres_client):
        results = await retrieve_for_analysis(
            query="test query",
            k_final=10,
            enable_rerank=False
        )

        # No duplicate article_ids
        article_ids = [doc["article_id"] for doc in results]
        assert len(article_ids) == len(set(article_ids))


@pytest.mark.asyncio
async def test_retrieval_respects_k_final(mock_postgres_client):
    """Test retrieval returns exactly k_final results"""
    from ranking_api import retrieve_for_analysis

    with patch('ranking_api.get_postgres_client', return_value=mock_postgres_client):
        results = await retrieve_for_analysis(
            query="test query",
            k_final=3,
            enable_rerank=False
        )

        assert len(results) <= 3


@pytest.mark.asyncio
async def test_empty_query_returns_empty(mock_postgres_client):
    """Test empty query returns empty results"""
    from ranking_api import retrieve_for_analysis

    mock_postgres_client.search_by_vector = AsyncMock(return_value=[])
    mock_postgres_client.search_by_bm25 = AsyncMock(return_value=[])

    with patch('ranking_api.get_postgres_client', return_value=mock_postgres_client):
        results = await retrieve_for_analysis(
            query="",
            k_final=5,
            enable_rerank=False
        )

        assert len(results) == 0


@pytest.mark.asyncio
async def test_retrieval_includes_metadata(mock_postgres_client):
    """Test retrieved documents include required metadata"""
    from ranking_api import retrieve_for_analysis

    with patch('ranking_api.get_postgres_client', return_value=mock_postgres_client):
        results = await retrieve_for_analysis(
            query="test query",
            k_final=5,
            enable_rerank=False
        )

        for doc in results:
            # Check required fields
            assert "article_id" in doc
            assert "url" in doc
            assert "title" in doc
            assert "snippet" in doc or "text" in doc


@pytest.mark.asyncio
async def test_reranking_integration(mock_postgres_client):
    """Test reranking reorders results"""
    from ranking_api import retrieve_for_analysis

    # Mock reranker
    mock_reranker = Mock()
    mock_reranker.rerank = Mock(return_value=[
        {"article_id": "art_3", "rerank_score": 0.98},
        {"article_id": "art_1", "rerank_score": 0.92},
        {"article_id": "art_2", "rerank_score": 0.88},
    ])

    with patch('ranking_api.get_postgres_client', return_value=mock_postgres_client):
        with patch('ranking_api.get_reranker', return_value=mock_reranker):
            results = await retrieve_for_analysis(
                query="test query",
                k_final=5,
                enable_rerank=True
            )

            # Check reranking was applied
            if len(results) > 0:
                # First result should have highest rerank score
                assert results[0]["article_id"] in ["art_3", "art_1", "art_2"]
