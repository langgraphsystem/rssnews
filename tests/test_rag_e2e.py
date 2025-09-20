"""
End-to-end tests for Stage 8 RAG functionality.
Tests complete integration with mock DB + LLM, realistic scenarios.
"""

import pytest
import unittest.mock as mock
import os
import tempfile
from typing import Dict, List, Any

from pg_client_new import PgClient
from stage8_retrieval.rag_pipeline import RAGPipeline, RAGResponse
from stage8_retrieval.retriever import HybridRetriever


class MockPgClient:
    """Mock database client for E2E testing."""
    
    def __init__(self):
        self.chunks_data = [
            {
                'id': 1,
                'text': 'OpenAI releases GPT-5 Turbo with improved reasoning capabilities and reduced hallucinations. The new model shows significant improvements in mathematical problem solving.',
                'title_norm': 'OpenAI Releases GPT-5 Turbo',
                'source_domain': 'openai.com',
                'published_at': '2024-01-15T10:00:00Z',
                'url': 'https://openai.com/gpt5-turbo',
                'language': 'en',
                'category': 'technology',
                'tags_norm': ['ai', 'gpt', 'openai'],
                'embedding': [0.1, 0.2, 0.3, 0.4, 0.5]
            },
            {
                'id': 2,
                'text': 'Google announces breakthrough in quantum computing with new error correction techniques. Their quantum processor achieved 99.9% fidelity in quantum operations.',
                'title_norm': 'Google Quantum Computing Breakthrough',
                'source_domain': 'googleblog.com',
                'published_at': '2024-01-14T14:30:00Z',
                'url': 'https://googleblog.com/quantum',
                'language': 'en',
                'category': 'technology',
                'tags_norm': ['quantum', 'google', 'computing'],
                'embedding': [0.2, 0.1, 0.4, 0.3, 0.6]
            },
            {
                'id': 3,
                'text': 'Tesla reports record quarterly deliveries driven by strong demand for Model 3 and Model Y. The company delivered over 400,000 vehicles in Q4.',
                'title_norm': 'Tesla Record Quarterly Deliveries',
                'source_domain': 'tesla.com',
                'published_at': '2024-01-13T09:15:00Z',
                'url': 'https://tesla.com/deliveries-q4',
                'language': 'en',
                'category': 'business',
                'tags_norm': ['tesla', 'deliveries', 'electric'],
                'embedding': [0.3, 0.4, 0.1, 0.2, 0.7]
            },
            {
                'id': 4,
                'text': 'New study shows climate change accelerating with global temperatures rising faster than predicted. Scientists call for immediate action.',
                'title_norm': 'Climate Change Accelerating Study',
                'source_domain': 'nature.com',
                'published_at': '2024-01-12T16:45:00Z',
                'url': 'https://nature.com/climate-study',
                'language': 'en',
                'category': 'science',
                'tags_norm': ['climate', 'environment', 'study'],
                'embedding': [0.4, 0.3, 0.2, 0.5, 0.1]
            }
        ]
        
        self.stats_data = {
            'total_articles': 1000,
            'active_feeds': 50,
            'total_chunks': len(self.chunks_data),
            'indexed_chunks': len([c for c in self.chunks_data if c.get('embedding')])
        }
    
    def search_chunks_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Mock FTS search with simple keyword matching."""
        query_words = query.lower().split()
        results = []
        
        for chunk in self.chunks_data:
            text_lower = chunk['text'].lower()
            title_lower = chunk['title_norm'].lower()
            
            # Simple scoring based on keyword matches
            score = 0.0
            for word in query_words:
                if word in text_lower:
                    score += 0.3
                if word in title_lower:
                    score += 0.5
                if word in chunk.get('tags_norm', []):
                    score += 0.4
            
            if score > 0:
                result = chunk.copy()
                result['fts_score'] = score
                results.append(result)
        
        # Sort by score and limit
        results.sort(key=lambda x: x['fts_score'], reverse=True)
        return results[:limit]
    
    def search_chunks_embedding(self, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """Mock embedding search with cosine similarity."""
        results = []
        
        for chunk in self.chunks_data:
            if not chunk.get('embedding'):
                continue
                
            # Simple cosine similarity simulation
            dot_product = sum(a * b for a, b in zip(query_vector, chunk['embedding']))
            norm_a = sum(a * a for a in query_vector) ** 0.5
            norm_b = sum(b * b for b in chunk['embedding']) ** 0.5
            
            if norm_a > 0 and norm_b > 0:
                similarity = dot_product / (norm_a * norm_b)
                
                result = chunk.copy()
                result['embedding_score'] = similarity
                results.append(result)
        
        # Sort by similarity and limit
        results.sort(key=lambda x: x['embedding_score'], reverse=True)
        return results[:limit]
    
    def hybrid_search(self, query: str, query_vector: List[float], limit: int = 10, alpha: float = 0.5) -> List[Dict[str, Any]]:
        """Mock hybrid search combining FTS and embedding results."""
        fts_results = self.search_chunks_fts(query, limit * 2)  # Get more for merging
        embedding_results = self.search_chunks_embedding(query_vector, limit * 2)
        
        # Normalize scores to 0-1 range
        if fts_results:
            max_fts = max(r['fts_score'] for r in fts_results)
            for r in fts_results:
                r['fts_score_norm'] = r['fts_score'] / max_fts if max_fts > 0 else 0
        
        if embedding_results:
            max_emb = max(r['embedding_score'] for r in embedding_results)
            for r in embedding_results:
                r['embedding_score_norm'] = r['embedding_score'] / max_emb if max_emb > 0 else 0
        
        # Combine and calculate hybrid scores
        chunk_scores = {}
        
        for result in fts_results:
            chunk_id = result['id']
            chunk_scores[chunk_id] = {
                'chunk': result,
                'fts_score': result['fts_score_norm'],
                'embedding_score': 0.0
            }
        
        for result in embedding_results:
            chunk_id = result['id']
            if chunk_id in chunk_scores:
                chunk_scores[chunk_id]['embedding_score'] = result['embedding_score_norm']
            else:
                chunk_scores[chunk_id] = {
                    'chunk': result,
                    'fts_score': 0.0,
                    'embedding_score': result['embedding_score_norm']
                }
        
        # Calculate hybrid scores
        hybrid_results = []
        for chunk_id, scores in chunk_scores.items():
            hybrid_score = alpha * scores['fts_score'] + (1 - alpha) * scores['embedding_score']
            
            result = scores['chunk'].copy()
            result['hybrid_score'] = hybrid_score
            hybrid_results.append(result)
        
        # Sort by hybrid score and limit
        hybrid_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        return hybrid_results[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Return mock database statistics."""
        return self.stats_data.copy()


class TestRAGE2E:
    """End-to-end tests for RAG pipeline."""
    
    def setup_method(self):
        """Set up E2E test environment."""
        self.mock_pg_client = MockPgClient()
        self.mock_settings = mock.Mock()
        
        # Mock Gemini settings
        self.mock_settings.gemini.model = 'gemini-2.5-flash'
        self.mock_settings.gemini.embedding_model = 'text-embedding-004'
        self.mock_settings.rate_limit.cost_per_token_input = 0.001
        self.mock_settings.rate_limit.embedding_daily_cost_limit_usd = 10.0
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    @mock.patch('stage8_retrieval.rag_pipeline.GeminiClient')
    @mock.patch('stage8_retrieval.retriever.get_settings')
    @mock.patch('stage8_retrieval.rag_pipeline.get_settings')
    def test_e2e_ai_query(self, mock_rag_settings, mock_ret_settings, mock_rag_gemini, mock_ret_gemini):
        """Test complete E2E flow for AI-related query."""
        # Setup settings mocks
        mock_rag_settings.return_value = self.mock_settings
        mock_ret_settings.return_value = self.mock_settings
        
        # Setup embedding client mock
        mock_embedding_client = mock.Mock()
        mock_embedding_client.embed_texts.return_value = [[0.15, 0.25, 0.35, 0.45, 0.55]]  # Query embedding
        mock_ret_gemini.return_value = mock_embedding_client
        
        # Setup LLM client mock
        mock_llm_client = mock.Mock()
        mock_llm_client.refine_chunks_via_llm.return_value = [
            {'refined_text': 'Based on the latest developments, AI is advancing rapidly with OpenAI releasing GPT-5 Turbo, which features improved reasoning capabilities and reduced hallucinations. Additionally, Google has made breakthrough advances in quantum computing that could further accelerate AI development.'}
        ]
        mock_rag_gemini.return_value = mock_llm_client
        
        # Create RAG pipeline
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        # Test query
        response = pipeline.answer_query(
            query="What are the latest AI developments?",
            limit=5,
            alpha=0.5  # Balanced hybrid search
        )
        
        # Validate response structure
        assert isinstance(response, RAGResponse)
        assert response.query == "What are the latest AI developments?"
        assert len(response.answer) > 0
        assert "GPT-5 Turbo" in response.answer
        
        # Validate chunks were retrieved
        assert len(response.chunks_used) > 0
        assert any("OpenAI" in chunk.get('text', '') for chunk in response.chunks_used)
        
        # Validate retrieval info
        assert response.retrieval_info['search_type'] == 'hybrid'
        assert response.retrieval_info['alpha'] == 0.5
        assert response.retrieval_info['total_results'] > 0
        assert response.retrieval_info['search_time_ms'] > 0
        
        # Validate LLM info
        assert response.llm_info['success'] is True
        assert response.llm_info['tokens_used'] > 0
        assert response.llm_info['call_time_ms'] > 0
        
        # Validate timing
        assert response.total_time_ms > 0
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    def test_e2e_fts_only_search(self, mock_gemini):
        """Test E2E with FTS-only search (alpha = 1.0)."""
        # Create pipeline with FTS-only
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        # Mock LLM response
        with mock.patch.object(pipeline.llm_client, 'call_llm') as mock_llm:
            mock_llm.return_value = {
                'response': 'Tesla reported record deliveries in Q4, delivering over 400,000 vehicles.',
                'success': True,
                'tokens_used': 100,
                'cost_estimate': 0.1,
                'call_time_ms': 150.0,
                'model': 'gemini-2.5-flash'
            }
            
            response = pipeline.answer_query(
                query="Tesla deliveries",
                limit=3,
                alpha=1.0  # FTS only
            )
            
            # Should use FTS search
            assert response.retrieval_info['search_type'] == 'fts'
            assert len(response.chunks_used) > 0
            assert any("Tesla" in chunk.get('text', '') for chunk in response.chunks_used)
            assert "400,000 vehicles" in response.answer
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    def test_e2e_embedding_only_search(self, mock_gemini):
        """Test E2E with embedding-only search (alpha = 0.0)."""
        # Setup embedding client
        mock_embedding_client = mock.Mock()
        mock_embedding_client.embed_texts.return_value = [[0.25, 0.35, 0.15, 0.25, 0.65]]
        mock_gemini.return_value = mock_embedding_client
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        # Mock LLM response
        with mock.patch.object(pipeline.llm_client, 'call_llm') as mock_llm:
            mock_llm.return_value = {
                'response': 'Climate change is accelerating with global temperatures rising faster than predicted.',
                'success': True,
                'tokens_used': 120,
                'cost_estimate': 0.12,
                'call_time_ms': 180.0,
                'model': 'gemini-2.5-flash'
            }
            
            response = pipeline.answer_query(
                query="environmental climate",
                limit=3,
                alpha=0.0  # Embedding only
            )
            
            # Should use embedding search
            assert response.retrieval_info['search_type'] == 'embedding'
            assert len(response.chunks_used) > 0
            assert "climate" in response.answer.lower()
    
    def test_e2e_no_results_scenario(self):
        """Test E2E when no relevant chunks are found."""
        # Create empty mock client
        empty_client = MockPgClient()
        empty_client.chunks_data = []
        
        pipeline = RAGPipeline(empty_client, self.mock_settings)
        
        response = pipeline.answer_query(
            query="nonexistent topic xyz",
            limit=5,
            alpha=0.5
        )
        
        # Should handle no results gracefully
        assert "couldn't find any relevant information" in response.answer
        assert len(response.chunks_used) == 0
        assert response.llm_info['success'] is False
        assert response.llm_info['reason'] == 'no_chunks'
        assert response.retrieval_info['total_results'] == 0
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    def test_e2e_embedding_fallback(self, mock_gemini):
        """Test E2E when embedding fails and falls back to FTS."""
        # Setup embedding client to fail
        mock_embedding_client = mock.Mock()
        mock_embedding_client.embed_texts.side_effect = Exception("Embedding API Error")
        mock_gemini.return_value = mock_embedding_client
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        # Mock LLM response
        with mock.patch.object(pipeline.llm_client, 'call_llm') as mock_llm:
            mock_llm.return_value = {
                'response': 'Found some information about quantum computing from Google.',
                'success': True,
                'tokens_used': 90,
                'cost_estimate': 0.09,
                'call_time_ms': 120.0,
                'model': 'gemini-2.5-flash'
            }
            
            response = pipeline.answer_query(
                query="quantum computing",
                limit=3,
                alpha=0.5  # Should try hybrid but fallback to FTS
            )
            
            # Should fallback to FTS
            assert response.retrieval_info['search_type'] == 'fts_fallback'
            assert len(response.chunks_used) > 0
            assert any("quantum" in chunk.get('text', '').lower() for chunk in response.chunks_used)
    
    def test_e2e_different_alpha_values(self):
        """Test E2E with different alpha weighting values."""
        with mock.patch('stage8_retrieval.retriever.GeminiClient') as mock_gemini:
            # Setup embedding client
            mock_embedding_client = mock.Mock()
            mock_embedding_client.embed_texts.return_value = [[0.2, 0.3, 0.1, 0.4, 0.5]]
            mock_gemini.return_value = mock_embedding_client
            
            pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
            
            # Mock LLM for consistent responses
            with mock.patch.object(pipeline.llm_client, 'call_llm') as mock_llm:
                mock_llm.return_value = {
                    'response': 'Test response',
                    'success': True,
                    'tokens_used': 50,
                    'cost_estimate': 0.05,
                    'call_time_ms': 100.0,
                    'model': 'gemini-2.5-flash'
                }
                
                # Test different alpha values
                alphas = [0.0, 0.25, 0.5, 0.75, 1.0]
                expected_types = ['embedding', 'hybrid', 'hybrid', 'hybrid', 'fts']
                
                for alpha, expected_type in zip(alphas, expected_types):
                    response = pipeline.answer_query(
                        query="technology news",
                        limit=3,
                        alpha=alpha
                    )
                    
                    assert response.retrieval_info['search_type'] == expected_type
                    assert response.retrieval_info['alpha'] == alpha
    
    def test_e2e_pipeline_stats(self):
        """Test E2E pipeline statistics."""
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        stats = pipeline.get_pipeline_stats()
        
        # Validate stats structure
        assert stats['pipeline_ready'] is True
        assert 'retriever' in stats
        assert stats['retriever']['retrieval_ready'] is True
        assert stats['retriever']['total_chunks'] == 4
        assert stats['retriever']['indexed_chunks'] == 4
        assert 'components' in stats
        assert stats['components']['retriever'] == 'ready'
    
    @mock.patch('stage8_retrieval.retriever.GeminiClient')
    def test_e2e_error_recovery(self, mock_gemini):
        """Test E2E error handling and recovery."""
        # Setup embedding client
        mock_embedding_client = mock.Mock()
        mock_embedding_client.embed_texts.return_value = [[0.1, 0.2, 0.3, 0.4, 0.5]]
        mock_gemini.return_value = mock_embedding_client
        
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        # Mock LLM to fail first time, succeed second time
        with mock.patch.object(pipeline.llm_client, 'call_llm') as mock_llm:
            mock_llm.return_value = {
                'response': 'Sorry, I encountered an error processing your question: Test error',
                'success': False,
                'tokens_used': 0,
                'cost_estimate': 0.0,
                'call_time_ms': 50.0,
                'error': 'Test error'
            }
            
            response = pipeline.answer_query(
                query="test query",
                limit=3,
                alpha=0.5
            )
            
            # Should handle LLM error gracefully
            assert len(response.chunks_used) > 0  # Retrieval should succeed
            assert "encountered an error" in response.answer
            assert response.llm_info['success'] is False
            assert response.llm_info['error'] == 'Test error'
    
    def test_e2e_query_normalization_effects(self):
        """Test E2E with various query formats to verify normalization."""
        pipeline = RAGPipeline(self.mock_pg_client, self.mock_settings)
        
        with mock.patch.object(pipeline.llm_client, 'call_llm') as mock_llm:
            mock_llm.return_value = {
                'response': 'Normalized query response',
                'success': True,
                'tokens_used': 75,
                'cost_estimate': 0.075,
                'call_time_ms': 125.0,
                'model': 'gemini-2.5-flash'
            }
            
            # Test various query formats
            queries = [
                "What is the latest AI news?",
                "WHAT IS THE LATEST AI NEWS?",
                "  what   is   the   latest   ai   news?  ",
                "What's the latest AI news!!!",
                "ai news"
            ]
            
            for query in queries:
                response = pipeline.answer_query(query, limit=3, alpha=1.0)  # FTS only for consistency
                
                # All should find AI-related content
                assert len(response.chunks_used) > 0
                assert response.retrieval_info['query_normalized'] == "latest ai news"
                assert response.retrieval_info['search_type'] == 'fts'


if __name__ == "__main__":
    pytest.main([__file__])
