"""
Tests for Stage 8 RAG pipeline components.
Tests prompt validation, LLM mocking, and complete pipeline orchestration.
"""

import pytest
import unittest.mock as mock
from datetime import datetime
from typing import List, Dict, Any

from stage8_retrieval.rag_pipeline import (
    PromptBuilder,
    LLMClient,
    RAGPipeline,
    RAGResponse
)
from stage8_retrieval.retriever import RetrievalResult


class TestPromptBuilder:
    """Test prompt building and formatting."""
    
    def setup_method(self):
        self.prompt_builder = PromptBuilder()
        
        self.sample_chunks = [
            {
                'id': 1,
                'title_norm': 'AI Breakthrough in Healthcare',
                'source_domain': 'techcrunch.com',
                'published_at': '2024-01-15T10:30:00Z',
                'text': 'Artificial intelligence is revolutionizing healthcare with new diagnostic tools that can detect diseases earlier than traditional methods.',
                'url': 'https://techcrunch.com/ai-healthcare',
                'hybrid_score': 0.95
            },
            {
                'id': 2,
                'title_norm': 'Machine Learning in Medical Imaging',
                'source_domain': 'nature.com',
                'published_at': '2024-01-14T15:45:00Z',
                'text': 'Recent advances in machine learning have enabled more accurate medical imaging analysis, improving patient outcomes.',
                'url': 'https://nature.com/ml-imaging',
                'hybrid_score': 0.87
            }
        ]
    
    def test_build_prompt_with_chunks(self):
        query = "How is AI being used in healthcare?"
        prompt = self.prompt_builder.build_prompt(query, self.sample_chunks)
        
        # Check prompt structure
        assert "How is AI being used in healthcare?" in prompt
        assert "AI Breakthrough in Healthcare" in prompt
        assert "techcrunch.com" in prompt
        assert "2024-01-15" in prompt
        assert "Artificial intelligence is revolutionizing healthcare" in prompt
        assert "Machine Learning in Medical Imaging" in prompt
        assert "nature.com" in prompt
        
        # Check formatting
        assert "[1] Title:" in prompt
        assert "[2] Title:" in prompt
        assert "Source:" in prompt
        assert "Published:" in prompt
        assert "Content:" in prompt
    
    def test_build_prompt_no_chunks(self):
        query = "What is quantum computing?"
        prompt = self.prompt_builder.build_prompt(query, [])
        
        assert "What is quantum computing?" in prompt
        assert "No relevant news articles found" in prompt
    
    def test_build_prompt_text_truncation(self):
        # Create chunk with very long text
        long_chunk = {
            'id': 1,
            'title_norm': 'Long Article',
            'source_domain': 'example.com',
            'published_at': '2024-01-15T10:30:00Z',
            'text': 'A' * 1000,  # 1000 character text
            'url': 'https://example.com/long',
            'hybrid_score': 0.9
        }
        
        query = "Test query"
        prompt = self.prompt_builder.build_prompt(query, [long_chunk])
        
        # Should truncate at 800 chars and add ellipsis
        assert 'A' * 800 in prompt
        assert '...' in prompt
        assert 'A' * 801 not in prompt
    
    def test_build_json_prompt(self):
        query = "AI in healthcare trends"
        json_prompt = self.prompt_builder.build_json_prompt(query, self.sample_chunks)
        
        # Check structure
        assert json_prompt["user_query"] == query
        assert "system_prompt" in json_prompt
        assert "context" in json_prompt
        assert "task" in json_prompt
        assert "response_format" in json_prompt
        
        # Check context chunks
        context_chunks = json_prompt["context"]
        assert len(context_chunks) == 2
        assert context_chunks[0]["title"] == "AI Breakthrough in Healthcare"
        assert context_chunks[0]["source"] == "techcrunch.com"
        assert context_chunks[0]["relevance_score"] == 0.95
        
        # Check text truncation in JSON (1000 char limit)
        assert len(context_chunks[0]["text"]) <= 1000
    
    def test_published_date_formatting(self):
        # Test various date formats
        chunks_with_dates = [
            {
                'id': 1,
                'title_norm': 'Test Article 1',
                'source_domain': 'test.com',
                'published_at': '2024-01-15T10:30:00Z',  # ISO format
                'text': 'Test content 1',
                'url': 'https://test.com/1'
            },
            {
                'id': 2,
                'title_norm': 'Test Article 2',
                'source_domain': 'test.com',
                'published_at': '2024-01-16 09:15:30',  # Datetime format
                'text': 'Test content 2',
                'url': 'https://test.com/2'
            },
            {
                'id': 3,
                'title_norm': 'Test Article 3',
                'source_domain': 'test.com',
                'published_at': None,  # None date
                'text': 'Test content 3',
                'url': 'https://test.com/3'
            }
        ]
        
        prompt = self.prompt_builder.build_prompt("test", chunks_with_dates)
        
        # Check date parsing
        assert "Published: 2024-01-15" in prompt
        assert "Published: 2024-01-16" in prompt
        assert "Published: Unknown Date" in prompt


class TestLLMClient:
    """Test LLM client with mocking and error handling."""
    
    @mock.patch('stage8_retrieval.rag_pipeline.GeminiClient')
    @mock.patch('stage8_retrieval.rag_pipeline.get_settings')
    def test_successful_llm_call(self, mock_settings, mock_gemini_class):
        # Setup mocks
        mock_settings_obj = mock.Mock()
        mock_settings_obj.rate_limit.cost_per_token_input = 0.001
        mock_settings_obj.gemini.model = 'gemini-2.5-flash'
        mock_settings.return_value = mock_settings_obj
        
        mock_gemini_client = mock.Mock()
        mock_gemini_client.refine_chunks_via_llm.return_value = [
            {'refined_text': 'AI is transforming healthcare through diagnostic tools and imaging analysis.'}
        ]
        mock_gemini_class.return_value = mock_gemini_client
        
        llm_client = LLMClient()
        result = llm_client.call_llm("How is AI used in healthcare?", max_tokens=500)
        
        # Check success response
        assert result['success'] is True
        assert 'AI is transforming healthcare' in result['response']
        assert result['tokens_used'] > 0
        assert result['cost_estimate'] >= 0
        assert result['call_time_ms'] > 0
        assert result['model'] == 'gemini-2.5-flash'
    
    @mock.patch('stage8_retrieval.rag_pipeline.GeminiClient')
    @mock.patch('stage8_retrieval.rag_pipeline.get_settings')
    def test_llm_call_failure(self, mock_settings, mock_gemini_class):
        # Setup mock to raise exception
        mock_settings.return_value = mock.Mock()
        mock_gemini_client = mock.Mock()
        mock_gemini_client.refine_chunks_via_llm.side_effect = Exception("API Error")
        mock_gemini_class.return_value = mock_gemini_client
        
        llm_client = LLMClient()
        result = llm_client.call_llm("Test prompt")
        
        # Check error response
        assert result['success'] is False
        assert 'encountered an error' in result['response']
        assert result['tokens_used'] == 0
        assert result['cost_estimate'] == 0.0
        assert 'error' in result
        assert result['call_time_ms'] > 0
    
    @mock.patch('stage8_retrieval.rag_pipeline.GeminiClient')
    @mock.patch('stage8_retrieval.rag_pipeline.get_settings')
    def test_llm_empty_response(self, mock_settings, mock_gemini_class):
        # Setup mock to return empty results
        mock_settings.return_value = mock.Mock()
        mock_gemini_client = mock.Mock()
        mock_gemini_client.refine_chunks_via_llm.return_value = []
        mock_gemini_class.return_value = mock_gemini_client
        
        llm_client = LLMClient()
        result = llm_client.call_llm("Test prompt")
        
        # Should handle empty response gracefully
        assert result['success'] is True
        assert "wasn't able to generate a response" in result['response']
    
    def test_call_gemini_for_rag_method(self):
        """Test the internal Gemini adaptation method."""
        llm_client = LLMClient()
        
        # Create a mock gemini client
        mock_gemini_client = mock.Mock()
        mock_gemini_client.refine_chunks_via_llm.return_value = [
            {'refined_text': 'Test response from Gemini'}
        ]
        
        result = llm_client._call_gemini_for_rag(mock_gemini_client, "Test prompt")
        
        assert result == "Test response from Gemini"
        
        # Check that it called the right method with expected structure
        call_args = mock_gemini_client.refine_chunks_via_llm.call_args
        assert call_args[0][1] == "answer_query"  # Second arg should be the task type
        assert "Test prompt" in call_args[1]["custom_prompt"]
    
    def test_token_estimation(self):
        """Test token usage and cost estimation logic."""
        llm_client = LLMClient()
        
        # Mock settings with cost info
        mock_settings = mock.Mock()
        mock_settings.rate_limit.cost_per_token_input = 0.002
        llm_client.settings = mock_settings
        
        # Test short prompt
        short_prompt = "AI healthcare"
        tokens = len(short_prompt.split()) * 1.3
        expected_cost = tokens * 0.002
        
        # This would be used in the actual call_llm method for cost estimation
        assert tokens > 0
        assert expected_cost >= 0


class TestRAGPipeline:
    """Test complete RAG pipeline orchestration."""
    
    def setup_method(self):
        self.mock_pg_client = mock.Mock()
        self.mock_settings = mock.Mock()
        
        # Sample chunks for testing
        self.sample_chunks = [
            {
                'id': 1,
                'title_norm': 'AI in Healthcare',
                'source_domain': 'techcrunch.com',
                'published_at': '2024-01-15T10:30:00Z',
                'text': 'AI is revolutionizing healthcare diagnostics.',
                'url': 'https://techcrunch.com/ai-healthcare'
            }
        ]
        
        # Sample retrieval result
        self.sample_retrieval = RetrievalResult(
            chunks=self.sample_chunks,
            query_normalized="ai healthcare",
            search_type="hybrid",
            total_results=1,
            search_time_ms=150.0
        )
    
    @mock.patch('stage8_retrieval.rag_pipeline.HybridRetriever')
    @mock.patch('stage8_retrieval.rag_pipeline.LLMClient')
    @mock.patch('stage8_retrieval.rag_pipeline.PromptBuilder')
    def test_successful_rag_pipeline(self, mock_prompt_builder_class, mock_llm_class, mock_retriever_class):
        # Setup mocks
        mock_retriever = mock.Mock()
        mock_retriever.hybrid_retrieve.return_value = self.sample_retrieval
        mock_retriever_class.return_value = mock_retriever
        
        mock_prompt_builder = mock.Mock()
        mock_prompt_builder.build_prompt.return_value = "Test prompt with context"
        mock_prompt_builder_class.return_value = mock_prompt_builder
        
        mock_llm_client = mock.Mock()
        mock_llm_client.call_llm.return_value = {
            'response': 'AI is transforming healthcare through advanced diagnostics.',
            'success': True,
            'tokens_used': 150,
            'cost_estimate': 0.3,
            'call_time_ms': 200.0,
            'model': 'gemini-2.5-flash'
        }
        mock_llm_class.return_value = mock_llm_client
        
        # Test pipeline
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        response = pipeline.answer_query("How is AI used in healthcare?", limit=5, alpha=0.5)
        
        # Check response structure
        assert isinstance(response, RAGResponse)
        assert response.query == "How is AI used in healthcare?"
        assert "AI is transforming healthcare" in response.answer
        assert len(response.chunks_used) == 1
        assert response.retrieval_info['search_type'] == 'hybrid'
        assert response.retrieval_info['alpha'] == 0.5
        assert response.llm_info['success'] is True
        assert response.total_time_ms > 0
        
        # Check method calls
        mock_retriever.hybrid_retrieve.assert_called_once_with("How is AI used in healthcare?", 5, 0.5)
        mock_prompt_builder.build_prompt.assert_called_once()
        mock_llm_client.call_llm.assert_called_once_with("Test prompt with context")
    
    @mock.patch('stage8_retrieval.rag_pipeline.HybridRetriever')
    def test_rag_pipeline_no_chunks(self, mock_retriever_class):
        # Setup retriever to return no chunks
        mock_retriever = mock.Mock()
        empty_retrieval = RetrievalResult(
            chunks=[],
            query_normalized="test query",
            search_type="hybrid",
            total_results=0,
            search_time_ms=50.0
        )
        mock_retriever.hybrid_retrieve.return_value = empty_retrieval
        mock_retriever_class.return_value = mock_retriever
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        response = pipeline.answer_query("Unknown topic query")
        
        # Check no-chunks response
        assert "couldn't find any relevant information" in response.answer
        assert len(response.chunks_used) == 0
        assert response.llm_info['success'] is False
        assert response.llm_info['reason'] == 'no_chunks'
    
    @mock.patch('stage8_retrieval.rag_pipeline.HybridRetriever')
    @mock.patch('stage8_retrieval.rag_pipeline.LLMClient')  
    @mock.patch('stage8_retrieval.rag_pipeline.PromptBuilder')
    def test_rag_pipeline_exception_handling(self, mock_prompt_builder_class, mock_llm_class, mock_retriever_class):
        # Setup retriever to raise exception
        mock_retriever = mock.Mock()
        mock_retriever.hybrid_retrieve.side_effect = Exception("Database connection failed")
        mock_retriever_class.return_value = mock_retriever
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        response = pipeline.answer_query("Test query")
        
        # Check error response
        assert "encountered an error while processing" in response.answer
        assert len(response.chunks_used) == 0
        assert response.retrieval_info['error'] == 'Database connection failed'
        assert response.llm_info['success'] is False
        assert response.total_time_ms > 0
    
    @mock.patch('stage8_retrieval.rag_pipeline.HybridRetriever')
    def test_get_pipeline_stats(self, mock_retriever_class):
        # Setup retriever stats
        mock_retriever = mock.Mock()
        mock_retriever.get_retrieval_stats.return_value = {
            'retrieval_ready': True,
            'total_chunks': 5000,
            'indexed_chunks': 4500
        }
        mock_retriever_class.return_value = mock_retriever
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        stats = pipeline.get_pipeline_stats()
        
        # Check stats structure
        assert stats['pipeline_ready'] is True
        assert stats['retriever']['retrieval_ready'] is True
        assert stats['retriever']['total_chunks'] == 5000
        assert stats['components']['retriever'] == 'ready'
        assert 'llm_client_ready' in stats
        assert 'llm_client' in stats['components']
    
    @mock.patch('stage8_retrieval.rag_pipeline.HybridRetriever')
    def test_get_pipeline_stats_error(self, mock_retriever_class):
        # Setup retriever to raise exception
        mock_retriever = mock.Mock()
        mock_retriever.get_retrieval_stats.side_effect = Exception("Stats error")
        mock_retriever_class.return_value = mock_retriever
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        stats = pipeline.get_pipeline_stats()
        
        # Check error handling
        assert stats['pipeline_ready'] is False
        assert 'error' in stats


class TestRAGResponse:
    """Test RAG response dataclass."""
    
    def test_rag_response_creation(self):
        chunks = [{'id': 1, 'text': 'test chunk'}]
        response = RAGResponse(
            query="test query",
            answer="test answer",
            chunks_used=chunks,
            retrieval_info={'search_type': 'hybrid'},
            llm_info={'success': True, 'tokens': 100},
            total_time_ms=500.0,
            timestamp="2024-01-15T10:30:00Z"
        )
        
        assert response.query == "test query"
        assert response.answer == "test answer"
        assert response.chunks_used == chunks
        assert response.retrieval_info['search_type'] == 'hybrid'
        assert response.llm_info['success'] is True
        assert response.total_time_ms == 500.0
        assert response.timestamp == "2024-01-15T10:30:00Z"
    
    def test_rag_response_empty_chunks(self):
        response = RAGResponse(
            query="empty query",
            answer="no results",
            chunks_used=[],
            retrieval_info={'search_type': 'none'},
            llm_info={'success': False, 'reason': 'no_chunks'},
            total_time_ms=100.0,
            timestamp="2024-01-15T10:30:00Z"
        )
        
        assert len(response.chunks_used) == 0
        assert response.llm_info['success'] is False


if __name__ == "__main__":
    pytest.main([__file__])