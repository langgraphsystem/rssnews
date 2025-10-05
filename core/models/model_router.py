"""
Model Router — Handles LLM routing with fallback chains and timeout management.
Supports GPT-5, Claude 4.5, Gemini 2.5 Pro with automatic fallbacks.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import os

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency
    AsyncOpenAI = None

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - optional dependency
    AsyncAnthropic = None

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None

logger = logging.getLogger(__name__)


class ModelUnavailableError(Exception):
    """Raised when all models in the fallback chain fail"""
    pass


class ModelRouter:
    """Routes requests to LLM models with automatic fallback handling"""

    # Model name mapping
    MODEL_MAP = {
        "gpt-5": os.getenv('OPENAI_GPT5_MODEL', 'gpt-5'),
        "gpt-5-mini": os.getenv('OPENAI_GPT5_MINI_MODEL', 'gpt-5-mini'),
        "gpt-5-nano": os.getenv('OPENAI_GPT5_NANO_MODEL', 'gpt-5-nano'),
        "gpt-3.5-turbo": "gpt-3.5-turbo",
        "claude-4.5": os.getenv('ANTHROPIC_CLAUDE_MODEL', 'claude-3-5-sonnet-20241022'),
        "gemini-2.5-pro": os.getenv('GOOGLE_GEMINI_MODEL', 'gemini-1.5-pro-latest')
    }

    # Token cost per 1K tokens (cents)
    TOKEN_COSTS = {
        "gpt-5": {"input": 0.8, "output": 2.4},
        "gpt-5-mini": {"input": 0.25, "output": 0.75},
        "gpt-5-nano": {"input": 0.12, "output": 0.36},
        "claude-4.5": {"input": 0.3, "output": 1.5},
        "gemini-2.5-pro": {"input": 0.125, "output": 0.375}
    }

    def __init__(self):
        """Initialize model clients"""
        self.openai_client = None
        self.anthropic_client = None
        self.gemini_configured = False

        # Lazy initialization - clients created on first use
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize API clients if keys are available"""
        try:
            if AsyncOpenAI and os.getenv("OPENAI_API_KEY"):
                self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                logger.info("OpenAI client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client: {e}")

        try:
            if AsyncAnthropic and os.getenv("ANTHROPIC_API_KEY"):
                self.anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                logger.info("Anthropic client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Anthropic client: {e}")

        try:
            if genai and os.getenv("GOOGLE_API_KEY"):
                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                self.gemini_configured = True
                logger.info("Google Gemini configured")
        except Exception as e:
            logger.warning(f"Failed to configure Gemini: {e}")

    def has_any_client(self) -> bool:
        """Check if at least one provider client is available"""
        return bool(self.openai_client or self.anthropic_client or self.gemini_configured)

    async def call_with_fallback(
        self,
        prompt: str,
        docs: List[Dict[str, Any]],
        primary: str,
        fallback: List[str],
        timeout_s: int,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Call LLM with automatic fallback chain

        Args:
            prompt: System/user prompt
            docs: Supporting documents for context
            primary: Primary model name
            fallback: List of fallback models
            timeout_s: Timeout per model call
            max_tokens: Max output tokens
            temperature: Sampling temperature

        Returns:
            Tuple of (response_dict, metadata_dict)
                - response_dict: {"content": str, "model": str}
                - metadata_dict: {"tokens_used": int, "cost_cents": float, "latency_ms": float}

        Raises:
            ModelUnavailableError: If all models fail
        """
        models_to_try = [primary] + fallback
        last_error = None

        for model_name in models_to_try:
            try:
                logger.info(f"Trying model: {model_name} (timeout={timeout_s}s)")
                start_time = time.time()

                response, tokens_used = await asyncio.wait_for(
                    self._call_model(prompt, docs, model_name, max_tokens, temperature),
                    timeout=timeout_s
                )

                latency_ms = (time.time() - start_time) * 1000
                cost_cents = self._calculate_cost(model_name, tokens_used)

                logger.info(
                    f"Success: {model_name} | tokens={tokens_used} | "
                    f"cost={cost_cents:.3f}¢ | latency={latency_ms:.0f}ms"
                )

                return (
                    {"content": response, "model": model_name},
                    {
                        "tokens_used": tokens_used,
                        "cost_cents": cost_cents,
                        "latency_ms": latency_ms,
                        "fallback_used": model_name != primary
                    }
                )

            except asyncio.TimeoutError:
                logger.warning(f"Timeout for {model_name} after {timeout_s}s")
                last_error = f"Timeout: {model_name}"
                continue

            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}")
                last_error = str(e)
                continue

        # All models failed
        raise ModelUnavailableError(
            f"All models failed. Last error: {last_error}. Tried: {models_to_try}"
        )

    async def _call_model(
        self,
        prompt: str,
        docs: List[Dict[str, Any]],
        model_name: str,
        max_tokens: int,
        temperature: float
    ) -> Tuple[str, int]:
        """
        Call specific model

        Returns:
            Tuple of (response_text, total_tokens)
        """
        # Build context from docs
        context = self._build_context(docs)
        full_prompt = f"{prompt}\n\nContext:\n{context}"

        if model_name.startswith("gpt"):
            return await self._call_openai(full_prompt, model_name, max_tokens, temperature)
        elif model_name.startswith("claude"):
            return await self._call_anthropic(full_prompt, model_name, max_tokens, temperature)
        elif model_name.startswith("gemini"):
            return await self._call_gemini(full_prompt, model_name, max_tokens, temperature)
        else:
            raise ValueError(f"Unknown model family: {model_name}")

    async def _call_openai(
        self,
        prompt: str,
        model_name: str,
        max_tokens: int,
        temperature: float
    ) -> Tuple[str, int]:
        """Call OpenAI API"""
        if not self.openai_client:
            raise ModelUnavailableError("OpenAI client not initialized")

        actual_model = self.MODEL_MAP.get(model_name, model_name)

        response = await self.openai_client.chat.completions.create(
            model=actual_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )

        content = response.choices[0].message.content
        tokens = response.usage.total_tokens

        return content, tokens

    async def _call_anthropic(
        self,
        prompt: str,
        model_name: str,
        max_tokens: int,
        temperature: float
    ) -> Tuple[str, int]:
        """Call Anthropic API"""
        if not self.anthropic_client:
            raise ModelUnavailableError("Anthropic client not initialized")

        actual_model = self.MODEL_MAP.get(model_name, model_name)

        response = await self.anthropic_client.messages.create(
            model=actual_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response.content[0].text
        # Anthropic returns input/output tokens separately
        tokens = response.usage.input_tokens + response.usage.output_tokens

        return content, tokens

    async def _call_gemini(
        self,
        prompt: str,
        model_name: str,
        max_tokens: int,
        temperature: float
    ) -> Tuple[str, int]:
        """Call Google Gemini API"""
        if not self.gemini_configured or not genai:
            raise ModelUnavailableError("Gemini not configured")

        actual_model = self.MODEL_MAP.get(model_name, model_name)

        model = genai.GenerativeModel(actual_model)

        # Gemini API is not async by default, run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                prompt,
                generation_config=(
                    genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature
                    ) if hasattr(genai, "types") else None
                )
            )
        )

        content = response.text
        # Gemini doesn't provide token counts directly, estimate
        tokens = self._estimate_tokens(prompt, content)

        return content, tokens

    def _build_context(self, docs: List[Dict[str, Any]], max_docs: int = 10) -> str:
        """Build context string from documents"""
        if not docs:
            return "No supporting documents provided."

        context_parts = []
        for idx, doc in enumerate(docs[:max_docs], 1):
            title = doc.get("title", "Untitled")
            snippet = doc.get("snippet", doc.get("content", ""))[:200]
            date = doc.get("date", "N/A")
            url = doc.get("url", "")

            context_parts.append(
                f"[{idx}] {title}\n"
                f"Date: {date}\n"
                f"URL: {url}\n"
                f"Excerpt: {snippet}\n"
            )

        return "\n".join(context_parts)

    def _estimate_tokens(self, prompt: str, response: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars)"""
        total_chars = len(prompt) + len(response)
        return total_chars // 4

    def _calculate_cost(self, model_name: str, tokens: int) -> float:
        """Calculate cost in cents based on token usage"""
        if model_name not in self.TOKEN_COSTS:
            return 0.0

        # Rough estimate: 70% input, 30% output tokens
        input_tokens = int(tokens * 0.7)
        output_tokens = int(tokens * 0.3)

        costs = self.TOKEN_COSTS[model_name]
        total_cost = (
            (input_tokens / 1000) * costs["input"] +
            (output_tokens / 1000) * costs["output"]
        )

        return round(total_cost, 4)


# Singleton instance
class MockModelRouter:
    """Simple mock router returning deterministic responses for tests/CI"""

    async def call_with_fallback(
        self,
        prompt: str,
        docs: List[Dict[str, Any]],
        primary: str,
        fallback: List[str],
        timeout_s: int,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        snippet = prompt.strip().splitlines()[0][:160] if prompt else ""
        content = f"[mock:{primary}] {snippet}"
        tokens = max(32, len(prompt) // 4)
        metadata = {
            "tokens_used": tokens,
            "cost_cents": 0.0,
            "latency_ms": 5.0,
            "fallback_used": False,
        }
        return {"content": content, "model": primary}, metadata


_router_instance: Optional[Union[ModelRouter, MockModelRouter]] = None


def get_model_router() -> Union[ModelRouter, MockModelRouter]:
    """Get singleton model router"""
    global _router_instance
    if _router_instance is None:
        mode = os.getenv("PHASE3_MODEL_ROUTER_MODE", "").lower()
        if mode == "mock":
            logger.info("ModelRouter running in mock mode (env override)")
            _router_instance = MockModelRouter()
        else:
            try:
                router = ModelRouter()
                if not router.has_any_client():
                    logger.warning(
                        "No LLM API clients configured; falling back to MockModelRouter."
                    )
                    _router_instance = MockModelRouter()
                else:
                    _router_instance = router
            except Exception as exc:
                logger.warning(
                    "Failed to initialize ModelRouter (%s); using mock mode.", exc
                )
                _router_instance = MockModelRouter()
    return _router_instance
