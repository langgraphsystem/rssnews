"""
Embeddings Service — Generate vector embeddings for semantic search.
Supports OpenAI, Cohere, and local models.
"""

import hashlib
import logging
import os
import asyncio
import random
from typing import List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingsService:
    """Service for generating text embeddings"""

    def __init__(self, provider: str = "openai", api_key: Optional[str] = None):
        """
        Initialize embeddings service

        Args:
            provider: Provider name (openai, cohere, local)
            api_key: API key for the provider
        """
        self.provider = provider
        self.api_key = api_key
        self._client = None

        # Initialize client
        self._init_client()

    def _init_client(self):
        """Initialize embeddings client based on provider"""
        if self.provider == "openai":
            self._init_openai()
        elif self.provider == "cohere":
            self._init_cohere()
        elif self.provider == "local":
            self._init_local()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _init_openai(self):
        """Initialize async OpenAI client and model selection"""
        try:
            # Async client for non-blocking calls
            from openai import AsyncOpenAI  # type: ignore

            api_key = self.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not provided")

            # Preferred embeddings model (default: text-embedding-3-large, 3072-dim)
            self.openai_embedding_model = os.getenv(
                "OPENAI_EMBEDDING_MODEL",
                os.getenv("EMBEDDINGS_OPENAI_MODEL", "text-embedding-3-large")
            )

            # Batch and retry settings
            self.openai_batch_size = int(os.getenv("OPENAI_EMBEDDING_BATCH_SIZE", "100"))
            self.openai_max_retries = int(os.getenv("OPENAI_EMBEDDING_MAX_RETRIES", "3"))
            self.openai_timeout_s = float(os.getenv("EMBEDDING_TIMEOUT", "30"))

            self._aclient = AsyncOpenAI(api_key=api_key)
            logger.info(
                f"OpenAI async client initialized (model={self.openai_embedding_model}, "
                f"batch={self.openai_batch_size}, retries={self.openai_max_retries})"
            )

        except ImportError:
            logger.error("OpenAI library not installed. Install with: pip install openai")
            raise

    def _init_cohere(self):
        """Initialize Cohere client"""
        try:
            import cohere
            import os

            api_key = self.api_key or os.getenv("COHERE_API_KEY")
            if not api_key:
                raise ValueError("Cohere API key not provided")

            self._client = cohere.Client(api_key)
            logger.info("Cohere embeddings client initialized")

        except ImportError:
            logger.error("Cohere library not installed. Install with: pip install cohere")
            raise

    def _init_local(self):
        """Initialize local embeddings model (sentence-transformers)"""
        try:
            from sentence_transformers import SentenceTransformer

            # Use a small, fast model for local embeddings
            self._client = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Local embeddings model initialized: all-MiniLM-L6-v2")

        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise

    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text

        Args:
            text: Input text

        Returns:
            Embedding vector (list of floats)
        """
        if self.provider == "openai":
            result = await self._embed_openai([text])
            return result[0]
        elif self.provider == "cohere":
            result = await self._embed_cohere([text])
            return result[0]
        elif self.provider == "local":
            return self._embed_local([text])[0]
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        if self.provider == "openai":
            return await self._embed_openai(texts)
        elif self.provider == "cohere":
            return await self._embed_cohere(texts)
        elif self.provider == "local":
            return self._embed_local(texts)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI with async client, batching, and retries"""
        if not texts:
            return []

        model_name = getattr(self, "openai_embedding_model", None) or os.getenv(
            "OPENAI_EMBEDDING_MODEL",
            os.getenv("EMBEDDINGS_OPENAI_MODEL", "text-embedding-3-large")
        )

        batch_size = max(1, int(getattr(self, "openai_batch_size", 100)))
        max_retries = max(0, int(getattr(self, "openai_max_retries", 3)))
        timeout_s = float(getattr(self, "openai_timeout_s", 30.0))

        results: List[List[float]] = []

        # Helper: embed single batch with retries/backoff
        async def embed_batch(batch_inputs: List[str]) -> List[List[float]]:
            delay = 1.0
            attempt = 0
            last_err: Optional[Exception] = None
            while attempt <= max_retries:
                try:
                    coro = self._aclient.embeddings.create(model=model_name, input=batch_inputs)
                    resp = await asyncio.wait_for(coro, timeout=timeout_s)
                    return [d.embedding for d in resp.data]
                except Exception as e:  # rate limit / transient
                    last_err = e
                    attempt += 1
                    if attempt > max_retries:
                        break
                    # Exponential backoff with jitter
                    jitter = random.uniform(0, 0.25 * delay)
                    await asyncio.sleep(delay + jitter)
                    delay = min(delay * 2, 20.0)
            # Exhausted retries
            raise last_err or RuntimeError("OpenAI embeddings failed without exception detail")

        # Process all texts in batches
        for i in range(0, len(texts), batch_size):
            batch_inputs = texts[i:i + batch_size]
            batch_embeddings = await embed_batch(batch_inputs)
            results.extend(batch_embeddings)

        logger.info(
            f"Generated {len(results)} OpenAI embeddings (model={model_name}, batches={(len(texts)+batch_size-1)//batch_size})"
        )
        return results

    async def _embed_cohere(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Cohere"""
        try:
            # Use embed-english-v3.0 or embed-multilingual-v3.0
            response = self._client.embed(
                texts=texts,
                model="embed-english-v3.0",
                input_type="search_document"
            )

            embeddings = response.embeddings
            logger.info(f"Generated {len(embeddings)} Cohere embeddings")

            return embeddings

        except Exception as e:
            logger.error(f"Cohere embedding generation failed: {e}")
            raise

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local model"""
        try:
            # sentence-transformers returns numpy arrays
            embeddings_np = self._client.encode(texts, convert_to_numpy=True)

            # Convert to list of lists
            embeddings = embeddings_np.tolist()
            logger.info(f"Generated {len(embeddings)} local embeddings")

            return embeddings

        except Exception as e:
            logger.error(f"Local embedding generation failed: {e}")
            raise

    def get_dimensions(self) -> int:
        """Get embedding dimensions for this provider"""
        # Determine dimensions dynamically per provider/model
        if self.provider == "openai":
            model_name = getattr(self, "openai_embedding_model", None) or os.getenv(
                "OPENAI_EMBEDDING_MODEL",
                os.getenv("EMBEDDINGS_OPENAI_MODEL", "text-embedding-3-large")
            )
            return 3072 if model_name == "text-embedding-3-large" else 1536
        if self.provider == "cohere":
            return 1024
        if self.provider == "local":
            return 384
        return 1536

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score [0, 1]
        """
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)

        dot_product = np.dot(vec1_np, vec2_np)
        norm1 = np.linalg.norm(vec1_np)
        norm2 = np.linalg.norm(vec2_np)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Normalize to [0, 1]
        return (similarity + 1) / 2


class MockEmbeddingsService:
    """Deterministic mock embeddings for offline/testing environments"""

    def __init__(self, dimensions: int = 128):
        self.provider = "mock"
        self.dimensions = dimensions

    async def embed_text(self, text: str) -> List[float]:
        return self._hash_to_vector(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def _hash_to_vector(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vec = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
        if vec.size < self.dimensions:
            repeats = int(np.ceil(self.dimensions / vec.size))
            vec = np.tile(vec, repeats)
        vec = vec[: self.dimensions]
        norm = np.linalg.norm(vec)
        if norm:
            vec = vec / norm
        return vec.tolist()

    def get_dimensions(self) -> int:
        return self.dimensions

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        return EmbeddingsService.cosine_similarity(vec1, vec2)


def create_embeddings_service(
    provider: str = "openai",
    api_key: Optional[str] = None
) -> EmbeddingsService:
    """
    Factory function to create embeddings service

    Args:
        provider: Provider name (openai, cohere, local)
        api_key: Optional API key

    Returns:
        EmbeddingsService instance
    """
    mode = os.getenv("PHASE3_EMBEDDINGS_MODE", "").lower()
    if mode == "mock":
        logger.info("EmbeddingsService running in mock mode (env override)")
        return MockEmbeddingsService()

    try:
        service = EmbeddingsService(provider=provider, api_key=api_key)
        return service
    except (ImportError, ValueError) as exc:
        logger.warning("Falling back to MockEmbeddingsService: %s", exc)
        return MockEmbeddingsService()


# Convenience function
async def embed_text(text: str, provider: str = "openai") -> List[float]:
    """
    Quick embedding generation

    Args:
        text: Input text
        provider: Provider name

    Returns:
        Embedding vector
    """
    service = create_embeddings_service(provider=provider)
    return await service.embed_text(text)
