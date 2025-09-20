import os
import asyncio
import logging
from typing import Any, Optional, Dict


logger = logging.getLogger(__name__)


def _extract_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()
    out = getattr(response, "output", None) or []
    parts = []
    for item in out:
        for c in getattr(item, "content", []) or []:
            t = getattr(c, "text", None)
            if t:
                parts.append(t)
    return "\n".join(p.strip() for p in parts if p).strip()


async def generate_response_text(
    input: str | list,
    *,
    instructions: Optional[str] = None,
    model: str = "gpt-5",
    store: bool = False,
    max_output_tokens: Optional[int] = None,
    timeout: float = 90.0,
    retries: int = 3,
    previous_response_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("openai client not installed") from e

    client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            payload: Dict[str, Any] = {
                "model": model,
                "input": input,
                "store": store,
            }
            if instructions is not None:
                payload["instructions"] = instructions
            if previous_response_id is not None:
                payload["previous_response_id"] = previous_response_id
            if max_output_tokens is not None:
                payload["max_output_tokens"] = max_output_tokens
            if extra:
                payload.update(extra)

            resp = await client.responses.create(**payload)
            text = _extract_text(resp)
            if not text:
                raise RuntimeError("empty response text")
            return text
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "Responses API attempt %s failed: %s. Retrying in %ss...",
                    attempt + 1,
                    e,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                break
    assert last_err is not None
    raise last_err

