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
        self.db = ProductionDBClient()
        self.scorer = ProductionScorer()
        self.dedup_engine = DeduplicationEngine()
        self.diversifier = MMRDiversifier()
        self.explainer = ExplainabilityEngine()
        self.embedding_generator = OpenAIEmbeddingGenerator()
        self.cache = CachingService()

        # Load dynamic weights from database
        self._load_scoring_weights()

    def _load_scoring_weights(self):
        """Load scoring weights from database configuration"""
        try:
            weights = self.db.get_scoring_weights()
            if weights:
                self.scorer.weights.semantic = weights.get('semantic', 0.58)
                self.scorer.weights.fts = weights.get('fts', 0.32)
                self.scorer.weights.freshness = weights.get('freshness', 0.06)
                self.scorer.weights.source = weights.get('source', 0.04)
                self.scorer.weights.tau_hours = weights.get('tau_hours', 72)
                self.scorer.weights.max_per_domain = weights.get('max_per_domain', 3)
                self.scorer.weights.max_per_article = weights.get('max_per_article', 2)

                logger.info(f"Loaded scoring weights: {weights}")

        except Exception as e:
            logger.warning(f"Failed to load scoring weights, using defaults: {e}")

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
            scored_results = self.scorer.score_and_rank(candidates, query_normalized)

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
        use_rerank: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve documents for analysis (trends/analyze commands)

        Args:
            query: Optional search query (None for trends without query)
            window: Time window (6h, 12h, 24h, 1d, 3d, 1w, 2w, 1m, 3m, 6m, 1y)
            lang: Language filter (ru, en, auto)
            sources: Optional list of source domains to filter
            k_final: Number of documents to return
            use_rerank: Whether to use reranking (not implemented yet)

        Returns:
            List of document dictionaries with metadata
        """
        try:
            # Parse time window to hours
            window_hours = {
                "1h": 1, "6h": 6, "12h": 12,
                "24h": 24, "1d": 24, "3d": 72,
                "1w": 168, "2w": 336, "1m": 720,
                "3m": 2160, "6m": 4320, "1y": 8760
            }.get(window, 24)

            # Build time filter
            time_filter = f"NOW() - INTERVAL '{window_hours} hours'"

            # Build filters dict
            filters = {}
            if sources:
                filters['sources'] = sources
            if lang and lang != 'auto':
                filters['lang'] = lang

            # If query provided, use hybrid search
            if query:
                query_normalized = self._normalize_query(query)

                # Generate embedding
                query_embeddings = await self.embedding_generator.generate_embeddings([query_normalized])
                if not query_embeddings or not query_embeddings[0]:
                    logger.warning("Failed to generate query embedding for retrieve_for_analysis")
                    return []

                query_embedding = query_embeddings[0]

                # Search with time filter
                results = self.db.search_with_time_filter(
                    query=query_normalized,
                    query_embedding=query_embedding,
                    time_filter=time_filter,
                    limit=k_final * 2,  # Get more candidates
                    filters=filters
                )
            else:
                # No query - get recent articles for trends
                results = self.db.get_recent_articles(
                    hours=window_hours,
                    limit=k_final * 3,  # Get more for clustering
                    filters=filters
                )

            # Apply scoring
            if results:
                scored_results = self.scorer.score_and_rank(results, query or "")

                # Apply deduplication
                if len(scored_results) > 1:
                    deduplicated = self.dedup_engine.canonicalize_articles(scored_results)
                else:
                    deduplicated = scored_results

                # Return top k_final
                return deduplicated[:k_final]

            return []

        except Exception as e:
            logger.error(f"retrieve_for_analysis failed: {e}", exc_info=True)
            return []

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