"""
Tests for Stage 8 retrieval components.
Tests hybrid search, alpha weighting, edge cases.
"""

import pytest
import unittest.mock as mock
from typing import List, Dict, Any

from stage8_retrieval.retriever import (
    QueryNormalizer, 
    EmbeddingClient, 
    HybridRetriever,
    RetrievalResult
)


class TestQueryNormalizer:
    """Test query normalization and preprocessing."""
    
    def test_basic_normalization(self):
        normalizer = QueryNormalizer()
        
        # Basic case
        result = normalizer.normalize_query("What is AI technology?")
        assert result == "ai technology"
        
        # Case insensitive
        result = normalizer.normalize_query("MACHINE LEARNING")
        assert result == "machine learning"
        
        # Extra whitespace
        result = normalizer.normalize_query("  deep    learning   models  ")
        assert result == "deep learning models"
    
    def test_stop_word_removal(self):
        normalizer = QueryNormalizer()
        
        # Stop words removed
        result = normalizer.normalize_query("what is the best way to learn")
        assert result == "best way learn"
        
        # Articles and common words
        result = normalizer.normalize_query("a quick brown fox")
        assert result == "quick brown fox"
    
    def test_special_character_handling(self):
        normalizer = QueryNormalizer()
        
        # Special characters
        result = normalizer.normalize_query("AI & ML technologies!")
        assert result == "ai ml technologies"
        
        # Preserve hyphens and apostrophes
        result = normalizer.normalize_query("state-of-the-art AI models")
        assert result == "state-of-the-art ai models"
        
        # Handle apostrophes
        result = normalizer.normalize_query("OpenAI's GPT models")
        assert result == "openai's gpt models"
    
    def test_edge_cases(self):
        normalizer = QueryNormalizer()
        
        # Empty query
        assert normalizer.normalize_query("") == ""
        assert normalizer.normalize_query("   ") == ""
        
        # Only stop words
        result = normalizer.normalize_query("the and of")
        assert result == "the and of"  # Returns original when all filtered
        
        # Very short words
        result = normalizer.normalize_query("a b c python")
        assert result == "python"
        
        # Non-ASCII characters
        result = normalizer.normalize_query("café résumé naïve")
        assert result == "caf r sum na ve"


class TestEmbeddingClient:
    """Test embedding generation via Gemini API."""
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    @mock.patch('stage8_retrieval.retriever.get_settings')
    def test_successful_embedding(self, mock_settings, mock_gemini_class):
        # Mock setup
        mock_client = mock.Mock()
        mock_client.embed_texts.return_value = [[0.1, 0.2, 0.3, 0.4]]
        mock_gemini_class.return_value = mock_client
        mock_settings.return_value = mock.Mock()
        
        embedding_client = EmbeddingClient()
        result = embedding_client.get_query_embedding("test query")
        
        assert result == [0.1, 0.2, 0.3, 0.4]
        mock_client.embed_texts.assert_called_once_with(["test query"])
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    @mock.patch('stage8_retrieval.retriever.get_settings')
    def test_empty_embedding_response(self, mock_settings, mock_gemini_class):
        # Mock empty response
        mock_client = mock.Mock()
        mock_client.embed_texts.return_value = []
        mock_gemini_class.return_value = mock_client
        mock_settings.return_value = mock.Mock()
        
        embedding_client = EmbeddingClient()
        result = embedding_client.get_query_embedding("test query")
        
        assert result is None
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    @mock.patch('stage8_retrieval.retriever.get_settings')
    def test_embedding_api_error(self, mock_settings, mock_gemini_class):
        # Mock API error
        mock_client = mock.Mock()
        mock_client.embed_texts.side_effect = Exception("API Error")
        mock_gemini_class.return_value = mock_client
        mock_settings.return_value = mock.Mock()
        
        embedding_client = EmbeddingClient()
        result = embedding_client.get_query_embedding("test query")
        
        assert result is None
    
    def test_empty_query(self):
        embedding_client = EmbeddingClient()
        
        assert embedding_client.get_query_embedding("") is None
        assert embedding_client.get_query_embedding("   ") is None
        assert embedding_client.get_query_embedding(None) is None


class TestHybridRetriever:
    """Test hybrid search orchestration and alpha weighting."""
    
    def setup_method(self):
        """Set up mock clients for each test."""
        self.mock_pg_client = mock.Mock()
        self.mock_settings = mock.Mock()
        
        # Mock chunks for different search types
        self.fts_chunks = [
            {'id': 1, 'text': 'FTS result 1', 'fts_score': 0.9},
            {'id': 2, 'text': 'FTS result 2', 'fts_score': 0.7}
        ]
        
        self.embedding_chunks = [
            {'id': 3, 'text': 'Embedding result 1', 'embedding_score': 0.95},
            {'id': 4, 'text': 'Embedding result 2', 'embedding_score': 0.8}
        ]
        
        self.hybrid_chunks = [
            {'id': 5, 'text': 'Hybrid result 1', 'hybrid_score': 0.85},
            {'id': 6, 'text': 'Hybrid result 2', 'hybrid_score': 0.75}
        ]
    
    @mock.patch('stage8_retrieval.retriever.EmbeddingClient')
    def test_fts_only_search(self, mock_embedding_class):
        # Setup alpha = 1.0 (FTS only)
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.search_chunks_fts.return_value = self.fts_chunks
        
        result = retriever.hybrid_retrieve("test query", limit=5, alpha=1.0)
        
        assert result.search_type == "fts"
        assert result.chunks == self.fts_chunks
        assert result.total_results == 2
        assert result.query_normalized == "test query"
        self.mock_pg_client.search_chunks_fts.assert_called_once_with("test query", 5)
    
    @mock.patch('stage8_retrieval.retriever.EmbeddingClient')
    def test_embedding_only_search(self, mock_embedding_class):
        # Setup alpha = 0.0 (embedding only)
        mock_embedding_client = mock.Mock()
        mock_embedding_client.get_query_embedding.return_value = [0.1, 0.2, 0.3]
        mock_embedding_class.return_value = mock_embedding_client
        
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.search_chunks_embedding.return_value = self.embedding_chunks
        
        result = retriever.hybrid_retrieve("test query", limit=5, alpha=0.0)
        
        assert result.search_type == "embedding"
        assert result.chunks == self.embedding_chunks
        assert result.total_results == 2
        self.mock_pg_client.search_chunks_embedding.assert_called_once_with([0.1, 0.2, 0.3], 5)
    
    @mock.patch('stage8_retrieval.retriever.EmbeddingClient')
    def test_hybrid_search(self, mock_embedding_class):
        # Setup alpha = 0.5 (hybrid)
        mock_embedding_client = mock.Mock()
        mock_embedding_client.get_query_embedding.return_value = [0.1, 0.2, 0.3]
        mock_embedding_class.return_value = mock_embedding_client
        
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.hybrid_search.return_value = self.hybrid_chunks
        
        result = retriever.hybrid_retrieve("test query", limit=5, alpha=0.5)
        
        assert result.search_type == "hybrid"
        assert result.chunks == self.hybrid_chunks
        assert result.total_results == 2
        self.mock_pg_client.hybrid_search.assert_called_once_with(
            "test query", [0.1, 0.2, 0.3], 5, 0.5
        )
    
    @mock.patch('stage8_retrieval.retriever.EmbeddingClient')
    def test_embedding_fallback_to_fts(self, mock_embedding_class):
        # Test embedding failure fallback
        mock_embedding_client = mock.Mock()
        mock_embedding_client.get_query_embedding.return_value = None  # Embedding fails
        mock_embedding_class.return_value = mock_embedding_client
        
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.search_chunks_fts.return_value = self.fts_chunks
        
        # Test embedding-only fallback
        result = retriever.hybrid_retrieve("test query", limit=5, alpha=0.0)
        
        assert result.search_type == "fts_fallback"
        assert result.chunks == self.fts_chunks
        self.mock_pg_client.search_chunks_fts.assert_called_once_with("test query", 5)
    
    @mock.patch('stage8_retrieval.retriever.EmbeddingClient')
    def test_hybrid_fallback_to_fts(self, mock_embedding_class):
        # Test hybrid mode embedding failure fallback
        mock_embedding_client = mock.Mock()
        mock_embedding_client.get_query_embedding.return_value = None
        mock_embedding_class.return_value = mock_embedding_client
        
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.search_chunks_fts.return_value = self.fts_chunks
        
        # Test hybrid fallback
        result = retriever.hybrid_retrieve("test query", limit=5, alpha=0.5)
        
        assert result.search_type == "fts_fallback"
        assert result.chunks == self.fts_chunks
    
    def test_empty_query_after_normalization(self):
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        
        # Mock normalizer to return empty string
        with mock.patch.object(retriever.query_normalizer, 'normalize_query', return_value=""):
            result = retriever.hybrid_retrieve("   ", limit=5, alpha=0.5)
            
            assert result.search_type == "none"
            assert result.chunks == []
            assert result.total_results == 0
            assert result.query_normalized == ""
    
    @mock.patch('stage8_retrieval.retriever.EmbeddingClient')
    def test_search_exception_handling(self, mock_embedding_class):
        # Test database exception handling
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.search_chunks_fts.side_effect = Exception("Database error")
        
        result = retriever.hybrid_retrieve("test query", limit=5, alpha=1.0)
        
        assert result.search_type == "error"
        assert result.chunks == []
        assert result.total_results == 0
        assert "test query" in result.query_normalized
    
    def test_alpha_weighting_boundaries(self):
        """Test alpha values at boundaries and beyond."""
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.search_chunks_fts.return_value = self.fts_chunks
        
        # Test alpha > 1.0
        result = retriever.hybrid_retrieve("test", alpha=1.5)
        assert result.search_type == "fts"
        
        # Test alpha < 0.0
        with mock.patch.object(retriever.embedding_client, 'get_query_embedding', return_value=None):
            result = retriever.hybrid_retrieve("test", alpha=-0.5)
            assert result.search_type == "fts_fallback"
        
        # Test alpha exactly 1.0
        result = retriever.hybrid_retrieve("test", alpha=1.0)
        assert result.search_type == "fts"
        
        # Test alpha exactly 0.0
        with mock.patch.object(retriever.embedding_client, 'get_query_embedding', return_value=None):
            result = retriever.hybrid_retrieve("test", alpha=0.0)
            assert result.search_type == "fts_fallback"
    
    def test_get_retrieval_stats(self):
        """Test retrieval statistics gathering."""
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        
        # Mock successful stats
        self.mock_pg_client.get_stats.return_value = {
            'total_chunks': 1000,
            'indexed_chunks': 800
        }
        
        stats = retriever.get_retrieval_stats()
        
        assert stats['retrieval_ready'] is True
        assert stats['total_chunks'] == 1000
        assert stats['indexed_chunks'] == 800
        assert 'embedding_client_ready' in stats
    
    def test_get_retrieval_stats_error(self):
        """Test retrieval stats error handling."""
        retriever = HybridRetriever(self.mock_pg_client, self.mock_settings)
        self.mock_pg_client.get_stats.side_effect = Exception("Database error")
        
        stats = retriever.get_retrieval_stats()
        
        assert stats['retrieval_ready'] is False
        assert 'error' in stats


class TestRetrievalResult:
    """Test RetrievalResult dataclass."""
    
    def test_retrieval_result_creation(self):
        chunks = [{'id': 1, 'text': 'test'}]
        result = RetrievalResult(
            chunks=chunks,
            query_normalized="test query",
            search_type="hybrid",
            total_results=1,
            search_time_ms=150.5
        )
        
        assert result.chunks == chunks
        assert result.query_normalized == "test query"
        assert result.search_type == "hybrid"
        assert result.total_results == 1
        assert result.search_time_ms == 150.5
    
    def test_empty_retrieval_result(self):
        result = RetrievalResult(
            chunks=[],
            query_normalized="",
            search_type="none",
            total_results=0,
            search_time_ms=0.0
        )
        
        assert result.chunks == []
        assert result.total_results == 0
        assert result.search_type == "none"


if __name__ == "__main__":
    pytest.main([__file__])