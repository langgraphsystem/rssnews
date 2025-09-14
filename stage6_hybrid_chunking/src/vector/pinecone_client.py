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

