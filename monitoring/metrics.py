"""Prometheus metrics helpers for Phase 1 orchestrator and AI clients."""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
except ModuleNotFoundError:  # pragma: no cover
    Counter = Gauge = Histogram = None  # type: ignore
    start_http_server = None  # type: ignore

_PRIMARY_METRICS_ENABLED = {"true", "1", "yes", "on"}
_METRICS_STARTED = False
_METRICS_LOCK = threading.Lock()


def _metrics_available() -> bool:
    return Counter is not None and Histogram is not None and Gauge is not None and start_http_server is not None


def metrics_enabled() -> bool:
    """Return True when metrics collection is enabled via environment variable."""

    return os.getenv("ENABLE_METRICS", "true").lower() in _PRIMARY_METRICS_ENABLED


def ensure_metrics_server() -> None:
    """Start the Prometheus HTTP server once (idempotent)."""

    global _METRICS_STARTED

    if not metrics_enabled() or not _metrics_available():
        return

    if _METRICS_STARTED:
        return

    with _METRICS_LOCK:
        if _METRICS_STARTED:
            return

        port = int(os.getenv("METRICS_PORT", "9464"))
        host = os.getenv("METRICS_HOST", "0.0.0.0")
        start_http_server(port, addr=host)
        _METRICS_STARTED = True


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

if _metrics_available():
    ORCHESTRATOR_REQUESTS = Counter(
        "rss_orchestrator_requests_total",
        "Total orchestrator requests by command",
        ["command"],
    )
    ORCHESTRATOR_ERRORS = Counter(
        "rss_orchestrator_errors_total",
        "Total orchestrator error responses",
        ["command", "reason"],
    )
    ORCHESTRATOR_LATENCY = Histogram(
        "rss_orchestrator_latency_seconds",
        "Orchestrator end-to-end latency",
        ["command"],
        buckets=(0.5, 1, 2, 3, 4, 6, 8, 10, 12, 15, 20, 30),
    )
    ORCHESTRATOR_EVIDENCE = Gauge(
        "rss_orchestrator_evidence_coverage_ratio",
        "Evidence coverage ratio (0-1) per command",
        ["command"],
    )
    COMMAND_COST = Histogram(
        "rss_command_cost_cents",
        "Estimated command cost in cents",
        ["command"],
        buckets=(5, 10, 20, 30, 40, 50, 75, 100),
    )

    MODEL_INVOCATIONS = Counter(
        "rss_model_invocations_total",
        "Model invocations by task and outcome",
        ["model", "task", "outcome"],
    )
    MODEL_LATENCY = Histogram(
        "rss_model_latency_seconds",
        "Latency per model invocation",
        ["model", "task"],
        buckets=(0.25, 0.5, 1, 2, 4, 6, 8, 10, 15, 20),
    )
    MODEL_COST = Counter(
        "rss_model_cost_cents_total",
        "Accumulated model cost in cents",
        ["model"],
    )
else:  # pragma: no cover - metrics optional during testing
    ORCHESTRATOR_REQUESTS = ORCHESTRATOR_ERRORS = ORCHESTRATOR_LATENCY = None
    ORCHESTRATOR_EVIDENCE = COMMAND_COST = None
    MODEL_INVOCATIONS = MODEL_LATENCY = MODEL_COST = None


# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------


def record_orchestrator_start(command: str) -> float:
    """Register the start of an orchestrator command and return timer."""

    ensure_metrics_server()
    if ORCHESTRATOR_REQUESTS:
        ORCHESTRATOR_REQUESTS.labels(command=command).inc()
    return time.time()


def record_orchestrator_success(
    command: str,
    start_time: float,
    evidence_count: int,
    docs_count: Optional[int] = None,
    cost_cents: Optional[float] = None,
) -> None:
    """Record orchestrator success metrics."""

    if ORCHESTRATOR_LATENCY:
        ORCHESTRATOR_LATENCY.labels(command=command).observe(max(time.time() - start_time, 0.0))

    if ORCHESTRATOR_EVIDENCE:
        coverage = 0.0
        if docs_count and docs_count > 0:
            coverage = min(evidence_count / max(docs_count, 1), 1.0)
        elif evidence_count:
            coverage = 1.0
        ORCHESTRATOR_EVIDENCE.labels(command=command).set(coverage)

    if cost_cents is not None and COMMAND_COST:
        COMMAND_COST.labels(command=command).observe(max(cost_cents, 0.0))


def record_orchestrator_error(command: str, start_time: float, reason: str) -> None:
    """Record orchestrator error metrics."""

    if ORCHESTRATOR_LATENCY:
        ORCHESTRATOR_LATENCY.labels(command=command).observe(max(time.time() - start_time, 0.0))
    if ORCHESTRATOR_ERRORS:
        ORCHESTRATOR_ERRORS.labels(command=command, reason=reason).inc()


def record_model_invocation(
    *,
    task: str,
    model: str,
    latency_ms: int,
    cost_cents: float,
    success: bool,
) -> None:
    """Record a single model invocation."""

    ensure_metrics_server()
    outcome = "success" if success else "failure"

    if MODEL_INVOCATIONS:
        MODEL_INVOCATIONS.labels(model=model, task=task, outcome=outcome).inc()

    if MODEL_LATENCY:
        MODEL_LATENCY.labels(model=model, task=task).observe(max(latency_ms / 1000.0, 0.0))

    if cost_cents and MODEL_COST:
        MODEL_COST.labels(model=model).inc(max(cost_cents, 0.0))
