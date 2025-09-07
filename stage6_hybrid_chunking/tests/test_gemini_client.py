"""
Tests for Gemini API client functionality.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import json
from datetime import datetime, timedelta

from src.llm.gemini_client import (
    GeminiClient, LLMRefinementResult, GeminiRequest, GeminiResponse,
    CircuitBreaker, RateLimiter, APIErrorType, CircuitState
)
from tests.conftest import create_test_article_metadata


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initializes correctly."""
        cb = CircuitBreaker(threshold=3, timeout=60)
        
        assert cb.threshold == 3
        assert cb.timeout == 60
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() == True
    
    def test_circuit_breaker_failure_counting(self):
        """Test failure counting and state transitions."""
        cb = CircuitBreaker(threshold=2, timeout=5)
        
        # Initially closed
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() == True
        
        # First failure
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() == True
        
        # Second failure - should open
        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() == False
    
    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        cb = CircuitBreaker(threshold=1, timeout=1)  # 1 second timeout
        
        # Trigger failure
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() == False
        
        # Wait for timeout (simulate)
        import time
        cb.last_failure_time = datetime.utcnow() - timedelta(seconds=2)
        
        # Should transition to half-open
        assert cb.can_execute() == True
        assert cb.state == CircuitState.HALF_OPEN
        
        # Success should close it
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


class TestRateLimiter:
    """Test rate limiter functionality."""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes correctly."""
        rl = RateLimiter(max_calls=10, window_seconds=60)
        
        assert rl.max_calls == 10
        assert rl.window_seconds == 60
        assert len(rl.calls) == 0
        assert rl.can_execute() == True
    
    def test_rate_limiting_enforcement(self):
        """Test rate limiting enforcement."""
        rl = RateLimiter(max_calls=2, window_seconds=60)
        
        # First call
        assert rl.can_execute() == True
        rl.record_call()
        
        # Second call
        assert rl.can_execute() == True
        rl.record_call()
        
        # Third call - should be blocked
        assert rl.can_execute() == False
        
        # Wait time should be positive
        wait_time = rl.get_wait_time()
        assert wait_time > 0
    
    def test_rate_limiter_window_sliding(self):
        """Test sliding window behavior."""
        rl = RateLimiter(max_calls=1, window_seconds=1)
        
        # Make a call
        rl.record_call()
        assert rl.can_execute() == False
        
        # Simulate time passing
        old_time = datetime.utcnow() - timedelta(seconds=2)
        rl.calls = [old_time]
        
        # Should allow new calls after window
        assert rl.can_execute() == True


class TestGeminiClient:
    """Test Gemini API client functionality."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        mock_client = AsyncMock()
        return mock_client
    
    @pytest.fixture
    def gemini_client(self, test_settings, mock_http_client):
        """Create GeminiClient with mocked HTTP client."""
        client = GeminiClient(test_settings)
        client.client = mock_http_client
        return client
    
    def test_client_initialization(self, test_settings):
        """Test client initializes correctly."""
        client = GeminiClient(test_settings)
        
        assert client.api_key == test_settings.gemini.api_key.get_secret_value()
        assert client.model == test_settings.gemini.model
        assert client.max_retries == test_settings.gemini.max_retries
        assert client.total_requests == 0
        assert client.total_tokens == 0
    
    @pytest.mark.asyncio
    async def test_successful_chunk_refinement(self, gemini_client, mock_http_client):
        """Test successful chunk refinement."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "action": "keep",
                            "offset_adjust": 0,
                            "semantic_type": "body",
                            "confidence": 0.8,
                            "reason": "Chunk is well-formed"
                        })
                    }]
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        
        # Test refinement
        chunk_text = "This is a test chunk for refinement."
        chunk_metadata = {"index": 0, "word_count": 8}
        article_metadata = create_test_article_metadata()
        
        result = await gemini_client.refine_chunk(
            chunk_text, chunk_metadata, article_metadata
        )
        
        assert result is not None
        assert isinstance(result, LLMRefinementResult)
        assert result.action == "keep"
        assert result.confidence == 0.8
        assert result.reason == "Chunk is well-formed"
        
        # Verify API was called
        mock_http_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_requests(self, gemini_client):
        """Test circuit breaker prevents requests when open."""
        # Force circuit breaker open
        gemini_client.circuit_breaker.state = CircuitState.OPEN
        
        chunk_text = "Test chunk"
        chunk_metadata = {"index": 0, "word_count": 2}
        article_metadata = create_test_article_metadata()
        
        result = await gemini_client.refine_chunk(
            chunk_text, chunk_metadata, article_metadata
        )
        
        # Should return None when circuit breaker is open
        assert result is None
    
    @pytest.mark.asyncio
    async def test_rate_limiting_prevents_requests(self, gemini_client):
        """Test rate limiting prevents requests."""
        # Force rate limiter to block
        for _ in range(gemini_client.rate_limiter.max_calls + 1):
            gemini_client.rate_limiter.record_call()
        
        chunk_text = "Test chunk"
        chunk_metadata = {"index": 0, "word_count": 2}
        article_metadata = create_test_article_metadata()
        
        result = await gemini_client.refine_chunk(
            chunk_text, chunk_metadata, article_metadata
        )
        
        # Should return None when rate limited (with high wait time)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, gemini_client, mock_http_client):
        """Test API error handling and classification."""
        # Test different error types
        error_scenarios = [
            (429, "Rate limit exceeded", APIErrorType.RATE_LIMIT),
            (401, "Authentication failed", APIErrorType.AUTHENTICATION),
            (500, "Internal server error", APIErrorType.SERVER_ERROR),
            (400, "Bad request", APIErrorType.INVALID_REQUEST)
        ]
        
        for status_code, error_message, expected_type in error_scenarios:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.text = error_message
            mock_response.raise_for_status.side_effect = Exception(f"{status_code}: {error_message}")
            mock_http_client.post.return_value = mock_response
            
            chunk_text = "Test chunk"
            chunk_metadata = {"index": 0, "word_count": 2}
            article_metadata = create_test_article_metadata()
            
            result = await gemini_client.refine_chunk(
                chunk_text, chunk_metadata, article_metadata
            )
            
            # Should return None on error
            assert result is None
            
            # Check error classification
            error_type = gemini_client._classify_error(
                Exception(f"{status_code}: {error_message}")
            )
            assert error_type == expected_type
    
    @pytest.mark.asyncio
    async def test_retry_logic(self, gemini_client, mock_http_client):
        """Test retry logic with exponential backoff."""
        # Mock responses: fail twice, then succeed
        responses = []
        
        # First two calls fail
        for _ in range(2):
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Server error"
            mock_response.raise_for_status.side_effect = Exception("Server error")
            responses.append(mock_response)
        
        # Third call succeeds
        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "action": "keep",
                            "offset_adjust": 0,
                            "semantic_type": "body", 
                            "confidence": 0.8,
                            "reason": "Success after retries"
                        })
                    }]
                }
            }]
        }
        mock_success_response.raise_for_status = MagicMock()
        responses.append(mock_success_response)
        
        mock_http_client.post.side_effect = responses
        
        chunk_text = "Test chunk"
        chunk_metadata = {"index": 0, "word_count": 2}
        article_metadata = create_test_article_metadata()
        
        result = await gemini_client.refine_chunk(
            chunk_text, chunk_metadata, article_metadata
        )
        
        # Should succeed after retries
        assert result is not None
        assert result.reason == "Success after retries"
        
        # Should have made 3 calls (2 failures + 1 success)
        assert mock_http_client.post.call_count == 3
    
    @pytest.mark.asyncio
    async def test_response_validation(self, gemini_client, mock_http_client):
        """Test response validation and error handling."""
        # Test invalid JSON response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "invalid json {"
                    }]
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        
        chunk_text = "Test chunk"
        chunk_metadata = {"index": 0, "word_count": 2}
        article_metadata = create_test_article_metadata()
        
        result = await gemini_client.refine_chunk(
            chunk_text, chunk_metadata, article_metadata
        )
        
        # Should return None for invalid JSON
        assert result is None
    
    @pytest.mark.asyncio
    async def test_response_field_validation(self, gemini_client, mock_http_client):
        """Test validation of response fields."""
        # Test response with invalid field values
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "action": "invalid_action",  # Invalid action
                            "offset_adjust": 200,  # Out of range
                            "semantic_type": "invalid_type",  # Invalid type
                            "confidence": 1.5,  # Out of range
                            "reason": "Test response"
                        })
                    }]
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        
        chunk_text = "Test chunk"
        chunk_metadata = {"index": 0, "word_count": 2}
        article_metadata = create_test_article_metadata()
        
        result = await gemini_client.refine_chunk(
            chunk_text, chunk_metadata, article_metadata
        )
        
        # Should return None for invalid fields
        assert result is None
    
    @pytest.mark.asyncio 
    async def test_health_check(self, gemini_client, mock_http_client):
        """Test health check functionality."""
        # Mock successful health check response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"status": "healthy"}'
                    }]
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response
        
        is_healthy = await gemini_client.health_check()
        assert is_healthy == True
        
        # Test failed health check
        mock_response.raise_for_status.side_effect = Exception("Health check failed")
        is_healthy = await gemini_client.health_check()
        assert is_healthy == False
    
    def test_get_stats(self, gemini_client):
        """Test statistics retrieval."""
        # Set some values
        gemini_client.total_requests = 10
        gemini_client.total_tokens = 1000
        gemini_client.total_cost = 5.50
        
        stats = gemini_client.get_stats()
        
        assert stats['total_requests'] == 10
        assert stats['total_tokens'] == 1000
        assert stats['estimated_cost_usd'] == 5.50
        assert 'circuit_breaker_state' in stats
        assert 'circuit_breaker_failures' in stats
        assert 'rate_limiter_calls_window' in stats
    
    @pytest.mark.asyncio
    async def test_client_cleanup(self, gemini_client):
        """Test proper client cleanup."""
        await gemini_client.close()
        
        # Verify HTTP client was closed
        gemini_client.client.aclose.assert_called_once()


class TestLLMRefinementResult:
    """Test LLM refinement result validation."""
    
    def test_valid_refinement_result(self):
        """Test valid refinement result creation."""
        result = LLMRefinementResult(
            action="keep",
            offset_adjust=10,
            semantic_type="body",
            confidence=0.8,
            reason="Test reason"
        )
        
        assert result.action == "keep"
        assert result.offset_adjust == 10
        assert result.semantic_type == "body"
        assert result.confidence == 0.8
        assert result.reason == "Test reason"
    
    def test_default_values(self):
        """Test default values for optional fields."""
        result = LLMRefinementResult(action="merge_prev")
        
        assert result.action == "merge_prev"
        assert result.offset_adjust == 0
        assert result.semantic_type == "body"
        assert result.confidence == 0.5
        assert result.reason == ""
    
    def test_invalid_fields_rejected(self):
        """Test that invalid fields are rejected."""
        with pytest.raises(Exception):
            # Should reject unknown fields due to Config.extra = "forbid"
            LLMRefinementResult(
                action="keep",
                invalid_field="should_fail"
            )


class TestGeminiRequest:
    """Test Gemini request objects."""
    
    def test_request_creation(self):
        """Test request object creation."""
        request = GeminiRequest(
            request_id="test_123",
            prompt="Test prompt",
            chunk_metadata={"index": 0}
        )
        
        assert request.request_id == "test_123"
        assert request.prompt == "Test prompt"
        assert request.chunk_metadata == {"index": 0}
        assert request.retry_count == 0
        assert isinstance(request.created_at, datetime)
    
    def test_token_estimation(self):
        """Test token count estimation."""
        request = GeminiRequest(
            request_id="test",
            prompt="This is a test prompt with some words",
            chunk_metadata={}
        )
        
        # Should estimate roughly prompt length / 4
        estimated = request.estimated_tokens
        assert estimated > 0
        assert estimated < len(request.prompt)  # Should be less than character count


class TestGeminiResponse:
    """Test Gemini response objects."""
    
    def test_successful_response(self):
        """Test successful response creation."""
        response = GeminiResponse(
            request_id="test_123",
            success=True,
            response_data={"action": "keep"},
            tokens_used=50,
            latency_ms=250.5
        )
        
        assert response.request_id == "test_123"
        assert response.success == True
        assert response.response_data == {"action": "keep"}
        assert response.tokens_used == 50
        assert response.latency_ms == 250.5
        assert response.error_type is None
    
    def test_error_response(self):
        """Test error response creation."""
        response = GeminiResponse(
            request_id="test_456",
            success=False,
            error_type=APIErrorType.RATE_LIMIT,
            error_message="Rate limit exceeded",
            latency_ms=100.0
        )
        
        assert response.request_id == "test_456"
        assert response.success == False
        assert response.error_type == APIErrorType.RATE_LIMIT
        assert response.error_message == "Rate limit exceeded"
        assert response.response_data is None