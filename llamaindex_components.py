"""
Supporting Components for LlamaIndex Production Integration
==========================================================

Contains specialized components:
- HybridRetriever: FTS + Vector retrieval
- Cost tracking and monitoring
- Domain diversification
- Freshness boosting
- Semantic reranking
- Query caching
- Legacy mode fallback
"""

import time
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict, Counter
import statistics

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.vector_stores.postgres import PGVectorStore
# from llama_index.vector_stores.pinecone import PineconeVectorStore  # Temporarily disabled

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever combining PostgreSQL FTS + Pinecone vector search

    Strategy:
    1. Run both searches in parallel
    2. Normalize scores to 0-1 range
    3. Weighted combination (configurable alpha)
    4. Deduplicate by node_id
    5. Sort by combined score
    """

    def __init__(
        self,
        postgres_store: PGVectorStore,
        pinecone_store: Any,  # PineconeVectorStore temporarily disabled
        similarity_top_k: int = 24,
        alpha: float = 0.5,  # 0.0=pure vector, 1.0=pure FTS
        language: str = "en",
        namespace: str = "hot"
    ):
        self.postgres_store = postgres_store
        self.pinecone_store = pinecone_store
        self.similarity_top_k = similarity_top_k
        self.alpha = alpha
        self.language = language
        self.namespace = namespace

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Synchronous retrieval"""
        return asyncio.run(self.aretrieve(query_bundle))

    async def aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Asynchronous hybrid retrieval"""

        # Run both retrievals in parallel
        fts_task = asyncio.create_task(self._fts_retrieve(query_bundle))
        vector_task = asyncio.create_task(self._vector_retrieve(query_bundle))

        fts_nodes, vector_nodes = await asyncio.gather(fts_task, vector_task)

        # Combine and deduplicate
        combined_nodes = self._combine_results(fts_nodes, vector_nodes)

        logger.info(
            f"Hybrid retrieval: FTS={len(fts_nodes)}, Vector={len(vector_nodes)}, "
            f"Combined={len(combined_nodes)}, Alpha={self.alpha}"
        )

        return combined_nodes[:self.similarity_top_k]

    async def _fts_retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Retrieve using PostgreSQL FTS"""
        try:
            # Use postgres hybrid search capability
            fts_nodes = await self.postgres_store.aquery(
                query=query_bundle.query_str,
                similarity_top_k=self.similarity_top_k * 2,  # Get more for dedup
                mode="hybrid"  # Use FTS + vector if available
            )
            return fts_nodes
        except Exception as e:
            logger.warning(f"FTS retrieval failed: {e}")
            return []

    async def _vector_retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Retrieve using Pinecone vector search"""
        try:
            vector_nodes = await self.pinecone_store.aquery(
                query=query_bundle.query_str,
                similarity_top_k=self.similarity_top_k * 2,  # Get more for dedup
                namespace=self.namespace
            )
            return vector_nodes
        except Exception as e:
            logger.warning(f"Vector retrieval failed: {e}")
            return []

    def _combine_results(
        self,
        fts_nodes: List[NodeWithScore],
        vector_nodes: List[NodeWithScore]
    ) -> List[NodeWithScore]:
        """Combine and score results from both retrievers"""

        # Normalize scores
        fts_scores = self._normalize_scores([n.score for n in fts_nodes])
        vector_scores = self._normalize_scores([n.score for n in vector_nodes])

        # Create score maps
        fts_score_map = {node.node_id: score for node, score in zip(fts_nodes, fts_scores)}
        vector_score_map = {node.node_id: score for node, score in zip(vector_nodes, vector_scores)}

        # Collect all unique nodes
        all_nodes = {}

        # Add FTS nodes
        for node in fts_nodes:
            all_nodes[node.node_id] = node

        # Add vector nodes (merge metadata if duplicate)
        for node in vector_nodes:
            if node.node_id in all_nodes:
                # Node exists, merge metadata
                all_nodes[node.node_id].metadata.update(node.metadata)
            else:
                all_nodes[node.node_id] = node

        # Calculate combined scores
        combined_nodes = []
        for node_id, node in all_nodes.items():
            fts_score = fts_score_map.get(node_id, 0.0)
            vector_score = vector_score_map.get(node_id, 0.0)

            # Weighted combination
            combined_score = self.alpha * fts_score + (1 - self.alpha) * vector_score

            # Boost if present in both retrievers
            if node_id in fts_score_map and node_id in vector_score_map:
                combined_score *= 1.2  # 20% boost for dual presence

            node.score = combined_score
            combined_nodes.append(node)

        # Sort by combined score
        combined_nodes.sort(key=lambda x: x.score, reverse=True)

        return combined_nodes

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores to 0-1 range"""
        if not scores:
            return []

        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return [1.0] * len(scores)

        return [(score - min_score) / (max_score - min_score) for score in scores]


class DomainDiversificationProcessor(BaseNodePostprocessor):
    """
    Ensure domain diversity in results

    Rules:
    - Max 1-2 chunks per domain in final results
    - Prioritize high-scoring results
    - Maintain overall score ranking when possible
    """

    def __init__(self, max_per_domain: int = 2):
        self.max_per_domain = max_per_domain

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None
    ) -> List[NodeWithScore]:
        """Apply domain diversification"""

        domain_counts = defaultdict(int)
        diversified_nodes = []

        # Sort by score to prioritize high-scoring results
        sorted_nodes = sorted(nodes, key=lambda x: x.score, reverse=True)

        for node in sorted_nodes:
            domain = node.metadata.get('source_domain', 'unknown')

            if domain_counts[domain] < self.max_per_domain:
                diversified_nodes.append(node)
                domain_counts[domain] += 1

        logger.info(
            f"Domain diversification: {len(nodes)} → {len(diversified_nodes)} nodes, "
            f"{len(domain_counts)} unique domains"
        )

        return diversified_nodes


class FreshnessBoostProcessor(BaseNodePostprocessor):
    """
    Boost scores for recent content

    Strategy:
    - Articles within boost_recent_days get boost_factor multiplier
    - Linear decay for older content
    - Preserve relative ordering within time buckets
    """

    def __init__(self, boost_recent_days: int = 7, boost_factor: float = 1.2):
        self.boost_recent_days = boost_recent_days
        self.boost_factor = boost_factor

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None
    ) -> List[NodeWithScore]:
        """Apply freshness boosting"""

        boosted_nodes = []

        for node in nodes:
            # Parse published date
            published_str = node.metadata.get('published_at', '')
            try:
                if published_str:
                    published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                    # Ensure timezone compatibility for datetime arithmetic
                    if published_at.tzinfo is not None:
                        current_time = datetime.now(timezone.utc)
                    else:
                        current_time = datetime.now()
                    age_days = (current_time - published_at).days

                    # Calculate boost
                    if age_days <= self.boost_recent_days:
                        # Linear boost: newest gets full boost, older gets less
                        boost = self.boost_factor * (1 - age_days / self.boost_recent_days)
                        node.score *= boost
                        node.metadata['freshness_boost'] = boost
                    else:
                        node.metadata['freshness_boost'] = 1.0
                else:
                    node.metadata['freshness_boost'] = 1.0
            except Exception as e:
                logger.warning(f"Failed to parse published_at: {published_str}, error: {e}")
                node.metadata['freshness_boost'] = 1.0

            boosted_nodes.append(node)

        # Re-sort by boosted scores
        boosted_nodes.sort(key=lambda x: x.score, reverse=True)

        return boosted_nodes


class SemanticReranker(BaseNodePostprocessor):
    """
    Semantic reranking using cross-encoder or LLM

    Strategy:
    - Take top-K results from initial retrieval
    - Use more sophisticated relevance scoring
    - Return reranked top-N results
    """

    def __init__(self, top_k: int = 10, rerank_model: str = "cross-encoder"):
        self.top_k = top_k
        self.rerank_model = rerank_model

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None
    ) -> List[NodeWithScore]:
        """Apply semantic reranking"""

        if not query_bundle or len(nodes) <= self.top_k:
            return nodes[:self.top_k]

        # For now, implement simple relevance scoring
        # TODO: Integrate actual cross-encoder model
        query_terms = set(query_bundle.query_str.lower().split())

        for node in nodes:
            # Calculate term overlap relevance
            text_terms = set(node.text.lower().split())
            title_terms = set(node.metadata.get('title', '').lower().split())

            text_overlap = len(query_terms.intersection(text_terms)) / len(query_terms)
            title_overlap = len(query_terms.intersection(title_terms)) / len(query_terms)

            # Combine with original score
            relevance_score = 0.7 * text_overlap + 0.3 * title_overlap
            node.score = 0.8 * node.score + 0.2 * relevance_score

            node.metadata['rerank_score'] = relevance_score

        # Re-sort and limit
        reranked_nodes = sorted(nodes, key=lambda x: x.score, reverse=True)[:self.top_k]

        logger.info(f"Semantic reranking: {len(nodes)} → {self.top_k} nodes")

        return reranked_nodes


class CostTracker:
    """
    Track API costs and usage across different providers

    Features:
    - Real-time cost estimation
    - Daily/monthly budget tracking
    - Provider-specific pricing
    - Usage analytics
    """

    def __init__(self):
        self.daily_costs = defaultdict(float)
        self.monthly_costs = defaultdict(float)

        # Pricing per 1K tokens (approximate)
        self.pricing = {
            'openai_gpt5_input': 0.01,
            'openai_gpt5_output': 0.03,
            'gemini_pro_input': 0.0035,
            'gemini_pro_output': 0.0105,
            'gemini_embedding': 0.00001,
        }

        # Budget limits
        self.daily_limits = {
            'openai': 50.0,    # $50/day
            'gemini': 30.0,    # $30/day
            'total': 100.0,    # $100/day total
        }

    def estimate_cost(self, response: Any) -> Dict[str, float]:
        """Estimate cost for a response"""

        # Extract token usage from response
        input_tokens = getattr(response, 'input_tokens', 0)
        output_tokens = getattr(response, 'output_tokens', 0)
        provider = getattr(response, 'provider', 'unknown')

        if provider == 'openai':
            input_cost = (input_tokens / 1000) * self.pricing['openai_gpt5_input']
            output_cost = (output_tokens / 1000) * self.pricing['openai_gpt5_output']
        elif provider == 'gemini':
            input_cost = (input_tokens / 1000) * self.pricing['gemini_pro_input']
            output_cost = (output_tokens / 1000) * self.pricing['gemini_pro_output']
        else:
            input_cost = output_cost = 0.0

        total_cost = input_cost + output_cost

        # Track daily costs
        today = datetime.now().date().isoformat()
        self.daily_costs[f"{today}_{provider}"] += total_cost
        self.daily_costs[f"{today}_total"] += total_cost

        return {
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': total_cost,
            'provider': provider,
            'daily_total': self.daily_costs[f"{today}_total"]
        }

    def check_budget_limits(self, provider: str = 'total') -> bool:
        """Check if under budget limits"""

        today = datetime.now().date().isoformat()
        daily_spent = self.daily_costs.get(f"{today}_{provider}", 0.0)
        limit = self.daily_limits.get(provider, float('inf'))

        return daily_spent < limit

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics"""

        today = datetime.now().date().isoformat()

        return {
            'daily_costs': dict(self.daily_costs),
            'today_total': self.daily_costs.get(f"{today}_total", 0.0),
            'budget_remaining': {
                provider: limit - self.daily_costs.get(f"{today}_{provider}", 0.0)
                for provider, limit in self.daily_limits.items()
            }
        }


class QueryCache:
    """
    Simple in-memory query cache with TTL

    Features:
    - TTL-based expiration
    - LRU eviction when full
    - Query normalization for better hit rates
    """

    def __init__(self, ttl_minutes: int = 15, max_size: int = 1000):
        self.ttl_seconds = ttl_minutes * 60
        self.max_size = max_size
        self.cache = {}
        self.access_times = {}

    def _normalize_query(self, query: str) -> str:
        """Normalize query for better cache hits"""
        return query.lower().strip()

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if not expired"""

        if cache_key not in self.cache:
            return None

        entry_time, result = self.cache[cache_key]

        # Check if expired
        if time.time() - entry_time > self.ttl_seconds:
            self._evict(cache_key)
            return None

        # Update access time for LRU
        self.access_times[cache_key] = time.time()

        return result

    def set(self, cache_key: str, result: Dict[str, Any]):
        """Cache result with TTL"""

        current_time = time.time()

        # Evict if at capacity
        if len(self.cache) >= self.max_size:
            self._evict_lru()

        self.cache[cache_key] = (current_time, result)
        self.access_times[cache_key] = current_time

    def _evict(self, cache_key: str):
        """Remove specific cache entry"""
        self.cache.pop(cache_key, None)
        self.access_times.pop(cache_key, None)

    def _evict_lru(self):
        """Evict least recently used entry"""
        if not self.access_times:
            return

        lru_key = min(self.access_times.keys(), key=self.access_times.get)
        self._evict(lru_key)

    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        self.access_times.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""

        current_time = time.time()

        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'ttl_seconds': self.ttl_seconds,
            'expired_entries': sum(
                1 for entry_time, _ in self.cache.values()
                if current_time - entry_time > self.ttl_seconds
            )
        }


class LegacyModeManager:
    """
    Manage fallback to legacy RSS system components

    Features:
    - One-click legacy mode toggle
    - Gradual rollback capabilities
    - Performance comparison
    - A/B testing support
    """

    def __init__(self, config_path: str = "legacy_config.json"):
        self.config_path = config_path
        self.legacy_mode = False
        self.legacy_components = {}

    def enable_legacy_mode(self, components: List[str] = None):
        """Enable legacy mode for specified components"""

        available_components = [
            'chunking',      # Use chunking_simple.py
            'retrieval',     # Use HybridRetriever (custom)
            'synthesis',     # Use custom RAG pipeline
            'full'          # Complete fallback
        ]

        if components is None:
            components = ['full']

        for component in components:
            if component in available_components:
                self.legacy_components[component] = True
                logger.info(f"Legacy mode enabled for: {component}")

        self.legacy_mode = True

    def disable_legacy_mode(self):
        """Disable legacy mode completely"""
        self.legacy_mode = False
        self.legacy_components.clear()
        logger.info("Legacy mode disabled - using LlamaIndex pipeline")

    def is_legacy_enabled(self, component: str) -> bool:
        """Check if legacy mode is enabled for component"""
        return self.legacy_mode and (
            self.legacy_components.get('full', False) or
            self.legacy_components.get(component, False)
        )

    def get_legacy_status(self) -> Dict[str, Any]:
        """Get current legacy mode status"""
        return {
            'legacy_mode': self.legacy_mode,
            'legacy_components': self.legacy_components,
            'llamaindex_components': {
                component: not self.is_legacy_enabled(component)
                for component in ['chunking', 'retrieval', 'synthesis']
            }
        }


# Performance monitoring
class PerformanceMonitor:
    """
    Monitor system performance and quality metrics

    Metrics:
    - Response time per component
    - Retrieval accuracy
    - User satisfaction (if available)
    - Cost efficiency
    - Error rates
    """

    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_times = {}

    def start_timer(self, operation: str) -> str:
        """Start timing an operation"""
        timer_id = f"{operation}_{int(time.time() * 1000)}"
        self.start_times[timer_id] = time.time()
        return timer_id

    def end_timer(self, timer_id: str) -> float:
        """End timing and record duration"""
        if timer_id not in self.start_times:
            return 0.0

        duration = time.time() - self.start_times[timer_id]
        operation = timer_id.rsplit('_', 1)[0]
        self.metrics[f"{operation}_duration"].append(duration)

        del self.start_times[timer_id]
        return duration

    def record_metric(self, metric_name: str, value: float):
        """Record a custom metric"""
        self.metrics[metric_name].append(value)

    def get_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a metric"""
        values = self.metrics.get(metric_name, [])

        if not values:
            return {'count': 0}

        return {
            'count': len(values),
            'mean': statistics.mean(values),
            'median': statistics.median(values),
            'min': min(values),
            'max': max(values),
            'p95': sorted(values)[int(0.95 * len(values))] if len(values) > 1 else values[0]
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all metrics"""
        return {
            metric_name: self.get_stats(metric_name)
            for metric_name in self.metrics.keys()
        }