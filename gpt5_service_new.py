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
            raise FileNotFoundError(f"GPT-5 config file not found: {config_path}. Please ensure gpt5.config.json exists with valid model and routing configuration.")

        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                cfg = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in GPT-5 config file {config_path}: {e}. Please check the JSON syntax.")

        # Validate required config structure
        self._validate_config(cfg, config_path)

        self.config: Dict[str, Any] = cfg
        self.routing: Dict[str, str] = cfg.get("routing", {})
        models: List[Dict[str, Any]] = cfg.get("models", [])
        self.models: Dict[str, Dict[str, Any]] = {m["id"]: m for m in models if "id" in m}

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise KeyError("OPENAI_API_KEY environment variable not set. Please set your OpenAI API key.")

        self.client = OpenAI(api_key=api_key)

        # Default model
        self.default_model_id: str = preferred_model_id or self.routing.get("chat") or next(iter(self.models), "gpt-5")

    def _validate_config(self, cfg: Dict[str, Any], config_path: str) -> None:
        """Validate configuration structure and required fields"""
        if not isinstance(cfg, dict):
            raise ValueError(f"GPT-5 config must be a JSON object, got {type(cfg).__name__}")

        # Check for required models section
        if "models" not in cfg:
            raise ValueError(f"GPT-5 config {config_path} missing required 'models' section")

        models = cfg["models"]
        if not isinstance(models, list) or len(models) == 0:
            raise ValueError(f"GPT-5 config 'models' must be a non-empty list")

        # Validate each model has required id field
        for i, model in enumerate(models):
            if not isinstance(model, dict):
                raise ValueError(f"GPT-5 config model[{i}] must be an object")
            if "id" not in model:
                raise ValueError(f"GPT-5 config model[{i}] missing required 'id' field")

        # Check for routing section
        if "routing" not in cfg:
            raise ValueError(f"GPT-5 config {config_path} missing required 'routing' section")

        routing = cfg["routing"]
        if not isinstance(routing, dict):
            raise ValueError(f"GPT-5 config 'routing' must be an object")

        # Ensure routing refers to valid models
        model_ids = {m["id"] for m in models}
        for task, model_id in routing.items():
            if model_id not in model_ids:
                raise ValueError(f"GPT-5 config routing task '{task}' refers to unknown model '{model_id}'")

    def choose_model(self, task: str) -> str:
        return self.routing.get(task, self.default_model_id)

    def ping(self, timeout_seconds: int = 10) -> bool:
        """Ping GPT-5 service to validate API key and connectivity"""
        try:
            # Use minimal prompt and token limit for fast ping
            test_prompt = "ping"
            model_id = self.choose_model("chat")

            # Success is the absence of errors from the API, regardless of text content
            _ = self.generate_text_sync(
                test_prompt,
                model_id=model_id,
                max_output_tokens=16,
            )
            return True

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"GPT-5 ping failed: {e}")
            return False

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
        **kwargs,
    ) -> Dict[str, Any]:
        # Backward-compat for old callers: accept max_completion_tokens as alias
        if max_output_tokens is None and "max_completion_tokens" in kwargs:
            try:
                max_output_tokens = int(kwargs.pop("max_completion_tokens"))
            except Exception:
                # Remove invalid alias value silently
                kwargs.pop("max_completion_tokens", None)
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
            supports_temp = bool(self.models.get(model_id, {}).get("supports_temperature"))
            if supports_temp:
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

    def _extract_output_text(self, resp: Any, logger) -> str:
        """Best-effort extraction of text from a Responses API response object."""
        # 1) Direct convenience field
        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text

        # 2) Inspect resp.output items for message text
        try:
            output = getattr(resp, "output", None)
            if output:
                # Try Pydantic model_dump when available to unify access
                try:
                    # model_dump available on SDK pydantic models
                    output_dicts = [getattr(item, "model_dump", lambda: item)() for item in output]
                except Exception:
                    output_dicts = output

                collected: List[str] = []
                for item in output_dicts:
                    # item could be dict-like or model
                    itype = None
                    content = None
                    if isinstance(item, dict):
                        itype = item.get("type")
                        content = item.get("content") or item.get("summary")
                    else:
                        itype = getattr(item, "type", None)
                        content = getattr(item, "content", None) or getattr(item, "summary", None)

                    # Prefer message content blocks
                    if itype == "message" and content:
                        # content is a list of blocks; find text fields
                        try:
                            for block in content:
                                if isinstance(block, dict):
                                    t = block.get("text")
                                    if isinstance(t, str) and t.strip():
                                        collected.append(t)
                                else:
                                    t = getattr(block, "text", None)
                                    if isinstance(t, str) and t.strip():
                                        collected.append(t)
                        except Exception:
                            pass
                    # As a fallback, if reasoning contains a non-empty summary array, join it
                    if itype == "reasoning" and content:
                        try:
                            if isinstance(content, list) and content:
                                joined = "\n".join([c for c in content if isinstance(c, str)])
                                if joined.strip():
                                    collected.append(joined)
                        except Exception:
                            pass

                final = "\n".join([c for c in collected if c.strip()])
                if final.strip():
                    return final
        except Exception as ex:
            logger.info(f"🔍 [RAILWAY] Output inspection failed: {type(ex).__name__}: {ex}")

        # 3) As a last resort, try converting the whole response to dict and mining text
        try:
            to_dict = getattr(resp, "to_dict", None) or getattr(resp, "model_dump", None)
            if to_dict:
                data = to_dict()
                # Walk possible locations
                paths = [
                    ("output",),
                    ("message",),
                    ("content",),
                ]
                texts: List[str] = []
                def _mine(obj: Any):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k == "text" and isinstance(v, str) and v.strip():
                                texts.append(v)
                            _mine(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            _mine(v)
                _mine(data)
                if texts:
                    return "\n".join(texts)
        except Exception:
            pass

        return ""

    def _call_responses(self, payload: Dict[str, Any], *, stream: bool = False) -> str:
        import logging
        logger = logging.getLogger(__name__)

        logger.info("🔍 [RAILWAY] _call_responses started")
        logger.info(f"🔍 [RAILWAY] Payload keys: {list(payload.keys())}")
        logger.info(f"🔍 [RAILWAY] Stream: {stream}")

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
                text_final = "".join(chunks) or getattr(final, "output_text", "")
                return text_final
            except Exception as e:
                raise Exception(f"OpenAI Responses stream error: {type(e).__name__}: {e}") from e

        try:
            logger.info("🔍 [RAILWAY] Calling self.client.responses.create...")
            resp = self.client.responses.create(**payload)
            logger.info(f"🔍 [RAILWAY] Response received: {type(resp)}")
            logger.info(f"🔍 [RAILWAY] Response attributes: {dir(resp)}")

            output_text = self._extract_output_text(resp, logger)
            logger.info(f"🔍 [RAILWAY] output_text (extracted): '{output_text}' (length: {len(output_text)})")

            if not output_text:
                logger.info("🔍 [RAILWAY] No text from Responses. Trying GPT-5-mini (Responses) fallback...")
                # Build a second Responses request with chat model (gpt-5-mini)
                try:
                    payload2 = dict(payload)
                    payload2["model"] = self.routing.get("chat", "gpt-5-mini")
                    # Removing reasoning can help force plain text output on some models
                    if "reasoning" in payload2:
                        payload2.pop("reasoning", None)
                    resp2 = self.client.responses.create(**payload2)
                    output_text2 = self._extract_output_text(resp2, logger)
                    if output_text2 and output_text2.strip():
                        output_text = output_text2
                        logger.info(f"✅ [RAILWAY] GPT-5-mini fallback succeeded, length: {len(output_text)}")
                    else:
                        logger.info("⚠️ [RAILWAY] GPT-5-mini fallback returned empty text")
                except Exception as fe:
                    logger.error(f"❌ [RAILWAY] GPT-5-mini fallback failed: {type(fe).__name__}: {fe}")

            logger.info(f"✅ [RAILWAY] Final output_text: '{output_text}' (length: {len(output_text)})")
            return output_text

        except Exception as e:
            logger.error(f"❌ [RAILWAY] _call_responses error: {str(e)}")
            logger.error(f"❌ [RAILWAY] Error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [RAILWAY] _call_responses traceback:\n{traceback.format_exc()}")
            raise Exception(f"OpenAI Responses API error: {type(e).__name__}: {e}") from e

    # Sync core used by bot
    def generate_text_sync(
        self,
        prompt: str,
        *,
        model_id: Optional[str] = None,
        max_completion_tokens: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        verbosity: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        model = model_id or self.default_model_id
        eff_tokens = max_output_tokens if max_output_tokens is not None else max_completion_tokens
        payload = self._build_payload(
            message=prompt,
            model_id=model,
            max_output_tokens=eff_tokens,
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
        max_output_tokens: Optional[int] = None,
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
            max_output_tokens=max_output_tokens,
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
        import logging
        logger = logging.getLogger(__name__)

        logger.info("🔍 [RAILWAY] send_chat called")
        logger.info(f"🔍 [RAILWAY] Message length: {len(message)}")

        try:
            model_id = self.choose_model("chat")
            logger.info(f"🔍 [RAILWAY] Chosen chat model: {model_id}")
            result = self.generate_text_sync(message, model_id=model_id, **kwargs)
            logger.info(f"✅ [RAILWAY] send_chat succeeded, length: {len(result) if result else 0}")
            return result
        except Exception as e:
            logger.error(f"❌ [RAILWAY] send_chat failed: {str(e)}")
            import traceback
            logger.error(f"❌ [RAILWAY] send_chat traceback:\n{traceback.format_exc()}")
            raise

    def send_code(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("code")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_bulk(self, message: str, **kwargs) -> str:
        model_id = self.choose_model("bulk")
        return self.generate_text_sync(message, model_id=model_id, **kwargs)

    def send_analysis(self, message: str, **kwargs) -> str:
        import logging
        logger = logging.getLogger(__name__)

        logger.info("🔍 [RAILWAY] send_analysis called")
        logger.info(f"🔍 [RAILWAY] Message length: {len(message)}")
        logger.info(f"🔍 [RAILWAY] Kwargs: {kwargs}")

        try:
            model_id = self.choose_model("analysis")
            logger.info(f"🔍 [RAILWAY] Chosen model: {model_id}")

            result = self.generate_text_sync(message, model_id=model_id, **kwargs)
            logger.info(f"✅ [RAILWAY] send_analysis succeeded, result length: {len(result) if result else 0}")
            return result

        except Exception as e:
            logger.error(f"❌ [RAILWAY] send_analysis failed: {str(e)}")
            logger.error(f"❌ [RAILWAY] Error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [RAILWAY] send_analysis traceback:\n{traceback.format_exc()}")
            raise

    def send_sentiment(self, message: str, **kwargs) -> str:
        import logging
        logger = logging.getLogger(__name__)

        logger.info("🔍 [RAILWAY] send_sentiment called")
        logger.info(f"🔍 [RAILWAY] Message length: {len(message)}")

        try:
            model_id = self.choose_model("sentiment")
            logger.info(f"🔍 [RAILWAY] Chosen sentiment model: {model_id}")
            result = self.generate_text_sync(message, model_id=model_id, **kwargs)
            logger.info(f"✅ [RAILWAY] send_sentiment succeeded, length: {len(result) if result else 0}")
            return result
        except Exception as e:
            logger.error(f"❌ [RAILWAY] send_sentiment failed: {str(e)}")
            import traceback
            logger.error(f"❌ [RAILWAY] send_sentiment traceback:\n{traceback.format_exc()}")
            raise

    def send_insights(self, message: str, **kwargs) -> str:
        import logging
        logger = logging.getLogger(__name__)

        logger.info("🔍 [RAILWAY] send_insights called")
        logger.info(f"🔍 [RAILWAY] Message length: {len(message)}")

        try:
            model_id = self.choose_model("insights")
            logger.info(f"🔍 [RAILWAY] Chosen insights model: {model_id}")
            result = self.generate_text_sync(message, model_id=model_id, **kwargs)
            logger.info(f"✅ [RAILWAY] send_insights succeeded, length: {len(result) if result else 0}")
            return result
        except Exception as e:
            logger.error(f"❌ [RAILWAY] send_insights failed: {str(e)}")
            import traceback
            logger.error(f"❌ [RAILWAY] send_insights traceback:\n{traceback.format_exc()}")
            raise

    def list_available_models(self) -> List[str]:
        return list(self.models.keys())

    def get_model_info(self, model_id: str) -> Dict[str, Any]:
        return self.models.get(model_id, {})


def create_gpt5_service(preferred_model_id: Optional[str] = None) -> GPT5Service:
    """Create GPT-5 service with detailed Railway logging"""
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"🔍 [RAILWAY] create_gpt5_service called with model: {preferred_model_id}")

    # Check environment
    import os
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key:
        logger.info("🔍 [RAILWAY] OPENAI_API_KEY found (value hidden)")
    else:
        logger.error("❌ [RAILWAY] OPENAI_API_KEY not found in environment!")
        logger.error("❌ [RAILWAY] Available env vars:")
        for key in os.environ:
            if 'OPENAI' in key or 'API' in key:
                logger.error(f"❌ [RAILWAY] Found env: {key}")
        raise ValueError("OPENAI_API_KEY not set")

    try:
        logger.info("🔍 [RAILWAY] Creating GPT5Service instance...")
        service = GPT5Service(preferred_model_id=preferred_model_id, config_path=CONFIG_PATH)
        logger.info("✅ [RAILWAY] GPT5Service created successfully")
        return service
    except Exception as e:
        logger.error(f"❌ [RAILWAY] Failed to create GPT5Service: {str(e)}")
        logger.error(f"❌ [RAILWAY] Error type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [RAILWAY] Traceback:\n{traceback.format_exc()}")
        raise


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
                    response = service.generate_text_sync(test_message, model_id=model, max_output_tokens=50)
                    print(f"✅ {model}: {response}")
                except Exception as e:
                    print(f"❌ {model}: {e}")

        except Exception as e:
            print(f"Service initialization error: {e}")
