"""
Budget Manager — Tracks tokens/cost and applies degradation when limits are reached.
Ensures commands stay within max_tokens, budget_cents, and timeout_s constraints.
"""

import logging
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when budget limits are exceeded and degradation is not possible"""
    pass


class BudgetManager:
    """Manages budget tracking and parameter degradation"""

    def __init__(
        self,
        max_tokens: int = 8000,
        budget_cents: int = 50,
        timeout_s: int = 30
    ):
        """
        Initialize budget manager

        Args:
            max_tokens: Maximum total tokens allowed
            budget_cents: Maximum cost in cents
            timeout_s: Maximum total timeout in seconds
        """
        self.max_tokens = max_tokens
        self.budget_cents = budget_cents
        self.timeout_s = timeout_s

        # Tracking
        self.spent_tokens = 0
        self.spent_cents = 0.0
        self.spent_time_s = 0.0
        self.warnings: list[str] = []

    def can_afford(
        self,
        estimated_tokens: int,
        estimated_cents: float = 0.0,
        estimated_time_s: float = 0.0
    ) -> bool:
        """
        Check if operation is affordable within budget

        Args:
            estimated_tokens: Estimated tokens for operation
            estimated_cents: Estimated cost in cents
            estimated_time_s: Estimated time in seconds

        Returns:
            True if operation is affordable
        """
        tokens_ok = (self.spent_tokens + estimated_tokens) <= self.max_tokens
        cost_ok = (self.spent_cents + estimated_cents) <= self.budget_cents
        time_ok = (self.spent_time_s + estimated_time_s) <= self.timeout_s

        return tokens_ok and cost_ok and time_ok

    def record_usage(
        self,
        tokens: int,
        cost_cents: float,
        latency_s: float
    ) -> None:
        """
        Record actual usage

        Args:
            tokens: Tokens used
            cost_cents: Cost in cents
            latency_s: Latency in seconds
        """
        self.spent_tokens += tokens
        self.spent_cents += cost_cents
        self.spent_time_s += latency_s

        logger.info(
            f"Budget usage: tokens={self.spent_tokens}/{self.max_tokens} "
            f"cost={self.spent_cents:.2f}/{self.budget_cents}¢ "
            f"time={self.spent_time_s:.1f}/{self.timeout_s}s"
        )

    def get_remaining_budget(self) -> Dict[str, float]:
        """Get remaining budget percentages"""
        return {
            "tokens_pct": ((self.max_tokens - self.spent_tokens) / self.max_tokens) * 100,
            "cost_pct": ((self.budget_cents - self.spent_cents) / self.budget_cents) * 100,
            "time_pct": ((self.timeout_s - self.spent_time_s) / self.timeout_s) * 100
        }

    def should_degrade(self) -> bool:
        """
        Check if degradation should be applied

        Returns:
            True if any budget metric is >70% spent
        """
        remaining = self.get_remaining_budget()
        return any(pct < 30 for pct in remaining.values())

    def get_degraded_params(
        self,
        command: Literal["/ask", "/events", "/graph", "/memory", "/synthesize"],
        current_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get degraded parameters based on command and remaining budget

        Args:
            command: Command name
            current_params: Current parameters

        Returns:
            Degraded parameters with warnings
        """
        degraded = dict(current_params)
        remaining = self.get_remaining_budget()
        min_remaining_pct = min(remaining.values())

        logger.info(f"Applying degradation for {command} (min_budget={min_remaining_pct:.1f}%)")

        if command == "/ask":
            # Agentic RAG degradation
            original_depth = degraded.get("depth", 3)
            if min_remaining_pct < 30:
                degraded["depth"] = 1
                degraded["self_check"] = False
                degraded["use_rerank"] = False
                self.warnings.append("Degraded to 1 iteration (no self-check, no rerank)")
            elif min_remaining_pct < 50:
                degraded["depth"] = min(2, original_depth)
                degraded["self_check"] = False
                self.warnings.append("Degraded to 2 iterations (no self-check)")

        elif command == "/graph":
            # GraphRAG degradation
            if min_remaining_pct < 30:
                degraded["hop_limit"] = 1
                degraded["max_nodes"] = 60
                degraded["max_edges"] = 180
                degraded["use_rerank"] = False
                self.warnings.append("Degraded graph: hop_limit=1, max_nodes=60, max_edges=180")
            elif min_remaining_pct < 50:
                degraded["hop_limit"] = 2
                degraded["max_nodes"] = 120
                degraded["max_edges"] = 360
                self.warnings.append("Degraded graph: hop_limit=2, max_nodes=120")

        elif command == "/events":
            # Event linking degradation
            original_k = degraded.get("k_final", 10)
            if min_remaining_pct < 30:
                degraded["k_final"] = min(5, original_k)
                degraded["include_alternatives"] = False
                degraded["use_rerank"] = False
                self.warnings.append("Degraded events: top-5 only, no alternatives, no rerank")
            elif min_remaining_pct < 50:
                degraded["include_alternatives"] = False
                self.warnings.append("Degraded events: no alternative interpretations")

        elif command == "/memory":
            # Memory degradation
            if min_remaining_pct < 30:
                degraded["operation"] = "recall"  # Force recall-only
                self.warnings.append("Degraded memory: recall-only (no suggest/store)")

        elif command == "/synthesize":
            # Synthesis degradation
            original_k = degraded.get("k_final", 10)
            if min_remaining_pct < 30:
                degraded["k_final"] = min(5, original_k)
                degraded["use_rerank"] = False
                self.warnings.append("Degraded synthesis: k_final=5, no rerank")

        # Global degradations
        if min_remaining_pct < 20:
            degraded["k_final"] = min(3, degraded.get("k_final", 5))
            self.warnings.append("Critical budget: reduced k_final to 3")

        return degraded

    def check_exceeded(self) -> None:
        """
        Check if budget is exceeded and raise error

        Raises:
            BudgetExceededError: If any budget limit is exceeded
        """
        if self.spent_tokens > self.max_tokens:
            raise BudgetExceededError(
                f"Token limit exceeded: {self.spent_tokens}/{self.max_tokens}"
            )

        if self.spent_cents > self.budget_cents:
            raise BudgetExceededError(
                f"Cost limit exceeded: {self.spent_cents:.2f}/{self.budget_cents}¢"
            )

        if self.spent_time_s > self.timeout_s:
            raise BudgetExceededError(
                f"Timeout exceeded: {self.spent_time_s:.1f}/{self.timeout_s}s"
            )

    def get_warnings(self) -> list[str]:
        """Get accumulated warnings"""
        return self.warnings.copy()

    def reset(self) -> None:
        """Reset budget tracking"""
        self.spent_tokens = 0
        self.spent_cents = 0.0
        self.spent_time_s = 0.0
        self.warnings = []
        logger.info("Budget reset")

    def get_summary(self) -> Dict[str, Any]:
        """Get budget usage summary"""
        return {
            "spent": {
                "tokens": self.spent_tokens,
                "cost_cents": round(self.spent_cents, 2),
                "time_s": round(self.spent_time_s, 1)
            },
            "limits": {
                "max_tokens": self.max_tokens,
                "budget_cents": self.budget_cents,
                "timeout_s": self.timeout_s
            },
            "remaining_pct": self.get_remaining_budget(),
            "warnings": self.warnings
        }


def create_budget_manager(
    max_tokens: int = 8000,
    budget_cents: int = 50,
    timeout_s: int = 30
) -> BudgetManager:
    """Factory function to create budget manager with defaults"""
    return BudgetManager(
        max_tokens=max_tokens,
        budget_cents=budget_cents,
        timeout_s=timeout_s
    )
