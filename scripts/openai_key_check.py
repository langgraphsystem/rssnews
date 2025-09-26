#!/usr/bin/env python3
"""
OpenAI API key validation utility.

Runs two checks:
- Connectivity: GET /v1/models with the provided API key
- Minimal Responses API call with a tiny prompt against the first model from gpt5.config.json

Usage:
  python scripts/openai_key_check.py            # uses OPENAI_API_KEY from env
  python scripts/openai_key_check.py --key sk-...  # explicit key (not recommended; prefer env)
"""

import argparse
import json
import os
import sys
from typing import Optional

import httpx
from openai import OpenAI


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gpt5.config.json")


def mask_key(key: str) -> str:
    if not key:
        return "<empty>"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]} (len={len(key)})"


def load_first_model_from_config() -> Optional[str]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        models = cfg.get("models", [])
        if models:
            return models[0].get("id")
    except Exception:
        pass
    return None


def test_connectivity(key: str) -> bool:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get("https://api.openai.com/v1/models", headers=headers)
        print(f"Connectivity status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            total = len(data.get("data", []))
            print(f"Models listed: {total}")
            return True
        else:
            print(f"Connectivity error: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"Connectivity exception: {type(e).__name__}: {e}")
        return False


def test_minimal_response(key: str, model_id: Optional[str]) -> bool:
    if not model_id:
        print("Skip Responses test: no model id from config")
        return False
    try:
        client = OpenAI(api_key=key)
        resp = client.responses.create(
            model=model_id,
            input=[{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
            max_output_tokens=16,
        )
        text = getattr(resp, "output_text", "")
        print(f"Responses test OK: {bool(text)} (len={len(text)})")
        return True
    except Exception as e:
        print(f"Responses API error: {type(e).__name__}: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OpenAI API key")
    parser.add_argument("--key", dest="key", help="API key (prefer OPENAI_API_KEY env)")
    args = parser.parse_args()

    key = args.key or os.getenv("OPENAI_API_KEY", "")
    print(f"Using key: {mask_key(key)}")
    if not key:
        print("ERROR: OPENAI_API_KEY not provided")
        return 2

    ok_connect = test_connectivity(key)
    model_id = load_first_model_from_config()
    print(f"Config model: {model_id}")
    ok_resp = test_minimal_response(key, model_id)

    if ok_connect and ok_resp:
        print("Result: OK — key works for connectivity and Responses API")
        return 0
    elif ok_connect:
        print("Result: PARTIAL — connectivity OK, Responses call failed (model or permissions)")
        return 3
    else:
        print("Result: FAIL — connectivity failed (invalid key or network)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
