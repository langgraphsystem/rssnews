"""Locust performance tests for Phase 2 orchestrator endpoints.

Usage:
    ORCHESTRATOR_BASE_URL=http://localhost:8080 locust -f tests/perf/locustfile.py

The default tasks exercise /trends and /analyze (keywords, sentiment, topics)
with realistic JSON payloads produced by the bot service. Adjust weights and
payloads as needed for your environment.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from locust import HttpUser, between, constant_throughput, task


DEFAULT_HEADERS = {"Content-Type": "application/json"}


def _payload(command: str, **overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "command": command,
        "params": {
            "window": overrides.get("window", "24h"),
            "lang": overrides.get("lang", "auto"),
            "k_final": overrides.get("k_final", 6),
            "sources": overrides.get("sources", []),
        },
        "retrieval": {
            "docs": overrides.get("docs", []),
            "window": overrides.get("window", "24h"),
            "lang": overrides.get("lang", "auto"),
            "sources": overrides.get("sources", []),
            "k_final": overrides.get("k_final", 6),
            "rerank_enabled": overrides.get("rerank_enabled", True),
        },
        "limits": {
            "max_tokens": overrides.get("max_tokens", 3000),
            "budget_cents": overrides.get("budget_cents", 50),
            "timeout_s": overrides.get("timeout_s", 12),
        },
        "telemetry": {
            "correlation_id": overrides.get("correlation_id", "locust"),
            "version": overrides.get("version", "phase2-loadtest"),
        },
    }
    if command.startswith("/analyze"):
        base["params"]["mode"] = overrides.get("mode", command.split()[1])
    return base


class OrchestratorUser(HttpUser):
    """Simulates bot-triggered orchestrator commands."""

    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:  # pragma: no cover - locust runtime hook
        self.base_url = os.getenv("ORCHESTRATOR_BASE_URL", "http://localhost:8080")
        self.headers = DEFAULT_HEADERS.copy()

    def _post(self, path: str, payload: Dict[str, Any]) -> None:
        self.client.post(
            path,
            data=json.dumps(payload),
            headers=self.headers,
            name=path,
        )

    @task(3)
    def trends(self) -> None:
        payload = _payload(
            "/trends",
            docs=[{
                "article_id": "art-001",
                "title": "AI adoption accelerates",
                "url": "https://example.com/ai",
                "date": "2025-09-28",
                "lang": "en",
                "score": 0.82,
                "snippet": "Organisations report faster deployment of LLM assistants...",
            }],
        )
        self._post("/orchestrator/trends", payload)

    @task(2)
    def analyze_keywords(self) -> None:
        payload = _payload(
            "/analyze keywords",
            mode="keywords",
            docs=[{
                "article_id": "art-100",
                "title": "LLM privacy controls",
                "url": "https://example.com/privacy",
                "date": "2025-09-27",
                "lang": "en",
                "score": 0.77,
                "snippet": "Vendors launch differential privacy options for AI stacks...",
            }],
        )
        self._post("/orchestrator/analyze", payload)

    @task(1)
    def analyze_sentiment(self) -> None:
        payload = _payload(
            "/analyze sentiment",
            mode="sentiment",
            docs=[{
                "article_id": "art-200",
                "title": "Investors sceptical about AI hype",
                "url": "https://example.com/investor",
                "date": "2025-09-26",
                "lang": "en",
                "score": 0.64,
                "snippet": "Analysts warn valuations may outpace revenue beyond 2026...",
            }],
        )
        self._post("/orchestrator/analyze", payload)

    @task(1)
    def analyze_topics(self) -> None:
        payload = _payload(
            "/analyze topics",
            mode="topics",
            docs=[{
                "article_id": "art-300",
                "title": "AI regulation update",
                "url": "https://example.com/reg",
                "date": "2025-09-25",
                "lang": "en",
                "score": 0.7,
                "snippet": "New guidance focuses on auditability and incident reporting...",
            }],
        )
        self._post("/orchestrator/analyze", payload)

    @task(0.5)
    def forecast(self) -> None:
        payload = _payload(
            "/predict trends",
            docs=[{
                "article_id": "art-400",
                "title": "AI chips production ramp",
                "url": "https://example.com/chips",
                "date": "2025-09-28",
                "lang": "en",
                "score": 0.81,
                "snippet": "Vendors announce 2x capacity growth for TPU equivalents...",
            }],
            topic="AI hardware",
        )
        self._post("/orchestrator/predict", payload)
