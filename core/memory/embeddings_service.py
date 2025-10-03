"""
Embeddings Service — Generate vector embeddings for semantic search.
Supports OpenAI, Cohere, and local models.
"""

import hashlib
import logging
import os
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
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            api_key = self.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not provided")

            self._client = OpenAI(api_key=api_key)
            logger.info("OpenAI embeddings client initialized")

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
        """Generate embeddings using OpenAI"""
        try:
            # Use text-embedding-3-large (3072 dimensions)
            response = self._client.embeddings.create(
                input=texts,
                model="text-embedding-3-large"
            )

            embeddings = [data.embedding for data in response.data]
            logger.info(f"Generated {len(embeddings)} OpenAI embeddings")

            return embeddings

        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            raise

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
        dimensions = {
            "openai": 3072,  # text-embedding-3-large
            "cohere": 1024,  # embed-english-v3.0
            "local": 384     # all-MiniLM-L6-v2
        }
        return dimensions.get(self.provider, 3072)

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
