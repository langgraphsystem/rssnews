"""GPT-5 Service aligned with latest OpenAI Responses API and project config.

- Loads routing/model metadata from `gpt5.config.json`
- Uses `OpenAI.responses` API for all requests (streaming supported)
- Supports reasoning_effort and text verbosity when available in config
- Exposes async `generate_text(...)` for tests and sync helpers for bot
"""

import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional, List

from openai import OpenAI


CONFIG_PATH = "gpt5.config.json"


class GPT5Service:
    """Service for GPT-5 models using OpenAI Responses API."""

    def __init__(self, preferred_model_id: Optional[str] = None, config_path: str = CONFIG_PATH) -> None:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                cfg = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in config file: {e}")

        self.config: Dict[str, Any] = cfg
        self.routing: Dict[str, str] = cfg.get("routing", {})
        models: List[Dict[str, Any]] = cfg.get("models", [])
        self.models: Dict[str, Dict[str, Any]] = {m["id"]: m for m in models if "id" in m}

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise KeyError("OPENAI_API_KEY environment variable not set")

        self.client = OpenAI(api_key=api_key)

        # Default model
        self.default_model_id: str = preferred_model_id or self.routing.get("chat") or next(iter(self.models), "gpt-5")

    def choose_model(self, task: str) -> str:
        return self.routing.get(task, self.default_model_id)

    # Build Responses payload per config
    def _build_payload(
        self,
        message: str,
        model_id: str,
        *,
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        verbosity: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model_id,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": message}
                    ],
                }
            ],
        }

        if max_output_tokens is not None:
            payload["max_output_tokens"] = int(max_output_tokens)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if verbosity:
            payload["text"] = {"verbosity": verbosity}

        # Only include reasoning if supported
        supports_reasoning = bool(self.models.get(model_id, {}).get("supports_reasoning_effort"))
        if reasoning_effort and supports_reasoning:
            payload["reasoning"] = {"effort": reasoning_effort}

        if stream:
            payload["stream"] = True

        return payload

    def _call_responses(self, payload: Dict[str, Any], *, stream: bool = False) -> str:
        if stream:
            try:
                chunks: List[str] = []
                with self.client.responses.stream(**payload) as s:
                    for event in s:
                        if getattr(event, "type", "").endswith(".delta") and hasattr(event, "delta"):
                            piece = getattr(event, "delta", None)
                            if isinstance(piece, str) and piece:
                                print(piece, end="", flush=True)
                                chunks.append(piece)
                    s.until_done()
                    final = s.get_final_response()
                return "".join(chunks) or getattr(final, "output_text", "")
            except Exception as e:
                raise Exception(f"OpenAI Responses stream error: {type(e).__name__}: {e}") from e

        try:
            resp = self.client.responses.create(**payload)
            return getattr(resp, "output_text", "")
        except Exception as e:
            raise Exception(f"OpenAI Responses API error: {type(e).__name__}: {e}") from e

    # Sync core used by bot
    def generate_text_sync(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_completion_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        verbosity: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        model = model_id or self.default_model_id
        payload = self._build_payload(
            message=prompt,
            model_id=model,
            max_output_tokens=max_completion_tokens,
            temperature=temperature,
            verbosity=verbosity,
            reasoning_effort=reasoning_effort,
            stream=stream,
        )
        return self._call_responses(payload, stream=stream)

    # Async wrapper used by tests
    async def generate_text(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_completion_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        verbosity: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        return await asyncio.to_thread(
            self.generate_text_sync,
            prompt,
            model_id=model_id,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
            verbosity=verbosity,
            reasoning_effort=reasoning_effort,
            stream=stream,
        )

    # Convenience methods with routing
    def send_qa(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("qa")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_chat(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("chat")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_code(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("code")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_bulk(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("bulk")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_analysis(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("analysis")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_sentiment(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("sentiment")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_insights(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("insights")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def list_available_models(self) -> List[str]:
        return list(self.models.keys())

    def get_model_info(self, model_id: str) -> Dict[str, Any]:
        return self.models.get(model_id, {})


def create_gpt5_service(preferred_model_id: Optional[str] = None) -> GPT5Service:
    return GPT5Service(preferred_model_id=preferred_model_id, config_path=CONFIG_PATH)


if __name__ == "__main__":
    # Demo usage
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])

        try:
            service = GPT5Service()
            print(f"Available models: {service.list_available_models()}")

            response = service.send_chat(message)
            print(f"Response: {response}")

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        # Demo: Show available models
        try:
            service = GPT5Service()
            print("🤖 GPT-5 Service Initialized Successfully!")
            print(f"📋 Available models: {service.list_available_models()}")

            # Test each model with a simple message
            test_message = "Say hello in one sentence"

            for model in service.list_available_models():
                print(f"\n🧪 Testing {model}...")
                try:
                    response = service.generate_text_sync(test_message, model_id=model, max_completion_tokens=50)
                    print(f"✅ {model}: {response}")
                except Exception as e:
                    print(f"❌ {model}: {e}")

        except Exception as e:
            print(f"Service initialization error: {e}")
