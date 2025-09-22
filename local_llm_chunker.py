"""
Local LLM chunker using Qwen2.5-coder:3b for smart article chunking
"""

import os
import json
import logging
import asyncio
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SimpleOllamaClient:
    """Simple Ollama API client for chunking"""

    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def generate(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.1) -> str:
        """Generate text using Ollama API"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Hint to Ollama to produce strict JSON output
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_p": 0.9
            }
        }

        response = await self.client.post(
            f"{self.base_url}/api/generate",
            json=payload
        )

        if response.status_code != 200:
            raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

        data = response.json()
        resp = data.get("response", "")
        # Some models wrap JSON in code fences; strip them here
        if isinstance(resp, str) and resp.strip().startswith("```"):
            # remove leading and trailing fences
            s = resp.strip()
            # Remove language hint if present e.g. ```json
            if s.startswith("```"):
                s = s[3:]
                s = s[s.find("\n") + 1:] if "\n" in s else s
            if s.endswith("```"):
                s = s[:-3]
            resp = s
        return (resp or "").strip()


class LocalLLMChunker:
    """Smart chunker using local Qwen2.5-coder:3b model via Ollama"""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
        self.target_words = int(os.getenv("CHUNK_TARGET_WORDS", "400"))
        self.max_chunks = int(os.getenv("MAX_CHUNKS_PER_ARTICLE", "20"))

    async def create_chunks(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create smart chunks using local LLM"""

        if not text or len(text) < 100:
            return []

        # Truncate very long texts to avoid token limits
        max_text_length = 8000  # ~2000 tokens for Qwen2.5-coder:3b
        if len(text) > max_text_length:
            text = text[:max_text_length] + "..."

        async with SimpleOllamaClient(
            base_url=self.base_url,
            model=self.model,
            timeout=60
        ) as client:

            # Build chunking prompt
            prompt = self._build_chunking_prompt(text, metadata)

            try:
                response = await client.generate(
                    prompt=prompt,
                    max_tokens=2000,
                    temperature=0.1  # Low temperature for consistent chunking
                )

                chunks = self._parse_chunks_response(response, text)

                logger.info(
                    f"Smart chunking completed: {len(chunks)} chunks, "
                    f"model: {self.model}"
                )

                return chunks

            except Exception as e:
                # Don't fail the whole article on chunking issues; log and return no chunks
                logger.error(f"LLM chunking failed: {e}")
                return []

    def _build_chunking_prompt(self, text: str, metadata: Dict[str, Any]) -> str:
        """Build prompt for smart chunking"""

        category = metadata.get('category', 'news')
        title = metadata.get('title', '')[:100]
        language = metadata.get('language', 'en')

        prompt = f"""Analyze this {category} article and split it into logical chunks of ~{self.target_words} words each.

Title: {title}
Language: {language}

Consider:
- Natural paragraph boundaries
- Topic transitions
- Logical flow of information
- Keep related information together
- Avoid breaking sentences

Text to chunk:
{text}

Return ONLY a JSON array with chunks:
[
    {{"text": "chunk content...", "topic": "brief topic", "type": "intro|body|conclusion"}},
    {{"text": "chunk content...", "topic": "brief topic", "type": "body"}}
]

Maximum {self.max_chunks} chunks. Focus on quality over quantity."""

        return prompt

    def _parse_chunks_response(self, response: str, original_text: str) -> List[Dict[str, Any]]:
        """Parse LLM response into chunk objects"""

        try:
            # Try to extract JSON from response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1

            if json_start == -1 or json_end == 0:
                # Try to recover from code fences or text before JSON
                # If still not found, return empty chunk list instead of raising
                raise ValueError("No JSON array found in response")

            json_str = response[json_start:json_end]
            chunks_data = json.loads(json_str)

            if not isinstance(chunks_data, list):
                raise ValueError("Expected JSON array")

            chunks = []
            char_offset = 0

            for i, chunk_data in enumerate(chunks_data):
                if i >= self.max_chunks:
                    break

                text_chunk = chunk_data.get('text', '').strip()
                if not text_chunk or len(text_chunk) < 20:
                    continue

                # Find approximate position in original text
                chunk_start = original_text.find(text_chunk[:50], char_offset)
                if chunk_start == -1:
                    chunk_start = char_offset

                chunk_end = chunk_start + len(text_chunk)
                char_offset = chunk_end

                word_count = len(text_chunk.split())

                chunk = {
                    'chunk_index': i,
                    'text': text_chunk,
                    'word_count_chunk': word_count,
                    'char_start': chunk_start,
                    'char_end': chunk_end,
                    'semantic_type': chunk_data.get('type', 'body'),
                    'boundary_confidence': 0.9,  # High confidence from LLM
                    'llm_topic': chunk_data.get('topic', ''),
                    'chunking_method': 'local_llm'
                }

                chunks.append(chunk)

            return chunks

        except Exception as e:
            logger.error(f"Failed to parse LLM chunks response: {e}")
            # Return safe fallback: no chunks
            return []

