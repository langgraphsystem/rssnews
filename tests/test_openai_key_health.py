"""OpenAI API key health tests.

These tests validate that:
- OPENAI_API_KEY is present in environment
- The Models endpoint is reachable (GET /v1/models)
- A minimal Responses API call works for a small subset of models from gpt5.config.json

Safe by default:
- Skips when no OPENAI_API_KEY
- Uses tiny prompts and token limits
"""

from __future__ import annotations

import json
import os
from typing import List, Dict, Any

import httpx
import pytest
from openai import OpenAI


ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ROOT, "gpt5.config.json")


def load_models_from_config(max_models: int = 3) -> List[str]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg: Dict[str, Any] = json.load(f)
        models = [m["id"] for m in cfg.get("models", []) if "id" in m]
        return models[:max_models]
    except Exception:
        return []


@pytest.fixture(scope="session")
def api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        pytest.skip("OPENAI_API_KEY is not set; skipping OpenAI key health tests")
    return key


def test_models_endpoint_reachable(api_key: str) -> None:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=20.0) as client:
        r = client.get("https://api.openai.com/v1/models", headers=headers)
    assert r.status_code == 200, f"/v1/models failed: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("model_id", load_models_from_config())
def test_minimal_responses_call(api_key: str, model_id: str) -> None:
    if not model_id:
        pytest.skip("No models found in config")
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(
        model=model_id,
        input=[{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
        max_output_tokens=8,
    )
    text = getattr(resp, "output_text", "")
    assert isinstance(text, str) and len(text) >= 1

