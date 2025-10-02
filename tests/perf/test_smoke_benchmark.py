"""Pytest benchmark smoke test for orchestrator functions."""

import asyncio
from typing import Any, Dict

import pytest

from services.orchestrator import OrchestratorService


@pytest.mark.benchmark(group="orchestrator-smoke")
def test_trends_smoke(benchmark):
    orchestrator = OrchestratorService()

    sample_payload: Dict[str, Any] = {
        "window": "24h",
        "lang": "auto",
        "sources": [],
        "k_final": 5,
    }

    async def run_trends() -> Dict[str, Any]:
        return await orchestrator.handle_trends_command(**sample_payload)

    result = benchmark(lambda: asyncio.run(run_trends()))
    assert "text" in result
