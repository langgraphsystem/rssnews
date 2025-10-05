"""
Production Database Client
Extends pg_client_new with production features: search logs, quality metrics, domain profiles
"""

import os
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from pg_client_new import PgClient

logger = logging.getLogger(__name__)


@dataclass
class SearchLogEntry:
    """Search log entry structure"""
    user_id: str
    query: str
    query_normalized: str
    search_method: str = 'hybrid'
    filters: Dict[str, Any] = None
    results_count: int = 0
    response_time_ms: int = 0
    top_result_ids: List[str] = None
    session_id: str = None


@dataclass
class QualityMetrics:
    """Quality metrics structure"""
    metric_date: datetime
    metric_type: str
    ndcg_at_10: float = None
    recall_at_20: float = None
    precision_at_10: float = None
    fresh_at_10: float = None
    duplicates_at_10: float = None
    avg_response_time_ms: int = None
    p95_response_time_ms: int = None
    total_queries: int = None


class ProductionDBClient(PgClient):
    """Extended database client with production features"""

    def __init__(self):
        super().__init__()

    # ============================================================================
    # Search Logging
    # ============================================================================

    def log_search(self, search_log: SearchLogEntry) -> bool:
        """Log search query and results for analytics"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    INSERT INTO search_logs (
                        user_id, query, query_normalized, search_method,
                        filters, results_count, response_time_ms,
                        top_result_ids, session_id, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    search_log.user_id,
                    search_log.query,
                    search_log.query_normalized,
                    search_log.search_method,
                    json.dumps(search_log.filters or {}),
                    search_log.results_count,
                    search_log.response_time_ms,
                    search_log.top_result_ids or [],
                    search_log.session_id,
                    datetime.utcnow()
                ))
                return True
        except Exception as e:
            logger.error(f"Failed to log search: {e}")
            return False

    def update_search_clicks(self, search_log_id: int, clicked_ids: List[str]) -> bool:
        """Update search log with clicked result IDs"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    UPDATE search_logs
                    SET clicked_result_ids = %s
                    WHERE id = %s
                """, (clicked_ids, search_log_id))
                return True
        except Exception as e:
            logger.error(f"Failed to update search clicks: {e}")
            return False

    def get_search_analytics(self, days: int = 7) -> Dict[str, Any]:
        """Get search analytics for the last N days"""
        try:
            with self._cursor() as cur:
                since_date = datetime.utcnow() - timedelta(days=days)

                # Query analytics
                cur.execute("""
                    SELECT
                        COUNT(*) as total_searches,
                        COUNT(DISTINCT user_id) as unique_users,
                        AVG(response_time_ms) as avg_response_time,
                        AVG(results_count) as avg_results_count,
                        COUNT(CASE WHEN results_count = 0 THEN 1 END) as zero_results_count,
                        search_method,
                        COUNT(*) as method_count
                    FROM search_logs
                    WHERE timestamp >= %s
                    GROUP BY search_method
                """, (since_date,))

                method_stats = cur.fetchall()

                # Top queries
                cur.execute("""
                    SELECT query, COUNT(*) as frequency
                    FROM search_logs
                    WHERE timestamp >= %s AND query != ''
                    GROUP BY query
                    ORDER BY frequency DESC
                    LIMIT 20
                """, (since_date,))

                top_queries = cur.fetchall()

                # Performance stats
                cur.execute("""
                    SELECT
                        AVG(response_time_ms) as avg_response_time,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) as p95_response_time,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY response_time_ms) as p99_response_time
                    FROM search_logs
                    WHERE timestamp >= %s
                """, (since_date,))

                performance = cur.fetchone()

                return {
                    'period_days': days,
                    'method_stats': [dict(zip(['method', 'total', 'unique_users', 'avg_response_time', 'avg_results', 'zero_results'], row)) for row in method_stats],
                    'top_queries': [{'query': q, 'frequency': f} for q, f in top_queries],
                    'performance': {
                        'avg_response_time_ms': int(performance[0]) if performance[0] else 0,
                        'p95_response_time_ms': int(performance[1]) if performance[1] else 0,
                        'p99_response_time_ms': int(performance[2]) if performance[2] else 0
                    }
                }

        except Exception as e:
            logger.error(f"Failed to get search analytics: {e}")
            return {}

    # ============================================================================
    # Domain Profiles Management
    # ============================================================================

    def get_domain_profile(self, domain: str) -> Dict[str, Any]:
        """Get domain profile with scoring information"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT
                        domain, source_score, authority_level,
                        total_clicks, total_impressions, ctr_percentage,
                        avg_dwell_time_seconds, bounce_rate, complaint_count,
                        categories, created_at, updated_at
                    FROM domain_profiles
                    WHERE domain = %s
                """, (domain,))

                row = cur.fetchone()
                if row:
                    return {
                        'domain': row[0],
                        'source_score': float(row[1]),
                        'authority_level': row[2],
                        'total_clicks': row[3],
                        'total_impressions': row[4],
                        'ctr_percentage': float(row[5]) if row[5] else 0,
                        'avg_dwell_time_seconds': row[6],
                        'bounce_rate': float(row[7]) if row[7] else 0,
                        'complaint_count': row[8],
                        'categories': row[9] or [],
                        'created_at': row[10],
                        'updated_at': row[11]
                    }
                else:
                    # Return default profile for unknown domain
                    return {
                        'domain': domain,
                        'source_score': 0.5,
                        'authority_level': 'standard',
                        'total_clicks': 0,
                        'total_impressions': 0,
                        'ctr_percentage': 0.0
                    }

        except Exception as e:
            logger.error(f"Failed to get domain profile for {domain}: {e}")
            return {'domain': domain, 'source_score': 0.5}

    def update_domain_score(self, domain: str, new_score: float, reason: str = None) -> bool:
        """Update domain source score"""
        try:
            with self._cursor() as cur:
                # Check if domain exists
                cur.execute("SELECT id FROM domain_profiles WHERE domain = %s", (domain,))
                exists = cur.fetchone()

                if exists:
                    cur.execute("""
                        UPDATE domain_profiles
                        SET
                            source_score = %s,
                            score_last_updated = %s,
                            score_update_reason = %s,
                            updated_at = %s
                        WHERE domain = %s
                    """, (new_score, datetime.utcnow(), reason, datetime.utcnow(), domain))
                else:
                    # Create new domain profile
                    cur.execute("""
                        INSERT INTO domain_profiles (
                            domain, source_score, score_update_reason, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (domain, new_score, reason, datetime.utcnow(), datetime.utcnow()))

                return True

        except Exception as e:
            logger.error(f"Failed to update domain score for {domain}: {e}")
            return False

    def record_domain_interaction(self, domain: str, interaction_type: str) -> bool:
        """Record user interaction with domain content"""
        try:
            with self._cursor() as cur:
                if interaction_type == 'impression':
                    cur.execute("""
                        UPDATE domain_profiles
                        SET total_impressions = total_impressions + 1
                        WHERE domain = %s
                    """, (domain,))
                elif interaction_type == 'click':
                    cur.execute("""
                        UPDATE domain_profiles
                        SET total_clicks = total_clicks + 1
                        WHERE domain = %s
                    """, (domain,))
                elif interaction_type == 'complaint':
                    cur.execute("""
                        UPDATE domain_profiles
                        SET complaint_count = complaint_count + 1
                        WHERE domain = %s
                    """, (domain,))

                # Update CTR
                cur.execute("SELECT update_domain_score(%s)", (domain,))
                return True

        except Exception as e:
            logger.error(f"Failed to record domain interaction: {e}")
            return False

    def get_top_domains_by_score(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top domains by source score"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT
                        domain, source_score, authority_level,
                        total_clicks, total_impressions, ctr_percentage
                    FROM domain_profiles
                    ORDER BY source_score DESC, total_clicks DESC
                    LIMIT %s
                """, (limit,))

                rows = cur.fetchall()
                return [{
                    'domain': row[0],
                    'source_score': float(row[1]),
                    'authority_level': row[2],
                    'total_clicks': row[3],
                    'total_impressions': row[4],
                    'ctr_percentage': float(row[5]) if row[5] else 0
                } for row in rows]

        except Exception as e:
            logger.error(f"Failed to get top domains: {e}")
            return []

    # ============================================================================
    # Quality Metrics
    # ============================================================================

    def save_quality_metrics(self, metrics: QualityMetrics) -> bool:
        """Save quality metrics for monitoring"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    INSERT INTO quality_metrics (
                        metric_date, metric_type, ndcg_at_10, recall_at_20,
                        precision_at_10, fresh_at_10, duplicates_at_10,
                        avg_response_time_ms, p95_response_time_ms,
                        total_queries
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_type) DO UPDATE SET
                        ndcg_at_10 = EXCLUDED.ndcg_at_10,
                        recall_at_20 = EXCLUDED.recall_at_20,
                        precision_at_10 = EXCLUDED.precision_at_10,
                        fresh_at_10 = EXCLUDED.fresh_at_10,
                        duplicates_at_10 = EXCLUDED.duplicates_at_10,
                        avg_response_time_ms = EXCLUDED.avg_response_time_ms,
                        p95_response_time_ms = EXCLUDED.p95_response_time_ms,
                        total_queries = EXCLUDED.total_queries
                """, (
                    metrics.metric_date.date(),
                    metrics.metric_type,
                    metrics.ndcg_at_10,
                    metrics.recall_at_20,
                    metrics.precision_at_10,
                    metrics.fresh_at_10,
                    metrics.duplicates_at_10,
                    metrics.avg_response_time_ms,
                    metrics.p95_response_time_ms,
                    metrics.total_queries
                ))
                return True

        except Exception as e:
            logger.error(f"Failed to save quality metrics: {e}")
            return False

    def get_quality_metrics_trend(self, metric_type: str = 'search_quality',
                                 days: int = 30) -> List[Dict[str, Any]]:
        """Get quality metrics trend over time"""
        try:
            with self._cursor() as cur:
                since_date = datetime.utcnow().date() - timedelta(days=days)

                cur.execute("""
                    SELECT
                        metric_date, ndcg_at_10, recall_at_20, precision_at_10,
                        fresh_at_10, duplicates_at_10, avg_response_time_ms,
                        p95_response_time_ms, total_queries
                    FROM quality_metrics
                    WHERE metric_type = %s AND metric_date >= %s
                    ORDER BY metric_date
                """, (metric_type, since_date))

                rows = cur.fetchall()
                return [{
                    'date': row[0].isoformat(),
                    'ndcg_at_10': float(row[1]) if row[1] else None,
                    'recall_at_20': float(row[2]) if row[2] else None,
                    'precision_at_10': float(row[3]) if row[3] else None,
                    'fresh_at_10': float(row[4]) if row[4] else None,
                    'duplicates_at_10': float(row[5]) if row[5] else None,
                    'avg_response_time_ms': row[6],
                    'p95_response_time_ms': row[7],
                    'total_queries': row[8]
                } for row in rows]

        except Exception as e:
            logger.error(f"Failed to get quality metrics trend: {e}")
            return []

    # ============================================================================
    # System Configuration
    # ============================================================================

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get system configuration value"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT value, value_type
                    FROM system_config
                    WHERE key = %s
                """, (key,))

                row = cur.fetchone()
                if row:
                    value, value_type = row
                    # Convert based on type
                    if value_type == 'number':
                        return float(value) if '.' in str(value) else int(value)
                    elif value_type == 'boolean':
                        return str(value).lower() in ('true', '1', 'yes')
                    elif value_type == 'json':
                        return json.loads(value)
                    else:
                        return value
                else:
                    return default

        except Exception as e:
            # Schema may differ across environments; fall back to defaults quietly
            logger.warning(f"Failed to get config value {key}: {e}")
            return default

    def set_config_value(self, key: str, value: Any, config_type: str = 'string',
                        description: str = None, category: str = None) -> bool:
        """Set system configuration value"""
        try:
            with self._cursor() as cur:
                # Convert value to string
                if config_type == 'json':
                    str_value = json.dumps(value)
                elif config_type == 'boolean':
                    str_value = 'true' if value else 'false'
                else:
                    str_value = str(value)

                cur.execute("""
                    INSERT INTO system_config (
                        config_key, config_value, config_type, description, category, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (config_key) DO UPDATE SET
                        config_value = EXCLUDED.config_value,
                        config_type = EXCLUDED.config_type,
                        description = COALESCE(EXCLUDED.description, system_config.description),
                        category = COALESCE(EXCLUDED.category, system_config.category),
                        updated_at = EXCLUDED.updated_at
                """, (key, str_value, config_type, description, category, datetime.utcnow()))

                return True

        except Exception as e:
            logger.error(f"Failed to set config value {key}: {e}")
            return False

    def get_scoring_weights(self) -> Dict[str, float]:
        """Get current scoring weights from configuration"""
        weights = {
            'semantic': self.get_config_value('scoring.semantic_weight', 0.58),
            'fts': self.get_config_value('scoring.fts_weight', 0.32),
            'freshness': self.get_config_value('scoring.freshness_weight', 0.06),
            'source': self.get_config_value('scoring.source_weight', 0.04),
            'tau_hours': self.get_config_value('scoring.tau_hours', 72),
            'max_per_domain': self.get_config_value('scoring.max_per_domain', 3),
            'max_per_article': self.get_config_value('scoring.max_per_article', 2)
        }
        return weights

    # ============================================================================
    # Content Canonicalization
    # ============================================================================

    def update_article_canonical_refs(self, article_id: str, canonical_id: str = None,
                                    is_canonical: bool = False, alternatives_count: int = 0,
                                    content_hash: str = None) -> bool:
        """Update article canonicalization references"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    UPDATE articles_index
                    SET
                        is_canonical = %s,
                        canonical_article_id = %s,
                        alternatives_count = %s,
                        content_hash = COALESCE(%s, content_hash),
                        updated_at = %s
                    WHERE article_id = %s OR id = %s
                """, (
                    is_canonical,
                    canonical_id or article_id,
                    alternatives_count,
                    content_hash,
                    datetime.utcnow(),
                    article_id,
                    article_id
                ))
                return True

        except Exception as e:
            logger.error(f"Failed to update canonical refs for {article_id}: {e}")
            return False

    def get_canonical_articles_only(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get only canonical articles (no duplicates)"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT
                        article_id, url, source, title_norm, clean_text,
                        published_at, is_canonical, alternatives_count,
                        source_score, content_hash
                    FROM articles_index
                    WHERE is_canonical = TRUE
                    ORDER BY published_at DESC NULLS LAST
                    LIMIT %s
                """, (limit,))

                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                records = [dict(zip(cols, row)) for row in rows]
                for record in records:
                    if 'title' not in record or not record.get('title'):
                        record['title'] = record.get('title_norm')
                return records

        except Exception as e:
            logger.error(f"Failed to get canonical articles: {e}")
            return []

    # ============================================================================
    # User Interactions Tracking
    # ============================================================================

    def log_user_interaction(self, user_id: str, interaction_type: str,
                           target_type: str, target_id: str,
                           source_query: str = None, result_position: int = None,
                           session_id: str = None, dwell_time: int = None) -> bool:
        """Log user interaction for analytics"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    INSERT INTO user_interactions (
                        user_id, interaction_type, target_type, target_id,
                        source_query, result_position, search_session_id,
                        dwell_time_seconds, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, interaction_type, target_type, target_id,
                    source_query, result_position, session_id,
                    dwell_time, datetime.utcnow()
                ))
                return True

        except Exception as e:
            # Tolerate schema differences without spamming errors
            logger.warning(f"Failed to log user interaction: {e}")
            return False

    # ============================================================================
    # Data Cleanup
    # ============================================================================

    def cleanup_old_data(self) -> Dict[str, int]:
        """Run data cleanup procedures"""
        results = {}

        try:
            with self._cursor() as cur:
                # Clean search logs
                cur.execute("SELECT cleanup_old_search_logs()")
                results['search_logs_deleted'] = cur.fetchone()[0]

                # Clean user interactions
                cur.execute("SELECT cleanup_old_interactions()")
                results['interactions_deleted'] = cur.fetchone()[0]

                # Clean quality metrics
                cur.execute("SELECT cleanup_old_quality_metrics()")
                results['metrics_deleted'] = cur.fetchone()[0]

                logger.info(f"Data cleanup completed: {results}")

        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
            results['error'] = str(e)

        return results

    # ============================================================================
    # Article Retrieval for Analysis
    # ============================================================================

    async def get_recent_articles(
        self, hours: int = 24, limit: int = 50, filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Get recent articles for analysis (async version)"""
        return await asyncio.to_thread(self._get_recent_articles_sync, hours, limit, filters)

    def _get_recent_articles_sync(
        self, hours: int = 24, limit: int = 50, filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Get recent articles for analysis (sync version)"""
        try:
            with self._cursor() as cur:
                # Build WHERE clauses
                where_clauses = [
                    "ai.published_at >= NOW() - (%s || ' hours')::interval",
                    "ai.title_norm IS NOT NULL"
                ]
                params = [int(hours)]

                # Add source filter if provided
                if filters and filters.get('sources'):
                    placeholders = ','.join(['%s'] * len(filters['sources']))
                    where_clauses.append(f"ai.source IN ({placeholders})")
                    params.extend(filters['sources'])

                params.append(limit)
                where_sql = " AND ".join(where_clauses)

                query = f"""
                    SELECT
                        ai.article_id, ai.url, ai.source,
                        ai.title_norm, ai.clean_text, ai.published_at
                    FROM articles_index ai
                    WHERE {where_sql}
                    ORDER BY ai.published_at DESC NULLS LAST
                    LIMIT %s
                """

                cur.execute(query, params)

                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                records = [dict(zip(cols, row)) for row in rows]
                for record in records:
                    if 'title' not in record or not record.get('title'):
                        record['title'] = record.get('title_norm')
                return records

        except Exception as e:
            logger.error(f"Failed to get recent articles: {e}")
            return []

    async def search_with_time_filter(
        self,
        query: str,
        query_embedding: List[float],
        hours: int = 24,
        limit: int = 20,
        filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Search articles with time filtering (async version)"""
        return await asyncio.to_thread(
            self._search_with_time_filter_sync,
            query, query_embedding, hours, limit, filters
        )

    def _search_with_time_filter_sync(
        self,
        query: str,
        query_embedding: List[float],
        hours: int = 24,
        limit: int = 20,
        filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Search articles with time filtering using pgvector (sync version)"""
        try:
            with self._cursor() as cur:
                # Convert embedding to pgvector format
                vector_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

                # Build WHERE clauses and params list
                where_clauses = ["ac.embedding_vector IS NOT NULL"]
                where_clauses.append("ac.published_at >= NOW() - (%s || ' hours')::interval")
                params = [vector_str, hours]

                # Add source filter if provided
                if filters and filters.get('sources'):
                    placeholders = ','.join(['%s'] * len(filters['sources']))
                    where_clauses.append(f"ac.source_domain IN ({placeholders})")
                    params.extend(filters['sources'])

                # Add vector params for ORDER BY and LIMIT
                params.extend([vector_str, limit])

                where_sql = " AND ".join(where_clauses)

                # Execute hybrid search with time filter
                query_sql = f"""
                    SELECT
                        ac.id, ac.article_id, ac.chunk_index, ac.text,
                        ac.url, ac.title_norm, ac.source_domain, ac.published_at,
                        1 - (ac.embedding_vector <=> %s::vector) AS similarity
                    FROM article_chunks ac
                    WHERE {where_sql}
                    ORDER BY ac.embedding_vector <=> %s::vector
                    LIMIT %s
                """

                cur.execute(query_sql, params)

                results = []
                for row in cur.fetchall():
                    results.append({
                        'id': row[0],
                        'article_id': row[1],
                        'chunk_index': row[2],
                        'text': row[3],
                        'url': row[4],
                        'title_norm': row[5],
                        'title': row[5],
                        'source_domain': row[6],
                        'published_at': str(row[7]) if row[7] else None,
                        'similarity': float(row[8]),
                        'semantic_score': float(row[8]),
                        'fts_score': 0.5  # Default FTS score
                    })

                logger.debug(f"search_with_time_filter returned {len(results)} results")
                return results

        except Exception as e:
            logger.error(f"search_with_time_filter failed: {e}", exc_info=True)
            return []

    # ============================================================================
    # Analysis Reports Persistence
    # ============================================================================

    def save_analysis_report(
        self,
        *,
        query: str,
        timeframe: str,
        length: str,
        grounded: bool,
        articles_count: int,
        report_text: str,
        top_domains: List[Tuple[str, int]] = None,
        timeline: Dict[str, int] = None,
        sources: List[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Persist full analysis report to database (idempotent-safe)."""
        try:
            with self._cursor() as cur:
                # Ensure table exists
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_reports (
                        id SERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        query TEXT,
                        timeframe TEXT,
                        length TEXT,
                        grounded BOOLEAN,
                        articles_count INTEGER,
                        report TEXT,
                        top_domains JSONB,
                        timeline JSONB,
                        sources JSONB,
                        user_id TEXT,
                        chat_id TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO analysis_reports (
                        query, timeframe, length, grounded, articles_count, report,
                        top_domains, timeline, sources, user_id, chat_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        query, timeframe, length, grounded, int(articles_count),
                        report_text,
                        json.dumps(top_domains or []),
                        json.dumps(timeline or {}),
                        json.dumps(sources or []),
                        user_id, chat_id,
                    ),
                )
                return True
        except Exception as e:
            logger.error(f"Failed to save analysis report: {e}")
            return False
