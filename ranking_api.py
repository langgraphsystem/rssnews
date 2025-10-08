"""
Production Ranking API Service
Main orchestrator for search ranking, deduplication, and explainability
"""

import os
import sys
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.production_db_client import ProductionDBClient, SearchLogEntry
from ranking_service.scorer import ProductionScorer, ScoringWeights
from ranking_service.deduplication import DeduplicationEngine
from ranking_service.diversification import MMRDiversifier
from core.config import get_ask_config
from core.metrics import get_metrics_collector
from ranking_service.explainability import ExplainabilityEngine
from openai_embedding_generator import OpenAIEmbeddingGenerator
from caching_service import CachingService

logger = logging.getLogger(__name__)


@dataclass
class SearchRequest:
    """Search request structure"""
    query: str
    method: str = 'hybrid'  # 'fts', 'semantic', 'hybrid'
    limit: int = 10
    offset: int = 0
    filters: Dict[str, Any] = None
    user_id: str = None
    session_id: str = None
    time_range: str = None  # '24h', '3d', '7d', '30d'
    sources: List[str] = None
    english_only: bool = True
    explain: bool = False


@dataclass
class SearchResponse:
    """Search response structure"""
    query: str
    query_normalized: str
    total_results: int
    results: List[Dict[str, Any]]
    response_time_ms: int
    search_method: str
    explanations: List[Dict[str, Any]] = None
    diversity_metrics: Dict[str, Any] = None
    applied_filters: Dict[str, Any] = None


class RankingAPI:
    """Production ranking API with full pipeline"""

    def __init__(self):
        self.config = get_ask_config()
        self.metrics = get_metrics_collector()

        self.db = ProductionDBClient()
        self.scorer = ProductionScorer(config=self.config)
        self.dedup_engine = DeduplicationEngine()
        self.diversifier = MMRDiversifier()
        self.explainer = ExplainabilityEngine()
        self.embedding_generator = OpenAIEmbeddingGenerator()
        self.cache = CachingService()

        # Load dynamic weights from database / config overrides
        self._load_scoring_weights()

    def _load_scoring_weights(self):
        """Load scoring weights from config, environment, and database overrides."""
        weights = self.scorer.weights

        # Config defaults
        try:
            if self.config:
                weights.semantic = getattr(self.config, 'semantic_weight', weights.semantic)
                weights.fts = getattr(self.config, 'fts_weight', weights.fts)
                weights.freshness = getattr(self.config, 'freshness_weight', weights.freshness)
                weights.source = getattr(self.config, 'source_weight', weights.source)
                weights.min_cosine_threshold = getattr(self.config, 'min_cosine_threshold', weights.min_cosine_threshold)
                weights.require_dates_in_top_n = getattr(self.config, 'date_penalties_enabled', weights.require_dates_in_top_n)
                weights.date_penalty_factor = getattr(self.config, 'date_penalty_factor', weights.date_penalty_factor)
                weights.max_per_domain = getattr(self.config, 'max_per_domain', weights.max_per_domain)
        except AttributeError:
            pass

        # Environment overrides
        weights.semantic = float(os.getenv('W_SEMANTIC', weights.semantic))
        weights.fts = float(os.getenv('W_FTS', weights.fts))
        weights.freshness = float(os.getenv('W_FRESH', weights.freshness))
        weights.source = float(os.getenv('W_SOURCE', weights.source))
        if os.getenv('ASK_MIN_COSINE'):
            try:
                weights.min_cosine_threshold = float(os.getenv('ASK_MIN_COSINE'))
            except ValueError:
                logger.warning('Invalid ASK_MIN_COSINE value; keeping %s', weights.min_cosine_threshold)
        if os.getenv('ASK_MAX_PER_DOMAIN'):
            try:
                weights.max_per_domain = int(os.getenv('ASK_MAX_PER_DOMAIN'))
            except ValueError:
                logger.warning('Invalid ASK_MAX_PER_DOMAIN; keeping %s', weights.max_per_domain)

        # Database overrides
        try:
            db_weights = self.db.get_scoring_weights()
            if db_weights:
                weights.semantic = db_weights.get('semantic', weights.semantic)
                weights.fts = db_weights.get('fts', weights.fts)
                weights.freshness = db_weights.get('freshness', weights.freshness)
                weights.source = db_weights.get('source', weights.source)
                weights.tau_hours = db_weights.get('tau_hours', weights.tau_hours)
                weights.max_per_domain = db_weights.get('max_per_domain', weights.max_per_domain)
                weights.max_per_article = db_weights.get('max_per_article', weights.max_per_article)
                logger.info(f"Loaded scoring weights (DB overrides): {db_weights}")
        except Exception as exc:
            logger.warning(f"Failed to load scoring weights, using configured defaults: {exc}")
    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent processing"""
        if not query:
            return ""

        # Basic normalization
        normalized = query.strip().lower()

        # Remove extra whitespace
        normalized = ' '.join(normalized.split())

        return normalized

    def _apply_time_filter(self, base_query: str, time_range: str) -> str:
        """Apply time range filter to SQL query"""
        if not time_range:
            return base_query

        time_conditions = {
            '24h': "AND published_at >= NOW() - INTERVAL '24 hours'",
            '3d': "AND published_at >= NOW() - INTERVAL '3 days'",
            '7d': "AND published_at >= NOW() - INTERVAL '7 days'",
            '30d': "AND published_at >= NOW() - INTERVAL '30 days'"
        }

        time_condition = time_conditions.get(time_range, "")
        if time_condition:
            # Insert time condition before ORDER BY
            if "ORDER BY" in base_query:
                parts = base_query.split("ORDER BY")
                return f"{parts[0]} {time_condition} ORDER BY {parts[1]}"
            else:
                return f"{base_query} {time_condition}"

        return base_query

    async def _search_fts(self, query: str, limit: int,
                         filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Perform FTS search"""
        try:
            # Use existing FTS search from pg_client
            sources = filters.get('sources', []) if filters else []
            since_days = None

            # Convert time_range to since_days
            time_range = filters.get('time_range') if filters else None
            if time_range:
                time_map = {'24h': 1, '3d': 3, '7d': 7, '30d': 30}
                since_days = time_map.get(time_range)

            results = self.db.search_chunks_fts_ts(
                tsquery=None,
                plainto=query,
                sources=sources,
                since_days=since_days,
                limit=limit * 3  # Get more candidates
            )

            # Add FTS scores
            for result in results:
                result['fts_score'] = result.get('fts_rank', 0.5)
                result['semantic_score'] = 0.5  # Default for FTS-only

            return results

        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            return []

    async def _search_semantic(self, query: str, limit: int,
                              filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Perform semantic search"""
        try:
            # Generate query embedding
            query_embeddings = await self.embedding_generator.generate_embeddings([query])
            if not query_embeddings or not query_embeddings[0]:
                logger.error("Failed to generate query embedding")
                return []

            query_embedding = query_embeddings[0]

            # Search by similarity (no threshold - get top results)
            results = self.db.search_chunks_by_similarity(
                query_embedding=query_embedding,
                limit=limit * 3,  # Get more candidates
                similarity_threshold=0.0  # No threshold - get all results sorted by similarity
            )

            # Add semantic scores
            for result in results:
                result['semantic_score'] = result.get('similarity', 0.5)
                result['fts_score'] = 0.5  # Default for semantic-only

            return results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def _search_hybrid(self, query: str, limit: int,
                            filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Perform hybrid search (FTS + Semantic)"""
        try:
            # Generate query embedding
            query_embeddings = await self.embedding_generator.generate_embeddings([query])
            if not query_embeddings or not query_embeddings[0]:
                logger.warning("Failed to generate query embedding, falling back to FTS")
                return await self._search_fts(query, limit, filters)

            query_embedding = query_embeddings[0]

            # Use existing hybrid search
            results = self.db.hybrid_search(
                query=query,
                query_vector=query_embedding,
                limit=limit * 3,  # Get more candidates
                alpha=0.5  # Balance between FTS and semantic
            )

            # Normalize scores
            for result in results:
                result['semantic_score'] = result.get('similarity', result.get('semantic_score', 0.5))
                result['fts_score'] = result.get('fts_rank', result.get('fts_score', 0.5))

            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # Fallback to FTS
            return await self._search_fts(query, limit, filters)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Main search API endpoint"""
        start_time = time.time()

        try:
            # Normalize query
            query_normalized = self._normalize_query(request.query)
            if not query_normalized:
                return SearchResponse(
                    query=request.query,
                    query_normalized=query_normalized,
                    total_results=0,
                    results=[],
                    response_time_ms=0,
                    search_method=request.method
                )

            # Check cache first (if no offset requested)
            if request.offset == 0 and not request.explain:
                cached_results = self.cache.get_cached_search_results(
                    query_normalized, request.method, request.filters
                )
                if cached_results:
                    response_time = int((time.time() - start_time) * 1000)
                    logger.info(f"Cache hit for '{request.query}' ({response_time}ms)")

                    # Trim to requested limit
                    final_results = cached_results[:request.limit]

                    return SearchResponse(
                        query=request.query,
                        query_normalized=query_normalized,
                        total_results=len(cached_results),
                        results=final_results,
                        response_time_ms=response_time,
                        search_method=request.method,
                        applied_filters={'cached': True}
                    )

            logger.info(f"Search request: '{request.query}' method={request.method} limit={request.limit}")

            # Step 1: Retrieve candidates
            if request.method == 'fts':
                candidates = await self._search_fts(query_normalized, request.limit, request.filters)
            elif request.method == 'semantic':
                candidates = await self._search_semantic(query_normalized, request.limit, request.filters)
            else:  # hybrid
                candidates = await self._search_hybrid(query_normalized, request.limit, request.filters)

            if not candidates:
                response_time = int((time.time() - start_time) * 1000)
                return SearchResponse(
                    query=request.query,
                    query_normalized=query_normalized,
                    total_results=0,
                    results=[],
                    response_time_ms=response_time,
                    search_method=request.method
                )

            # Step 2: Apply production scoring
            scored_results, _scoring_summary = self.scorer.score_and_rank(candidates, query_normalized)

            # Step 3: Apply deduplication (canonicalization)
            if len(scored_results) > 1:
                deduplicated_results = self.dedup_engine.canonicalize_articles(scored_results)
            else:
                deduplicated_results = scored_results

            # Step 4: Apply diversification (MMR)
            diversified_results = self.diversifier.diversify_results(
                deduplicated_results,
                max_results=request.limit * 2  # Get more for final filtering
            )

            # Step 5: Apply final limits and offset
            final_results = diversified_results[request.offset:request.offset + request.limit]

            # Step 6: Generate explanations if requested
            explanations = []
            if request.explain and final_results:
                explanations = self.explainer.bulk_explain(final_results, query_normalized)

            # Step 7: Calculate diversity metrics
            diversity_metrics = self.diversifier.analyze_diversity(final_results)

            # Calculate response time
            response_time = int((time.time() - start_time) * 1000)

            # Step 8: Log search for analytics
            if request.user_id:
                search_log = SearchLogEntry(
                    user_id=request.user_id,
                    query=request.query,
                    query_normalized=query_normalized,
                    search_method=request.method,
                    filters=request.filters or {},
                    results_count=len(final_results),
                    response_time_ms=response_time,
                    top_result_ids=[r.get('id', r.get('article_id')) for r in final_results[:5]],
                    session_id=request.session_id
                )
                self.db.log_search(search_log)

            # Cache results if successful and not offset-based
            if (request.offset == 0 and not request.explain and
                len(final_results) > 0 and response_time < 2000):  # Cache fast, successful searches
                try:
                    self.cache.cache_search_results(
                        query_normalized, request.method, request.filters,
                        final_results[:20]  # Cache up to 20 results
                    )
                except Exception as cache_error:
                    logger.debug(f"Failed to cache results: {cache_error}")

            # Prepare response
            response = SearchResponse(
                query=request.query,
                query_normalized=query_normalized,
                total_results=len(candidates),
                results=final_results,
                response_time_ms=response_time,
                search_method=request.method,
                explanations=explanations,
                diversity_metrics=diversity_metrics,
                applied_filters=request.filters
            )

            logger.info(f"Search completed: {len(candidates)} -> {len(final_results)} results in {response_time}ms")
            return response

        except Exception as e:
            logger.error(f"Search failed: {e}")
            response_time = int((time.time() - start_time) * 1000)
            return SearchResponse(
                query=request.query,
                query_normalized=query_normalized or "",
                total_results=0,
                results=[],
                response_time_ms=response_time,
                search_method=request.method,
                applied_filters={'error': str(e)}
            )

    async def retrieve_for_analysis(
        self,
        query: Optional[str] = None,
        window: str = "24h",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 5,
        use_rerank: bool = False,
        intent: str = "news_current_events",
        ensure_domain_diversity: bool = True,
        require_dates: bool = True,
        drop_offtopic: bool = True,
        min_cosine: Optional[float] = None,
        after_date: Optional[datetime] = None,
        before_date: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve documents for /ask news-mode with ranking and diversity."""
        overall_start = time.time()
        metrics_payload: Dict[str, Any] = {"timings": {}}

        try:
            window_key = (window or "7d").lower()
            window_hours_map = {
                "1h": 1,
                "6h": 6,
                "12h": 12,
                "24h": 24,
                "1d": 24,
                "3d": 72,
                "7d": 168,
                "1w": 168,
                "14d": 336,
                "2w": 336,
                "30d": 720,
                "1m": 720,
                "3m": 2160,
                "6m": 4320,
                "1y": 8760,
            }
            hours = window_hours_map.get(window_key, 168 if window_key in {"7d", "1w"} else 24)

            filters: Dict[str, Any] = {}
            if sources:
                filters["sources"] = sources
            if lang and lang != "auto":
                filters["lang"] = lang

            normalized_query = self._normalize_query(query or "")
            query_embedding = None
            if normalized_query:
                try:
                    embeddings = await self.embedding_generator.generate_embeddings([normalized_query])
                    if embeddings and embeddings[0]:
                        query_embedding = embeddings[0]
                except Exception as embed_err:
                    logger.warning("Failed to generate query embedding: %s", embed_err)

            db_start = time.time()
            raw_results = await self.db.search_with_time_filter(
                query=normalized_query,
                query_embedding=query_embedding,
                hours=hours,
                limit=max(k_final * 4, 40),
                filters=filters,
                after_date=after_date,
                before_date=before_date,
                lang=lang,
            )
            metrics_payload["timings"]["db_query_ms"] = int((time.time() - db_start) * 1000)

            logger.info(
                "[%s] retrieve_for_analysis window=%s intent=%s results=%d",
                correlation_id or "ask",
                window,
                intent,
                len(raw_results),
            )

            if not raw_results:
                metrics_payload.update(
                    {
                        "duplicates_removed": 0,
                        "domains_diversity_index": 0.0,
                        "with_date_ratio": 0.0,
                        "offtopic_dropped": 0,
                    }
                )
                metrics_payload["timings"]["ranking_ms"] = 0
                metrics_payload["timings"]["end_to_end_ms"] = int((time.time() - overall_start) * 1000)
                return {"docs": [], "metrics": metrics_payload}

            ranking_start = time.time()
            scored_results, scoring_summary = self.scorer.score_and_rank(
                raw_results,
                normalized_query,
                apply_caps=True,
                intent=intent,
                filter_offtopic=drop_offtopic,
                apply_category_penalties=True,
                apply_date_penalties=require_dates,
                min_cosine=min_cosine,
            )
            metrics_payload["timings"]["ranking_ms"] = int((time.time() - ranking_start) * 1000)

            deduped_results = self.dedup_engine.canonicalize_articles(scored_results)
            duplicates_removed = len(scored_results) - len(deduped_results)
            metrics_payload["duplicates_removed"] = max(0, duplicates_removed)

            diversified_results = self.diversifier.diversify_results(
                deduped_results,
                max_results=max(k_final * 2, 10),
                ensure_domain_div=ensure_domain_diversity,
            )

            final_docs = diversified_results[:k_final]
            if require_dates:
                final_docs = self._enforce_date_requirement(final_docs)
            if ensure_domain_diversity:
                final_docs = self._ensure_minimum_domain_diversity(final_docs, diversified_results)

            metrics_payload["domains_diversity_index"] = self._compute_domain_diversity_index(diversified_results, top_k=10)
            metrics_payload["with_date_ratio"] = self._compute_with_date_ratio(diversified_results, top_k=10)
            metrics_payload["offtopic_dropped"] = scoring_summary.get("offtopic_dropped", 0)
            metrics_payload["category_penalties"] = scoring_summary.get("category_penalties", 0)
            metrics_payload["date_penalties"] = scoring_summary.get("date_penalties", 0)
            metrics_payload["timings"]["end_to_end_ms"] = int((time.time() - overall_start) * 1000)

            return {"docs": final_docs, "metrics": metrics_payload}

        except Exception as exc:
            logger.error(f"retrieve_for_analysis failed: {exc}", exc_info=True)
            metrics_payload.setdefault("timings", {})["end_to_end_ms"] = int((time.time() - overall_start) * 1000)
            metrics_payload["error"] = str(exc)
            return {"docs": [], "metrics": metrics_payload}
    def _extract_domain(self, doc: Dict[str, Any]) -> str:
        domain = doc.get("source_domain") or doc.get("domain") or doc.get("source") or ""
        if not domain and doc.get("url"):
            try:
                from urllib.parse import urlparse

                parsed = urlparse(doc["url"])
                domain = parsed.netloc
            except Exception:
                domain = ""
        return (domain or "").lower()

    def _enforce_date_requirement(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not docs:
            return []
        dated = [doc for doc in docs if doc.get("published_at")]
        undated = [doc for doc in docs if not doc.get("published_at")]
        return dated + undated

    def _ensure_minimum_domain_diversity(
        self,
        primary: List[Dict[str, Any]],
        pool: List[Dict[str, Any]],
        *,
        min_unique: int = 3,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not primary or min_unique <= 1:
            return primary

        top_range = min(top_k, len(primary))
        domains = [self._extract_domain(doc) for doc in primary]
        unique_top = {d for d in domains[:top_range] if d}
        if len(unique_top) >= min_unique:
            return primary

        replacement_candidates: List[Dict[str, Any]] = []
        seen = set(unique_top)
        for doc in pool[top_range:]:
            dom = self._extract_domain(doc)
            if dom and dom not in seen:
                replacement_candidates.append(doc)
                seen.add(dom)
                if len(seen) >= min_unique:
                    break

        if not replacement_candidates:
            return primary

        counts = {}
        for dom in domains[:top_range]:
            counts[dom] = counts.get(dom, 0) + 1

        repl_iter = iter(replacement_candidates)
        for idx in range(top_range - 1, -1, -1):
            dom = domains[idx]
            if counts.get(dom, 0) > 1:
                try:
                    candidate = next(repl_iter)
                except StopIteration:
                    break
                candidate_domain = self._extract_domain(candidate)
                if not candidate_domain:
                    continue
                primary[idx] = candidate
                domains[idx] = candidate_domain
                counts[dom] = counts.get(dom, 0) - 1
                counts[candidate_domain] = counts.get(candidate_domain, 0) + 1
                if len({d for d in domains[:top_range] if d}) >= min_unique:
                    break

        return primary

    def _compute_domain_diversity_index(
        self,
        docs: List[Dict[str, Any]],
        *,
        top_k: int = 10,
    ) -> float:
        if not docs:
            return 0.0
        subset = docs[:top_k]
        if not subset:
            return 0.0
        domains = {self._extract_domain(doc) for doc in subset if self._extract_domain(doc)}
        if not subset:
            return 0.0
        return round(len(domains) / len(subset), 4)

    def _compute_with_date_ratio(
        self,
        docs: List[Dict[str, Any]],
        *,
        top_k: int = 10,
    ) -> float:
        if not docs:
            return 0.0
        subset = docs[:top_k]
        if not subset:
            return 0.0
        dated = sum(1 for doc in subset if doc.get("published_at"))
        return round(dated / len(subset), 4)

    async def ask(self, query: str, limit_context: int = 5,
                 user_id: str = None) -> Dict[str, Any]:
        """RAG-style question answering with context"""
        try:
            # Search for relevant context
            search_request = SearchRequest(
                query=query,
                method='hybrid',
                limit=limit_context,
                user_id=user_id,
                explain=True
            )

            search_response = await self.search(search_request)

            if not search_response.results:
                return {
                    'query': query,
                    'answer': "No relevant information found.",
                    'context': [],
                    'sources': []
                }

            # Prepare context snippets
            context_snippets = []
            sources = []

            for result in search_response.results:
                # Extract relevant snippet
                text = result.get('text', result.get('clean_text', ''))
                title = result.get('title_norm', result.get('title', ''))
                url = result.get('url', '')
                domain = result.get('source_domain', result.get('domain', ''))
                published_at = result.get('published_at', '')

                # Create snippet (limit to 200 chars)
                snippet = text[:200] + "..." if len(text) > 200 else text

                context_snippets.append({
                    'text': snippet,
                    'title': title,
                    'url': url,
                    'domain': domain,
                    'published_at': published_at,
                    'relevance_score': result.get('scores', {}).get('final', 0)
                })

                # Add unique sources
                if domain and domain not in [s['domain'] for s in sources]:
                    sources.append({
                        'domain': domain,
                        'url': url,
                        'title': title,
                        'published_at': published_at
                    })

            return {
                'query': query,
                'context': context_snippets,
                'sources': sources,
                'total_context_articles': len(search_response.results),
                'response_time_ms': search_response.response_time_ms
            }

        except Exception as e:
            logger.error(f"Ask failed: {e}")
            return {
                'query': query,
                'answer': f"Error processing question: {e}",
                'context': [],
                'sources': []
            }

    def update_scoring_weights(self, weights: Dict[str, float]) -> bool:
        """Update scoring weights dynamically"""
        try:
            # Update database configuration
            for key, value in weights.items():
                config_key = f"scoring.{key}"
                self.db.set_config_value(config_key, value, 'number')

            # Reload weights
            self._load_scoring_weights()

            logger.info(f"Updated scoring weights: {weights}")
            return True

        except Exception as e:
            logger.error(f"Failed to update scoring weights: {e}")
            return False

    def get_system_health(self) -> Dict[str, Any]:
        """Get system health and performance metrics"""
        try:
            # Check cache first
            cached_health = self.cache.get_cached_system_health()
            if cached_health:
                return cached_health

            # Get recent search analytics
            analytics = self.db.get_search_analytics(days=1)

            # Get quality metrics
            quality_trend = self.db.get_quality_metrics_trend(days=7)

            # Get top domains
            top_domains = self.db.get_top_domains_by_score(limit=10)

            # Get current configuration
            current_weights = self.db.get_scoring_weights()

            # Get cache statistics
            cache_stats = self.cache.get_cache_stats()

            health_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'search_analytics': analytics,
                'quality_trend': quality_trend[-1] if quality_trend else None,
                'top_domains': top_domains,
                'current_weights': current_weights,
                'cache_stats': cache_stats,
                'system_status': 'healthy'
            }

            # Cache the health data
            self.cache.cache_system_health(health_data)

            return health_data

        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'system_status': 'error',
                'error': str(e)
            }


async def main():
    """CLI interface for ranking API"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News Ranking API')
    parser.add_argument('command', choices=['search', 'ask', 'health', 'weights', 'cache'],
                       help='Command to run')
    parser.add_argument('--query', type=str, help='Search query')
    parser.add_argument('--method', type=str, default='hybrid',
                       choices=['fts', 'semantic', 'hybrid'], help='Search method')
    parser.add_argument('--limit', type=int, default=10, help='Result limit')
    parser.add_argument('--explain', action='store_true', help='Include explanations')
    parser.add_argument('--user-id', type=str, help='User ID for logging')
    parser.add_argument('--cache-action', type=str, choices=['stats', 'clear', 'warm'],
                       help='Cache management action')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize API
    api = RankingAPI()

    if args.command == 'search':
        if not args.query:
            print("Error: --query is required for search command")
            return

        request = SearchRequest(
            query=args.query,
            method=args.method,
            limit=args.limit,
            explain=args.explain,
            user_id=args.user_id
        )

        response = await api.search(request)

        print(f"\n=== Search Results for: '{response.query}' ===")
        print(f"Method: {response.search_method}")
        print(f"Total candidates: {response.total_results}")
        print(f"Returned: {len(response.results)}")
        print(f"Response time: {response.response_time_ms}ms")

        if response.diversity_metrics:
            print(f"Diversity score: {response.diversity_metrics.get('diversity_score', 'N/A')}")
            print(f"Unique domains: {response.diversity_metrics.get('unique_domains', 'N/A')}")

        print(f"\nResults:")
        for i, result in enumerate(response.results, 1):
            title = result.get('title_norm', result.get('title', 'No title'))[:80]
            domain = result.get('source_domain', result.get('domain', 'Unknown'))
            final_score = result.get('scores', {}).get('final', 0)
            print(f"[{i}] {final_score:.3f} - {title} ({domain})")

            if args.explain and response.explanations and i <= len(response.explanations):
                explanation = response.explanations[i-1]
                if explanation.get('why_relevant'):
                    print(f"    Why: {'; '.join(explanation['why_relevant'][:2])}")

    elif args.command == 'ask':
        if not args.query:
            print("Error: --query is required for ask command")
            return

        response = await api.ask(args.query, limit_context=5, user_id=args.user_id)

        print(f"\n=== Question: '{response['query']}' ===")
        print(f"Context articles: {response.get('total_context_articles', 0)}")
        print(f"Response time: {response.get('response_time_ms', 0)}ms")

        if response.get('context'):
            print(f"\nContext snippets:")
            for i, snippet in enumerate(response['context'][:3], 1):
                print(f"[{i}] {snippet['title'][:60]} ({snippet['domain']})")
                print(f"    {snippet['text'][:100]}...")

        if response.get('sources'):
            print(f"\nSources:")
            for source in response['sources'][:5]:
                print(f"  • {source['domain']} - {source['title'][:50]}")

    elif args.command == 'health':
        health = api.get_system_health()
        print(f"\n=== System Health ===")
        print(f"Status: {health.get('system_status', 'unknown')}")
        print(f"Timestamp: {health.get('timestamp', 'unknown')}")

        if health.get('search_analytics'):
            analytics = health['search_analytics']
            print(f"\nSearch Analytics (24h):")
            for method_stat in analytics.get('method_stats', []):
                print(f"  {method_stat.get('method', 'unknown')}: {method_stat.get('total', 0)} searches")

        if health.get('current_weights'):
            weights = health['current_weights']
            print(f"\nCurrent Scoring Weights:")
            print(f"  Semantic: {weights.get('semantic', 0):.2f}")
            print(f"  FTS: {weights.get('fts', 0):.2f}")
            print(f"  Freshness: {weights.get('freshness', 0):.2f}")
            print(f"  Source: {weights.get('source', 0):.2f}")

    elif args.command == 'weights':
        weights = api.db.get_scoring_weights()
        print(f"\n=== Current Scoring Weights ===")
        for key, value in weights.items():
            print(f"{key}: {value}")

    elif args.command == 'cache':
        if not args.cache_action:
            print("Error: --cache-action is required for cache command")
            print("Available actions: stats, clear, warm")
            return

        if args.cache_action == 'stats':
            # Show cache statistics
            stats = api.cache.get_cache_stats()
            print(f"\n=== Redis Cache Statistics ===")
            if stats.get('error'):
                print(f"Error: {stats['error']}")
            else:
                print(f"Redis Version: {stats.get('redis_version', 'unknown')}")
                print(f"Memory Used: {stats.get('used_memory_human', 'unknown')}")
                print(f"Connected Clients: {stats.get('connected_clients', 0)}")
                print(f"Total Keys: {stats.get('total_keys', 0)}")
                print(f"Cache Hit Ratio: {stats.get('cache_hit_ratio', 0)}%")
                print(f"Uptime: {stats.get('uptime_seconds', 0)} seconds")

                if stats.get('key_counts_by_type'):
                    print(f"\nKey Distribution:")
                    for key_type, count in stats['key_counts_by_type'].items():
                        print(f"  {key_type}: {count} keys")

        elif args.cache_action == 'clear':
            # Clear cache
            count = api.cache.invalidate_cache('*')
            print(f"🗑️  Cleared {count} cache entries")

        elif args.cache_action == 'warm':
            # Warm up cache
            print("🔥 Warming up cache with popular queries...")
            result = api.cache.warm_cache(api)
            if result.get('error'):
                print(f"Error: {result['error']}")
            else:
                print(f"✅ Cache warming completed:")
                print(f"  Searches cached: {result.get('searches', 0)}")
                print(f"  Trends cached: {result.get('trends', 0)}")
                print(f"  Health cached: {result.get('health', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
