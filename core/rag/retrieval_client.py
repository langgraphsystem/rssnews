"""
Retrieval Client — Unified interface to ranking_api.retrieve_for_analysis()
Handles caching, normalization, and error handling
"""

import logging
import hashlib
import time
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

logger = logging.getLogger(__name__)


class RetrievalClient:
    """
    Client for unified retrieval interface
    Single point of access to ranking API for all analysis commands
    """

    def __init__(self, ranking_api=None):
        """
        Initialize retrieval client

        Args:
            ranking_api: Instance of RankingAPI (injected for testing)
        """
        self.ranking_api = ranking_api
        self._cache = {}  # Simple in-memory cache
        self._cache_ttl = 300  # 5 minutes

    def _get_ranking_api(self):
        """Lazy load ranking API"""
        if self.ranking_api is None:
            from ranking_api import RankingAPI
            self.ranking_api = RankingAPI()
        return self.ranking_api

    def _build_cache_key(
        self,
        query: Optional[str],
        window: str,
        lang: str,
        sources: Optional[List[str]],
        k_final: int
    ) -> str:
        """Build cache key from normalized inputs"""
        # Normalize inputs
        query_norm = (query or "").strip().lower()
        window_norm = window.lower()
        lang_norm = lang.lower()
        sources_norm = sorted(sources) if sources else []

        # Build string representation
        key_str = f"{query_norm}|{window_norm}|{lang_norm}|{','.join(sources_norm)}|{k_final}"

        # Hash for shorter key
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get from cache if not expired"""
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if (time.time() - timestamp) < self._cache_ttl:
                logger.info(f"Cache hit: {cache_key}")
                return cached_data
            else:
                # Expired
                del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: List[Dict[str, Any]]) -> None:
        """Set cache with timestamp"""
        self._cache[cache_key] = (data, time.time())

    async def retrieve(
        self,
        query: Optional[str] = None,
        window: Literal["6h", "12h", "24h", "1d", "3d", "1w", "2w", "1m", "3m", "6m", "1y"] = "24h",
        lang: Literal["ru", "en", "auto"] = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 5,
        use_rerank: bool = False,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Unified retrieval interface

        Args:
            query: Search query (optional for trends)
            window: Time window
            lang: Language filter
            sources: Source domains filter
            k_final: Number of documents to return
            use_rerank: Whether to use reranking
            use_cache: Whether to use cache

        Returns:
            List of documents with metadata
        """
        try:
            # Build cache key
            cache_key = self._build_cache_key(query, window, lang, sources, k_final)

            # Check cache
            if use_cache:
                cached = self._get_from_cache(cache_key)
                if cached is not None:
                    return cached

            # Get ranking API
            api = self._get_ranking_api()

            # Call retrieve_for_analysis
            results = await api.retrieve_for_analysis(
                query=query,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
                use_rerank=use_rerank
            )

            # Cache results
            if use_cache and results:
                self._set_cache(cache_key, results)

            logger.info(
                f"Retrieved {len(results)} docs: "
                f"query={query or 'none'}, window={window}, k_final={k_final}"
            )

            return results

        except Exception as e:
            logger.error(f"Retrieval failed: {e}", exc_info=True)
            return []

    def clear_cache(self) -> int:
        """Clear all cached results"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cached entries")
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = time.time()
        valid_entries = sum(
            1 for (_, ts) in self._cache.values()
            if (now - ts) < self._cache_ttl
        )

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "ttl_seconds": self._cache_ttl
        }


# Singleton instance
_client_instance: Optional[RetrievalClient] = None


def get_retrieval_client() -> RetrievalClient:
    """Get singleton retrieval client"""
    global _client_instance
    if _client_instance is None:
        _client_instance = RetrievalClient()
    return _client_instance