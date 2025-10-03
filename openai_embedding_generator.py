"""
OpenAI embedding generator using text-embedding-3-large (3072 dimensions)
"""

import os
import logging
import asyncio
from typing import List, Optional

logger = logging.getLogger(__name__)


class OpenAIEmbeddingGenerator:
    """Generate embeddings using OpenAI text-embedding-3-large model (3072 dimensions)"""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        self.timeout = int(os.getenv("EMBEDDING_TIMEOUT", "30"))
        self.dimensions = 3072

        # Initialize OpenAI client
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)

        logger.info(f"OpenAI embedding generator initialized: model={self.model}, dimensions={self.dimensions}")

    async def generate_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for list of texts

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (3072-dim each), or None for failed embeddings
        """
        if not texts:
            return []

        # Truncate very long texts (OpenAI limit is ~8191 tokens)
        truncated_texts = []
        for text in texts:
            if len(text) > 8000:  # Conservative character limit
                truncated_texts.append(text[:8000])
                logger.warning(f"Truncated text from {len(text)} to 8000 characters")
            else:
                truncated_texts.append(text)

        try:
            # OpenAI supports batch processing (up to 2048 texts)
            # For now, process in smaller batches for reliability
            batch_size = 100
            all_embeddings = []

            for i in range(0, len(truncated_texts), batch_size):
                batch = truncated_texts[i:i + batch_size]
                batch_embeddings = await self._generate_batch(batch)
                all_embeddings.extend(batch_embeddings)

                if (i + len(batch)) % 100 == 0:
                    logger.info(f"Generated embeddings: {i + len(batch)}/{len(truncated_texts)}")

            logger.info(f"Embedding generation complete: {len([e for e in all_embeddings if e])} successful / {len(texts)} total")
            return all_embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            # Return None for all texts if batch fails
            return [None] * len(texts)

    async def _generate_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for a batch of texts using OpenAI API

        Args:
            texts: Batch of texts (up to 100)

        Returns:
            List of embeddings (3072-dim)
        """
        try:
            # OpenAI API call (synchronous, but we wrap in async for consistency)
            response = await asyncio.to_thread(
                self.client.embeddings.create,
                input=texts,
                model=self.model
            )

            # Extract embeddings from response
            embeddings = [data.embedding for data in response.data]

            # Validate dimensions
            for i, emb in enumerate(embeddings):
                if len(emb) != self.dimensions:
                    logger.error(f"Unexpected embedding dimension: {len(emb)} (expected {self.dimensions})")
                    embeddings[i] = None

            logger.debug(f"Generated {len(embeddings)} embeddings via OpenAI API")
            return embeddings

        except Exception as e:
            logger.error(f"OpenAI API error for batch: {e}")
            return [None] * len(texts)

    def generate_embeddings_sync(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Synchronous wrapper for embedding generation

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings (3072-dim)
        """
        try:
            return asyncio.run(self.generate_embeddings(texts))
        except RuntimeError:
            # If event loop is already running
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.generate_embeddings(texts))

    async def test_connection(self) -> bool:
        """Test connection to OpenAI API and validate model

        Returns:
            True if connection successful and model returns correct dimensions
        """
        try:
            # Test with simple text
            embeddings = await self.generate_embeddings(["test"])

            if embeddings and embeddings[0] and len(embeddings[0]) == self.dimensions:
                logger.info(f"✅ OpenAI connection OK, model={self.model}, dimensions={len(embeddings[0])}")
                return True
            else:
                logger.error(f"❌ OpenAI returned invalid embedding: dimensions={len(embeddings[0]) if embeddings and embeddings[0] else 'None'}")
                return False

        except Exception as e:
            logger.error(f"❌ OpenAI connection test failed: {e}")
            return False

    def get_dimensions(self) -> int:
        """Get embedding dimensions for this model

        Returns:
            3072 for text-embedding-3-large
        """
        return self.dimensions
