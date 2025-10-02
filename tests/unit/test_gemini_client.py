"""
Unit tests for core/ai_models/clients/gemini_client.py
Tests Gemini API client, timeout, retry, cost tracking
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from core.ai_models.clients.gemini_client import GeminiClient, create_gemini_client


class TestGeminiClient:
    """Test GeminiClient class"""

    @pytest.fixture
    def client(self):
        """Create GeminiClient instance"""
        return GeminiClient(
            api_key="test-api-key",
            model="gemini-2.5-pro-latest",
            timeout=10,
            max_retries=2
        )

    def test_initialization(self, client):
        """Test client initialization"""
        assert client.api_key == "test-api-key"
        assert client.model == "gemini-2.5-pro-latest"
        assert client.timeout == 10
        assert client.max_retries == 2
        assert client._total_requests == 0

    def test_initialization_without_api_key(self):
        """Test initialization fails without API key"""
        with pytest.raises(ValueError, match="API key is required"):
            GeminiClient(api_key="")

    @pytest.mark.asyncio
    async def test_successful_api_call(self, client):
        """Test successful API call"""
        mock_response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Generated text response"}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50
            }
        }

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response_data

            result = await client.generate_text(
                prompt="Test prompt",
                max_tokens=500,
                temperature=0.7
            )

            assert result == "Generated text response"
            assert client._total_requests == 1
            assert client._total_tokens_in == 100
            assert client._total_tokens_out == 50

    @pytest.mark.asyncio
    async def test_timeout_with_retry(self, client):
        """Test timeout triggers retry logic"""
        mock_response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Success after retry"}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50
            }
        }

        call_count = 0

        async def mock_request_with_timeout(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return mock_response_data

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = mock_request_with_timeout

            result = await client.generate_text(
                prompt="Test prompt",
                max_tokens=500
            )

            assert result == "Success after retry"
            assert call_count == 2  # First failed, second succeeded

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, client):
        """Test max retries exceeded raises exception"""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = asyncio.TimeoutError()

            with pytest.raises(Exception, match="timeout after"):
                await client.generate_text(
                    prompt="Test prompt",
                    max_tokens=500
                )

    @pytest.mark.asyncio
    async def test_api_error_response(self, client):
        """Test API error response handling"""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("API Error: 429 Rate Limit")

            with pytest.raises(Exception, match="API Error: 429"):
                await client.generate_text(
                    prompt="Test prompt",
                    max_tokens=500
                )

    def test_cost_calculation(self, client):
        """Test cost calculation"""
        cost = client._calculate_cost(tokens_in=1000, tokens_out=500)

        # Expected: (1000/1000 * 0.125) + (500/1000 * 0.375)
        # = 0.125 + 0.1875 = 0.3125 cents
        expected_cost = 0.3125
        assert abs(cost - expected_cost) < 0.001

    def test_text_extraction(self, client):
        """Test text extraction from API response"""
        response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Extracted text"}]
                    }
                }
            ]
        }

        text = client._extract_text(response_data)
        assert text == "Extracted text"

    def test_text_extraction_missing_candidates(self, client):
        """Test text extraction fails with missing candidates"""
        response_data = {"candidates": []}

        with pytest.raises(Exception, match="Invalid Gemini API response"):
            client._extract_text(response_data)

    def test_text_extraction_empty_text(self, client):
        """Test text extraction fails with empty text"""
        response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": ""}]
                    }
                }
            ]
        }

        with pytest.raises(Exception, match="Invalid Gemini API response"):
            client._extract_text(response_data)

    def test_request_building(self, client):
        """Test request payload building"""
        request_data = client._build_request(
            prompt="Test prompt",
            max_tokens=1000,
            temperature=0.8,
            system_instruction="You are a helpful assistant"
        )

        assert request_data["contents"][0]["role"] == "user"
        assert request_data["contents"][0]["parts"][0]["text"] == "Test prompt"
        assert request_data["generationConfig"]["temperature"] == 0.8
        assert request_data["generationConfig"]["maxOutputTokens"] == 1000
        assert "systemInstruction" in request_data
        assert request_data["systemInstruction"]["parts"][0]["text"] == "You are a helpful assistant"

    def test_request_building_without_system_instruction(self, client):
        """Test request building without system instruction"""
        request_data = client._build_request(
            prompt="Test prompt",
            max_tokens=1000,
            temperature=0.7,
            system_instruction=None
        )

        assert "systemInstruction" not in request_data

    def test_telemetry(self, client):
        """Test telemetry tracking"""
        # Simulate multiple requests
        client._total_requests = 3
        client._total_tokens_in = 3000
        client._total_tokens_out = 1500
        client._total_cost_cents = 0.75

        telemetry = client.get_telemetry()

        assert telemetry["model"] == "gemini-2.5-pro-latest"
        assert telemetry["total_requests"] == 3
        assert telemetry["total_tokens_in"] == 3000
        assert telemetry["total_tokens_out"] == 1500
        assert telemetry["total_cost_cents"] == 0.75
        assert telemetry["avg_tokens_per_request"] == 1500  # (3000 + 1500) / 3

    def test_create_gemini_client_with_api_key(self):
        """Test factory function with API key"""
        with patch('core.ai_models.clients.gemini_client._gemini_client_instance', None):
            client = create_gemini_client(api_key="test-key")
            assert client.api_key == "test-key"

    def test_create_gemini_client_without_api_key(self):
        """Test factory function without API key fails"""
        with patch('core.ai_models.clients.gemini_client._gemini_client_instance', None):
            with patch.dict('os.environ', {}, clear=True):
                with pytest.raises(ValueError, match="Google API key not provided"):
                    create_gemini_client()

    def test_create_gemini_client_singleton(self):
        """Test factory returns singleton instance"""
        with patch('core.ai_models.clients.gemini_client._gemini_client_instance', None):
            client1 = create_gemini_client(api_key="test-key")
            client2 = create_gemini_client()  # Should return same instance
            assert client1 is client2
