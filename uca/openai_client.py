from __future__ import annotations

import os
import asyncio
import logging
import time
from typing import Any, Callable, TypeVar, Awaitable
from functools import wraps

import httpx
# import structlog # Using standard logging for now to avoid dependency issues if structlog not installed

try:
    from openai import APITimeoutError, AsyncOpenAI
except ImportError:
    AsyncOpenAI = None  # type: ignore
    APITimeoutError = None  # type: ignore

# Simple CircuitBreaker implementation since core.resilience is missing
class CircuitBreaker:
    def __init__(self, failure_threshold: int, timeout: int, expected_exception: tuple, half_open_max_calls: int):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.half_open_max_calls = half_open_max_calls
        self.state = "CLOSED"
        self.failures = 0
        self.last_failure_time = 0

    def __call__(self, func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise Exception("CircuitBreaker is OPEN")
            
            try:
                result = await func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failures = 0
                return result
            except self.expected_exception as e:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.failure_threshold:
                    self.state = "OPEN"
                raise e
        return wrapper

logger = logging.getLogger(__name__)

class OpenAIClient:
    """OpenAI client with support for GPT-5.1 and latest models (November 2025)."""

    # GPT-5.1 model identifiers (November 2025 - PRIMARY)
    GPT_5_1_INSTANT = "gpt-5.1-chat-latest"  # NEW DEFAULT
    GPT_5_1_THINKING = "gpt-5.1"
    GPT_5_1_CODEX = "gpt-5.1-codex"
    GPT_5_1_CODEX_MINI = "gpt-5.1-codex-mini"

    # GPT-5 model identifiers (August 2025 - Legacy)
    GPT_5 = "gpt-5-2025-08-07"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_NANO = "gpt-5-nano"
    GPT_5_CHAT_LATEST = "gpt-5-chat-latest"  # Redirects to gpt-5.1-chat-latest

    # Reasoning models
    O3_MINI = "o3-mini"
    O4_MINI = "o4-mini"

    # GPT-5.1 models that support adaptive reasoning
    GPT5_1_MODELS = {
        GPT_5_1_INSTANT,
        GPT_5_1_THINKING,
        GPT_5_1_CODEX,
        GPT_5_1_CODEX_MINI,
        "gpt-5.1",
        "gpt-5.1-chat-latest",
    }

    # All GPT-5 family models that support verbosity parameter
    GPT5_MODELS = GPT5_1_MODELS | {
        GPT_5,
        GPT_5_MINI,
        GPT_5_NANO,
        GPT_5_CHAT_LATEST,
        "gpt-5",
        "gpt-5-2025-08-07",
    }

    # Reasoning models that don't support temperature/top_p
    REASONING_MODELS = {O3_MINI, O4_MINI}

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        prompt_cache_retention: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        **kwargs: Any,
    ) -> None:
        if AsyncOpenAI is None:
            raise ImportError(
                "openai package not installed. Install with: pip install openai>=1.58.0"
            )

        # Default to GPT-5.1 Instant (November 2025)
        normalized_model = (model or "").strip()
        if not normalized_model:
            normalized_model = self.GPT_5_1_INSTANT
        self.model = normalized_model
        self._model_lower = normalized_model.lower()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.prompt_cache_retention = prompt_cache_retention
        self.tools = tools
        self.tool_choice = tool_choice
        self.kwargs = kwargs

        api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key parameter."
            )

        timeout_seconds = float(os.getenv("OPENAI_TIMEOUT", "60.0"))
        timeout = httpx.Timeout(
            timeout=timeout_seconds,
            read=timeout_seconds,
            write=10.0,
            connect=5.0,
        )
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60,
            expected_exception=(Exception,),
            half_open_max_calls=3,
        )

    def _is_reasoning_model(self) -> bool:
        return self._model_lower in self.REASONING_MODELS

    def _is_gpt5_1_model(self) -> bool:
        lower = getattr(self, "_model_lower", self.model.lower())
        return lower in self.GPT5_1_MODELS or "gpt-5.1" in lower or "gpt5.1" in lower

    def _is_gpt5_model(self) -> bool:
        lower = getattr(self, "_model_lower", self.model.lower())
        return lower in self.GPT5_MODELS or lower.startswith("gpt-5")

    @classmethod
    def _extract_output_text(cls, message: Any) -> str:
        if message is None:
            return ""
        content = getattr(message, "content", message)
        if isinstance(message, dict):
            content = message.get("content", content)
        return str(content) if content else ""

    async def acomplete(self, prompt: str, **params: Any) -> dict[str, Any]:
        protected_call = self._circuit_breaker(self._acomplete_impl)
        return await protected_call(prompt, **params)

    async def _acomplete_impl(self, prompt: str, **params: Any) -> dict[str, Any]:
        max_tokens = params.get("max_tokens")
        if max_tokens is None:
            max_tokens = params.get("max_completion_tokens", self.max_tokens)
        temperature = params.get("temperature", self.temperature)
        
        api_params: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }

        if self._is_gpt5_model():
            if params.get("verbosity"):
                api_params["verbosity"] = params.get("verbosity")
            if params.get("reasoning_effort"):
                api_params["reasoning_effort"] = params.get("reasoning_effort")
            api_params["max_completion_tokens"] = max_tokens
        else:
            api_params["temperature"] = temperature
            api_params["max_tokens"] = max_tokens

        # Support for response_format (Pydantic)
        response_format = params.get("response_format")
        if response_format:
             # If using parse method, we need to handle it differently or pass it to create
             # But AsyncOpenAI.chat.completions.create supports response_format for JSON mode
             # For .parse() we need beta client.
             pass

        try:
            # If response_format is a Pydantic model, we should use beta.parse if possible, 
            # or just use json_object and parse manually.
            # For compatibility with the user's provided code structure which uses .create(),
            # we will use .create() and assume the caller handles parsing if they want raw JSON,
            # OR we switch to .parse if response_format is provided.
            
            if response_format and not isinstance(response_format, dict):
                 # It's likely a Pydantic class
                 response = await self.client.beta.chat.completions.parse(
                     **api_params,
                     response_format=response_format
                 )
                 return response.choices[0].message.parsed
            else:
                if response_format:
                    api_params["response_format"] = response_format

                response = await self.client.chat.completions.create(**api_params)
                
                output_text = ""
                if response.choices:
                    output_text = response.choices[0].message.content

                return {
                    "output": output_text,
                    "usage": response.usage,
                    "finish_reason": response.choices[0].finish_reason
                }

        except Exception as e:
            logger.error(f"OpenAI Error: {e}")
            raise e
