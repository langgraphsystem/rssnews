import os
from typing import List, Dict, Optional

try:
    from pinecone import Pinecone  # type: ignore
except Exception as e:  # pragma: no cover
    Pinecone = None  # type: ignore


class PineconeClient:
    """Minimal Pinecone wrapper used by the index stage.

    Reads configuration from environment variables:
      - PINECONE_API_KEY (required to enable Pinecone mode)
      - PINECONE_INDEX (required)
      - PINECONE_REGION (optional for serverless; defaults to us-east-1-aws)
      - PINECONE_NAMESPACE (optional)
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("PINECONE_API_KEY")
        self.index_name = os.environ.get("PINECONE_INDEX")
        self.region = os.environ.get("PINECONE_REGION", "us-east-1-aws")
        self.namespace = os.environ.get("PINECONE_NAMESPACE") or None
        self._pc = None
        self._index = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.index_name)

    def connect(self) -> bool:
        if not self.enabled:
            return False
        if Pinecone is None:
            return False
        try:
            self._pc = Pinecone(api_key=self.api_key)
            # Assume index exists; do not auto-create here to keep side effects minimal
            self._index = self._pc.Index(self.index_name)
            # Touch index to ensure it is reachable
            self._index.describe_index_stats(namespace=self.namespace)  # type: ignore
            return True
        except Exception:
            return False

    def upsert(self, vectors: List[Dict]) -> int:
        """Upsert vectors in batches; returns count of vectors upserted.

        Vector format: { 'id': str, 'values': List[float], 'metadata': Dict }
        """
        if not self._index:
            return 0
        total = 0
        batch = 100
        for i in range(0, len(vectors), batch):
            chunk = vectors[i : i + batch]
            self._index.upsert(vectors=chunk, namespace=self.namespace)  # type: ignore
            total += len(chunk)
        return total

    def search(self, query_vector: List[float], top_k: int = 10, include_metadata: bool = True) -> List[Dict]:
        """Search for similar vectors in Pinecone.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            include_metadata: Whether to include metadata in results

        Returns:
            List of search results with id, score, and metadata
        """
        if not self._index or not query_vector:
            return []

        try:
            response = self._index.query(
                vector=query_vector,
                top_k=top_k,
                include_metadata=include_metadata,
                namespace=self.namespace
            )

            results = []
            if hasattr(response, 'matches'):
                for match in response.matches:
                    result = {
                        'id': match.id,
                        'score': float(match.score),
                    }
                    if include_metadata and hasattr(match, 'metadata') and match.metadata:
                        result['metadata'] = match.metadata
                    results.append(result)

            return results

        except Exception as e:
            print(f"Pinecone search failed: {e}")
            return []

