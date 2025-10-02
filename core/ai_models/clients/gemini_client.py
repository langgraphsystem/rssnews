"""
Gemini Client — Google Gemini 2.5 Pro API client
Implements timeout, retry logic, quota tracking, and telemetry
"""

import asyncio
import logging
import time
import json
from typing import Optional, Dict, Any
import aiohttp

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Client for Google Gemini 2.5 Pro API

    Features:
    - Async HTTP requests with timeout
    - Retry logic (max 2 retries on transient errors)
    - Token and cost tracking
    - Telemetry logging
    """

    # API endpoints
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    # Model pricing (cents per 1K tokens) - Gemini 2.5 Pro
    # https://ai.google.dev/pricing
    COST_INPUT = 0.125   # $1.25 per 1M input tokens
    COST_OUTPUT = 0.375  # $3.75 per 1M output tokens

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-pro-latest",
        timeout: int = 10,
        max_retries: int = 2
    ):
        """
        Initialize Gemini client

        Args:
            api_key: Google API key
            model: Model name (default: gemini-2.5-pro-latest)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        if not api_key:
            raise ValueError("Gemini API key is required")

        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

        # Telemetry
        self._total_requests = 0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._total_cost_cents = 0.0

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_instruction: Optional[str] = None
    ) -> str:
        """
        Generate text using Gemini API

        Args:
            prompt: User prompt
            max_tokens: Maximum output tokens
            temperature: Sampling temperature (0.0-1.0)
            system_instruction: Optional system instruction

        Returns:
            Generated text

        Raises:
            Exception: On API errors or timeout
        """
        start_time = time.time()

        for attempt in range(self.max_retries + 1):
            try:
                # Build request
                request_data = self._build_request(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_instruction=system_instruction
                )

                # Make API call
                response_data = await self._make_request(request_data)

                # Extract text
                text = self._extract_text(response_data)

                # Track usage
                usage = response_data.get("usageMetadata", {})
                tokens_in = usage.get("promptTokenCount", 0)
                tokens_out = usage.get("candidatesTokenCount", 0)

                # Calculate cost
                cost_cents = self._calculate_cost(tokens_in, tokens_out)

                # Update telemetry
                self._total_requests += 1
                self._total_tokens_in += tokens_in
                self._total_tokens_out += tokens_out
                self._total_cost_cents += cost_cents

                # Log success
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    f"✅ Gemini API success | "
                    f"model={self.model} | "
                    f"tokens={tokens_in}/{tokens_out} | "
                    f"cost=${cost_cents/100:.4f} | "
                    f"latency={elapsed_ms}ms | "
                    f"attempt={attempt+1}"
                )

                return text

            except asyncio.TimeoutError:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    f"⏱️ Gemini API timeout after {elapsed_ms}ms | "
                    f"attempt={attempt+1}/{self.max_retries+1}"
                )

                if attempt >= self.max_retries:
                    raise Exception(f"Gemini API timeout after {self.max_retries+1} attempts")

                # Exponential backoff
                await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                logger.warning(
                    f"🔌 Gemini API connection error: {e} | "
                    f"attempt={attempt+1}/{self.max_retries+1}"
                )

                if attempt >= self.max_retries:
                    raise Exception(f"Gemini API connection failed: {e}")

                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                # Log and re-raise non-retryable errors
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    f"❌ Gemini API error: {e} | "
                    f"latency={elapsed_ms}ms | "
                    f"attempt={attempt+1}"
                )
                raise

    def _build_request(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_instruction: Optional[str]
    ) -> Dict[str, Any]:
        """Build Gemini API request payload"""

        # Build contents
        contents = [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ]

        # Build request
        request_data = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                "topK": 40
            }
        }

        # Add system instruction if provided
        if system_instruction:
            request_data["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        return request_data

    async def _make_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP request to Gemini API"""

        url = f"{self.BASE_URL}/models/{self.model}:generateContent"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=request_data) as response:

                # Check status
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Gemini API error {response.status}: {error_text}"
                    )

                # Parse response
                response_data = await response.json()
                return response_data

    def _extract_text(self, response_data: Dict[str, Any]) -> str:
        """Extract generated text from API response"""

        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates in response")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            if not parts:
                raise ValueError("No parts in content")

            text = parts[0].get("text", "")

            if not text:
                raise ValueError("Empty text in response")

            return text

        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"Failed to extract text from response: {e}")
            logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
            raise Exception(f"Invalid Gemini API response: {e}")

    def _calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Calculate cost in cents"""
        cost_in = (tokens_in / 1000) * self.COST_INPUT
        cost_out = (tokens_out / 1000) * self.COST_OUTPUT
        return cost_in + cost_out

    def get_telemetry(self) -> Dict[str, Any]:
        """Get telemetry data"""
        return {
            "model": self.model,
            "total_requests": self._total_requests,
            "total_tokens_in": self._total_tokens_in,
            "total_tokens_out": self._total_tokens_out,
            "total_cost_cents": round(self._total_cost_cents, 4),
            "avg_tokens_per_request": (
                (self._total_tokens_in + self._total_tokens_out) / self._total_requests
                if self._total_requests > 0 else 0
            )
        }


# Singleton factory
_gemini_client_instance: Optional[GeminiClient] = None


def create_gemini_client(api_key: Optional[str] = None) -> GeminiClient:
    """
    Create or get singleton Gemini client

    Args:
        api_key: Google API key (or uses GOOGLE_API_KEY env var)

    Returns:
        GeminiClient instance
    """
    global _gemini_client_instance

    if _gemini_client_instance is None:
        import os

        key = api_key or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "Google API key not provided. "
                "Set GOOGLE_API_KEY environment variable or pass api_key parameter."
            )

        _gemini_client_instance = GeminiClient(api_key=key)
        logger.info("✅ Gemini client initialized")

    return _gemini_client_instance