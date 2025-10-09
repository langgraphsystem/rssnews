"""
Retrieval Client — Unified interface to ranking_api.retrieve_for_analysis()
Implements query normalization, caching, metrics, and recovery telemetry.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from core.config import get_ask_config
from core.metrics import get_metrics_collector

logger = logging.getLogger(__name__)

# Conservative synonym expansion to keep queries on-topic
_SYN_ONTOLOGY: Dict[str, List[str]] = {
    "ceasefire": ["truce", "peace talks"],
    "armistice": ["ceasefire", "peace agreement"],
    "ai regulation": ["ai act", "artificial intelligence law", "ai law"],
    "sanction": ["sanctions", "penalties"],
    "election": ["vote", "poll"],
    # Lightweight typo-corrections for common entities
    # Appended to query to preserve user intent while improving recall
    "tump": ["trump"],
    "bidon": ["biden"],
    "pudin": ["putin"],
}

_OFFICIAL_SOURCES: List[str] = [
    "europa.eu",
    "ec.europa.eu",
    "whitehouse.gov",
    "state.gov",
    "defense.gov",
    "justice.gov",
    "gov.uk",
    "un.org",
    "who.int",
    "imf.org",
    "worldbank.org",
    "nato.int",
]


class RetrievalClient:
    """Client for the news-mode retrieval pipeline."""

    def __init__(self, ranking_api: Optional[Any] = None) -> None:
        self.ranking_api = ranking_api
        self._cache: Dict[str, tuple[List[Dict[str, Any]], float]] = {}
        self._cache_ttl = 300  # seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_ranking_api(self):
        if self.ranking_api is None:
            from ranking_api import RankingAPI  # Lazy import to avoid cycles

            self.ranking_api = RankingAPI()
        return self.ranking_api

    def _build_cache_key(
        self,
        normalized_query: str,
        window: str,
        lang: str,
        sources: Optional[List[str]],
        k_final: int,
        *,
        intent: str,
        official_only: bool,
        min_cosine: Optional[float],
        ensure_domain_diversity: bool,
        require_dates: bool,
        drop_offtopic: bool,
        after_date: Optional[str],
        before_date: Optional[str],
    ) -> str:
        parts = [
            normalized_query.lower(),
            window.lower(),
            lang.lower(),
            ",".join(sorted(sources or [])),
            str(k_final),
            intent,
            f"official={int(official_only)}",
            f"min={min_cosine:.3f}" if min_cosine is not None else "min=None",
            f"diversity={int(ensure_domain_diversity)}",
            f"dates={int(require_dates)}",
            f"drop={int(drop_offtopic)}",
            f"after={after_date or ''}",
            f"before={before_date or ''}",
        ]
        fingerprint = "|".join(parts)
        return hashlib.md5(fingerprint.encode("utf-8")).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        cached = self._cache.get(cache_key)
        if not cached:
            return None
        docs, ts = cached
        if (time.time() - ts) < self._cache_ttl:
            logger.debug("Retrieval cache hit for key=%s", cache_key)
            return docs
        self._cache.pop(cache_key, None)
        return None

    def _set_cache(self, cache_key: str, docs: List[Dict[str, Any]]) -> None:
        self._cache[cache_key] = (docs, time.time())

    def _expand_query_terms(self, query: str) -> List[str]:
        lowered = query.lower()
        expanded: List[str] = []
        for trigger, synonyms in _SYN_ONTOLOGY.items():
            if trigger in lowered:
                for synonym in synonyms:
                    if synonym not in lowered:
                        expanded.append(synonym)
        return expanded

    def build_search_query(
        self,
        *,
        query: Optional[str],
        intent: str,
        window: str,
        lang: str,
        domains: Optional[List[str]],
        official_only: bool,
        min_cosine: Optional[float],
    ) -> Dict[str, Any]:
        """Normalize the search payload passed to RankingAPI."""
        normalized_query = (query or "").strip()
        expanded_terms = self._expand_query_terms(normalized_query)
        if expanded_terms:
            normalized_query = f"{normalized_query} {' '.join(expanded_terms)}".strip()

        filters: Dict[str, Any] = {}
        if domains:
            filters["domains"] = domains
        if official_only:
            filters["domains"] = _OFFICIAL_SOURCES.copy()

        payload = {
            "normalized_query": normalized_query,
            "intent": intent,
            "window": window,
            "lang": lang,
            "filters": filters,
            "min_cosine": min_cosine,
        }
        return payload

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        *,
        query: Optional[str],
        window: str,
        lang: Literal["ru", "en", "auto"],
        k_final: int,
        intent: str,
        correlation_id: Optional[str],
        domains: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        official_only: bool = False,
        after_date: Optional[datetime] = None,
        before_date: Optional[datetime] = None,
        min_cosine_threshold: Optional[float] = None,
        ensure_domain_diversity: bool = True,
        require_dates: bool = True,
        drop_offtopic: bool = True,
        use_rerank: bool = True,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Execute retrieval and return docs with telemetry."""
        config = get_ask_config()
        metrics = get_metrics_collector()

        payload = self.build_search_query(
            query=query,
            intent=intent,
            window=window,
            lang=lang,
            domains=sources or domains,
            official_only=official_only,
            min_cosine=min_cosine_threshold,
        )

        normalized_query = payload["normalized_query"]
        effective_sources = payload["filters"].get("domains") if payload["filters"] else sources

        cache_key = self._build_cache_key(
            normalized_query,
            window,
            lang,
            effective_sources,
            k_final,
            intent=intent,
            official_only=official_only,
            min_cosine=min_cosine_threshold,
            ensure_domain_diversity=ensure_domain_diversity,
            require_dates=require_dates,
            drop_offtopic=drop_offtopic,
            after_date=after_date.isoformat() if after_date else None,
            before_date=before_date.isoformat() if before_date else None,
        )

        if use_cache:
            cached_docs = self._get_from_cache(cache_key)
            if cached_docs is not None:
                metrics.record_retrieval_cached(intent)
                return {"docs": cached_docs, "from_cache": True, "metrics": {}}

        metrics.record_retrieval_attempt(intent, window)

        api = self._get_ranking_api()

        result = await api.retrieve_for_analysis(
            query=normalized_query or None,
            window=window,
            lang=lang,
            sources=effective_sources,
            k_final=k_final,
            use_rerank=use_rerank,
            intent=intent,
            ensure_domain_diversity=ensure_domain_diversity,
            require_dates=require_dates,
            drop_offtopic=drop_offtopic,
            min_cosine=min_cosine_threshold,
            after_date=after_date,
            before_date=before_date,
            correlation_id=correlation_id,
        )

        docs = result.get("docs", [])
        telemetry = result.get("metrics", {})

        if use_cache and docs:
            self._set_cache(cache_key, docs)

        if docs:
            metrics.record_retrieval_success(window, len(docs))
        else:
            metrics.record_retrieval_no_candidates(window)

        timings = telemetry.get("timings", {})
        for timing_name, value_ms in timings.items():
            metrics.record_latency_metric(timing_name, value_ms)

        if telemetry.get("duplicates_removed"):
            metrics.record_duplicates_removed(telemetry["duplicates_removed"])
        if telemetry.get("domains_diversity_index") is not None:
            metrics.record_domains_diversity_index(telemetry["domains_diversity_index"])
        if telemetry.get("with_date_ratio") is not None:
            metrics.record_with_date_ratio(telemetry["with_date_ratio"])
        if telemetry.get("offtopic_dropped"):
            metrics.record_offtopic_dropped(telemetry["offtopic_dropped"])

        response = {
            "docs": docs,
            "metrics": telemetry,
            "from_cache": False,
            "window": window,
            "filters": payload["filters"],
        }
        return response

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        now = time.time()
        valid_entries = sum(1 for (_, ts) in self._cache.values() if (now - ts) < self._cache_ttl)
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "ttl_seconds": self._cache_ttl,
        }


_client_instance: Optional[RetrievalClient] = None


def get_retrieval_client() -> RetrievalClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = RetrievalClient()
    return _client_instance
