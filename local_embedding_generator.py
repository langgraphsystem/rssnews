"""
Local embedding generator using embeddinggemma via Ollama
"""

import os
import json
import logging
import asyncio
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class LocalEmbeddingGenerator:
    """Generate embeddings using embeddinggemma model via Ollama"""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
        self.timeout = int(os.getenv("EMBEDDING_TIMEOUT", "30"))

    async def generate_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for list of texts"""

        if not texts:
            return []

        embeddings = []

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
            for i, text in enumerate(texts):
                try:
                    embedding = await self._generate_single_embedding(client, text)
                    embeddings.append(embedding)

                    if (i + 1) % 5 == 0:
                        logger.info(f"Generated embeddings: {i + 1}/{len(texts)}")

                except Exception as e:
                    logger.error(f"Failed to generate embedding for text {i}: {e}")
                    embeddings.append(None)

        logger.info(f"Embedding generation complete: {len([e for e in embeddings if e])} successful / {len(texts)} total")
        return embeddings

    async def _generate_single_embedding(self, client: httpx.AsyncClient, text: str) -> Optional[List[float]]:
        """Generate single embedding via Ollama API"""

        # Truncate very long texts
        max_length = 2000  # Conservative limit for embeddings
        if len(text) > max_length:
            text = text[:max_length]

        payload = {
            "model": self.model,
            "prompt": text
        }

        try:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json=payload
            )

            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

            data = response.json()
            embedding = data.get("embedding")

            if not embedding or not isinstance(embedding, list):
                raise Exception(f"Invalid embedding response: {data}")

            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def generate_embeddings_sync(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Synchronous wrapper for embedding generation"""
        try:
            return asyncio.run(self.generate_embeddings(texts))
        except RuntimeError:
            # If event loop is already running
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.generate_embeddings(texts))

    async def test_connection(self) -> bool:
        """Test connection to Ollama and embeddinggemma model"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                # Test with simple text
                embedding = await self._generate_single_embedding(client, "test")
                if embedding and len(embedding) > 0:
                    logger.info(f"✅ embeddinggemma connection OK, vector dimensions: {len(embedding)}")
                    return True
                else:
                    logger.error("❌ embeddinggemma returned invalid embedding")
                    return False
        except Exception as e:
            logger.error(f"❌ embeddinggemma connection failed: {e}")
            return False