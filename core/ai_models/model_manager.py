"""
Model Manager — Centralized model selection, fallback, budget, and timeout management
Handles: primary/fallback routing, budget tracking, timeout enforcement, retry logic
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from infra.config.phase1_config import get_config, ModelRoute
from monitoring.metrics import record_model_invocation

logger = logging.getLogger(__name__)


@dataclass
class ModelInvocation:
    """Record of a single model invocation"""
    task: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_cents: float
    latency_ms: int
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BudgetTracker:
    """Budget tracking for commands and users"""
    command_tokens_used: int = 0
    command_cost_cents: float = 0.0
    user_commands_today: int = 0
    user_cost_today_cents: float = 0.0
    invocations: List[ModelInvocation] = field(default_factory=list)


class ModelManager:
    """
    Centralized manager for all model interactions
    Responsibilities:
    - Route tasks to primary/fallback models
    - Track budget (tokens + cost)
    - Enforce timeouts
    - Handle retries
    - Log telemetry
    """

    # Model cost estimates (cents per 1K tokens)
    # Input / Output
    MODEL_COSTS = {
        "gpt-5": (0.3, 0.6),  # Placeholder
        "gpt-4o-mini": (0.015, 0.06),
        "claude-4.5": (0.3, 1.5),  # Claude Sonnet 4
        "gemini-2.5-pro": (0.125, 0.375),
        "cohere-rerank-v3": (0.002, 0.002),
    }

    def __init__(self, correlation_id: str):
        self.config = get_config()
        self.correlation_id = correlation_id
        self.budget_tracker = BudgetTracker()

        # Import model clients
        self._init_clients()

    def _init_clients(self):
        """Initialize model clients (lazy loading)"""
        self._gpt5_client = None
        self._claude_client = None
        self._gemini_client = None

    def _get_gpt5_client(self):
        """Get or create GPT-5 client"""
        if self._gpt5_client is None:
            from gpt5_service_new import create_gpt5_service
            self._gpt5_client = create_gpt5_service()
        return self._gpt5_client

    def _get_claude_client(self):
        """Get or create Claude client"""
        if self._claude_client is None:
            from services.claude_service import create_claude_service
            self._claude_client = create_claude_service()
        return self._claude_client

    def _get_gemini_client(self):
        """Get or create Gemini client"""
        if self._gemini_client is None:
            from core.ai_models.clients.gemini_client import create_gemini_client
            try:
                self._gemini_client = create_gemini_client()
                logger.info("✅ Gemini client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Gemini client: {e}")
                return None
        return self._gemini_client

    async def invoke_model(
        self,
        task: str,
        prompt: str,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Tuple[str, List[str]]:
        """
        Invoke model with fallback chain
        Returns: (output_text, warnings)
        """
        route = self._get_route(task)
        if not route:
            raise ValueError(f"Unknown task: {task}")

        # Check budget before invoking
        if not self._check_budget_available():
            raise Exception("BUDGET_EXCEEDED: Command budget limit reached")

        warnings = []
        models_tried = []

        # Try primary model
        try:
            result = await self._invoke_single_model(
                task=task,
                model=route.primary,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout_seconds=route.timeout_seconds,
                **kwargs
            )
            if result:
                return result, warnings
        except Exception as e:
            logger.warning(f"Primary model {route.primary} failed: {e}")
            models_tried.append(route.primary)
            warnings.append(f"fallback_used: {route.primary} failed")

        # Try fallback models
        for fallback_model in route.fallback:
            try:
                logger.info(f"Trying fallback model: {fallback_model}")
                result = await self._invoke_single_model(
                    task=task,
                    model=fallback_model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    timeout_seconds=route.timeout_seconds,
                    **kwargs
                )
                if result:
                    warnings.append(f"fallback_used: {fallback_model}")
                    return result, warnings
            except Exception as e:
                logger.warning(f"Fallback model {fallback_model} failed: {e}")
                models_tried.append(fallback_model)

        # All models failed
        raise Exception(
            f"MODEL_UNAVAILABLE: All models failed for task {task}. Tried: {', '.join(models_tried)}"
        )

    async def _invoke_single_model(
        self,
        task: str,
        model: str,
        prompt: str,
        max_tokens: Optional[int],
        timeout_seconds: int,
        **kwargs
    ) -> Optional[str]:
        """
        Invoke a single model with timeout
        Returns output text or None if failed
        """
        start_time = time.time()

        try:
            # Route to appropriate client
            if model.startswith("gpt"):
                client = self._get_gpt5_client()
                result = await asyncio.wait_for(
                    self._call_gpt5(client, prompt, max_tokens, **kwargs),
                    timeout=timeout_seconds
                )
            elif model.startswith("claude"):
                client = self._get_claude_client()
                result = await asyncio.wait_for(
                    self._call_claude(client, prompt, max_tokens, **kwargs),
                    timeout=timeout_seconds
                )
            elif model.startswith("gemini"):
                client = self._get_gemini_client()
                if not client:
                    raise Exception("Gemini client not available")
                result = await asyncio.wait_for(
                    self._call_gemini(client, prompt, max_tokens, **kwargs),
                    timeout=timeout_seconds
                )
            else:
                raise ValueError(f"Unknown model: {model}")

            # Track invocation
            latency_ms = int((time.time() - start_time) * 1000)
            prompt_tokens = len(prompt.split())  # Rough estimate
            completion_tokens = len(result.split()) if result else 0
            cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

            self._track_invocation(
                task=task,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_cents=cost,
                latency_ms=latency_ms,
                success=True
            )

            logger.info(
                f"✅ Model {model} succeeded | "
                f"latency={latency_ms}ms | "
                f"tokens={prompt_tokens}/{completion_tokens} | "
                f"cost=${cost/100:.4f}"
            )

            return result

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            self._track_invocation(
                task=task,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                cost_cents=0,
                latency_ms=latency_ms,
                success=False,
                error="TIMEOUT"
            )
            logger.error(f"❌ Model {model} timeout after {timeout_seconds}s")
            raise Exception(f"TIMEOUT: {model} exceeded {timeout_seconds}s")

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            self._track_invocation(
                task=task,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                cost_cents=0,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
            logger.error(f"❌ Model {model} error: {e}")
            raise

    async def _call_gpt5(self, client, prompt: str, max_tokens: Optional[int], **kwargs) -> str:
        """Call GPT-5 service"""
        result = await client.generate_text(
            prompt,
            max_output_tokens=max_tokens or 2000,
            **kwargs
        )
        return result

    async def _call_claude(self, client, prompt: str, max_tokens: Optional[int], **kwargs) -> str:
        """Call Claude service (adapt to analysis method)"""
        # For now, use simple prompt wrapper
        # TODO: Integrate with Claude's structured format
        result = await client._make_api_request(prompt)

        # Extract text from Claude response
        content = result.get("content", [])
        text_blocks = [block.get("text", "") for block in content if block.get("type") == "text"]
        return "\n".join(text_blocks)

    async def _call_gemini(self, client, prompt: str, max_tokens: Optional[int], **kwargs) -> str:
        """Call Gemini service"""
        result = await client.generate_text(
            prompt=prompt,
            max_tokens=max_tokens or 2000,
            temperature=kwargs.get("temperature", 0.7),
            system_instruction=kwargs.get("system_instruction")
        )
        return result

    def _get_route(self, task: str) -> Optional[ModelRoute]:
        """Get model routing for task"""
        return getattr(self.config.models, task, None)

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in cents"""
        if model not in self.MODEL_COSTS:
            # Default to GPT-4o-mini costs if unknown
            input_cost, output_cost = self.MODEL_COSTS["gpt-4o-mini"]
        else:
            input_cost, output_cost = self.MODEL_COSTS[model]

        cost = (prompt_tokens / 1000 * input_cost) + (completion_tokens / 1000 * output_cost)
        return cost

    def _track_invocation(
        self,
        task: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_cents: float,
        latency_ms: int,
        success: bool,
        error: Optional[str] = None
    ):
        """Track model invocation in budget tracker"""
        invocation = ModelInvocation(
            task=task,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_cents=cost_cents,
            latency_ms=latency_ms,
            success=success,
            error=error
        )

        self.budget_tracker.invocations.append(invocation)
        self.budget_tracker.command_tokens_used += prompt_tokens + completion_tokens
        self.budget_tracker.command_cost_cents += cost_cents
        record_model_invocation(
            task=task,
            model=model,
            latency_ms=latency_ms,
            cost_cents=cost_cents,
            success=success,
        )


    def _check_budget_available(self) -> bool:
        """Check if budget is available for next invocation"""
        if not self.config.budget.enable_budget_tracking:
            return True

        # Check command budget
        if self.budget_tracker.command_tokens_used >= self.config.budget.max_tokens_per_command:
            logger.warning("Command token budget exceeded")
            return False

        if self.budget_tracker.command_cost_cents >= self.config.budget.max_cost_cents_per_command:
            logger.warning("Command cost budget exceeded")
            return False

        return True

    def get_budget_summary(self) -> Dict[str, Any]:
        """Get budget summary for telemetry"""
        return {
            "tokens_used": self.budget_tracker.command_tokens_used,
            "cost_cents": round(self.budget_tracker.command_cost_cents, 4),
            "invocations": len(self.budget_tracker.invocations),
            "successful": sum(1 for inv in self.budget_tracker.invocations if inv.success),
            "failed": sum(1 for inv in self.budget_tracker.invocations if not inv.success),
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Get full telemetry data"""
        invocations_summary = []
        for inv in self.budget_tracker.invocations:
            invocations_summary.append({
                "task": inv.task,
                "model": inv.model,
                "latency_ms": inv.latency_ms,
                "cost_cents": round(inv.cost_cents, 4),
                "success": inv.success,
                "error": inv.error
            })

        return {
            "correlation_id": self.correlation_id,
            "budget": self.get_budget_summary(),
            "invocations": invocations_summary,
        }

