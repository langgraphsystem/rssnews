"""
Phase 4 History Tracking Service
Tracks metrics and topic snapshots for dashboards and reports.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import asyncpg

logger = logging.getLogger(__name__)


class Phase4HistoryService:
    """Service for tracking and querying Phase 4 metrics history"""

    def __init__(self, pg_dsn: Optional[str] = None):
        self.pg_dsn = pg_dsn or os.getenv('PG_DSN')
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool"""
        if self._pool is None:
            if not self.pg_dsn:
                raise ValueError("PG_DSN not configured")

            self._pool = await asyncpg.create_pool(
                self.pg_dsn,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            logger.info("[Phase4History] Connection pool created")

        return self._pool

    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("[Phase4History] Connection pool closed")

    # ==========================================================================
    # METRICS TRACKING
    # ==========================================================================

    async def track_metric(
        self,
        metric: str,
        value: float,
        user_id: Optional[str] = None,
        time_window: str = "1h",
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Track a metric value.

        Args:
            metric: Metric name (e.g., 'traffic', 'ctr', 'roi')
            value: Metric value
            user_id: User ID (optional)
            time_window: Time window (e.g., '1h', '1d', '1w')
            source: Data source (e.g., 'dashboard', 'reports', 'manual')
            metadata: Additional metadata

        Returns:
            True if successful
        """
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO phase4_metrics (ts, user_id, metric, value, time_window, source, metadata)
                    VALUES (NOW(), $1, $2, $3, $4, $5, $6)
                    """,
                    user_id,
                    metric,
                    value,
                    time_window,
                    source,
                    metadata or {}
                )

            logger.debug(f"[Phase4History] Tracked metric: {metric}={value} (window={time_window})")
            return True

        except Exception as e:
            logger.error(f"[Phase4History] Failed to track metric {metric}: {e}")
            return False

    async def get_metrics(
        self,
        metric: str,
        user_id: Optional[str] = None,
        time_window: Optional[str] = None,
        hours_back: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query metric history.

        Args:
            metric: Metric name
            user_id: Filter by user ID
            time_window: Filter by time window
            hours_back: How many hours back to query
            limit: Max results

        Returns:
            List of metric records
        """
        try:
            pool = await self._get_pool()

            since = datetime.utcnow() - timedelta(hours=hours_back)

            async with pool.acquire() as conn:
                query = """
                    SELECT ts, metric, value, time_window, source, metadata
                    FROM phase4_metrics
                    WHERE metric = $1 AND ts >= $2
                """
                params = [metric, since]

                if user_id:
                    query += " AND user_id = $" + str(len(params) + 1)
                    params.append(user_id)

                if time_window:
                    query += " AND time_window = $" + str(len(params) + 1)
                    params.append(time_window)

                query += " ORDER BY ts DESC LIMIT $" + str(len(params) + 1)
                params.append(limit)

                rows = await conn.fetch(query, *params)

                return [
                    {
                        "ts": row['ts'].isoformat() + "Z",
                        "metric": row['metric'],
                        "value": float(row['value']),
                        "time_window": row['time_window'],
                        "source": row['source'],
                        "metadata": row['metadata']
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"[Phase4History] Failed to get metrics {metric}: {e}")
            return []

    async def get_metric_aggregate(
        self,
        metric: str,
        user_id: Optional[str] = None,
        hours_back: int = 24
    ) -> Optional[Dict[str, float]]:
        """
        Get aggregate statistics for a metric.

        Returns:
            Dict with avg, min, max, latest values
        """
        try:
            pool = await self._get_pool()

            since = datetime.utcnow() - timedelta(hours=hours_back)

            async with pool.acquire() as conn:
                query = """
                    SELECT
                        AVG(value) as avg_value,
                        MIN(value) as min_value,
                        MAX(value) as max_value,
                        (SELECT value FROM phase4_metrics
                         WHERE metric = $1 AND ts >= $2
                         ORDER BY ts DESC LIMIT 1) as latest_value,
                        COUNT(*) as sample_count
                    FROM phase4_metrics
                    WHERE metric = $1 AND ts >= $2
                """
                params = [metric, since]

                if user_id:
                    query += " AND user_id = $3"
                    params.append(user_id)

                row = await conn.fetchrow(query, *params)

                if not row or row['sample_count'] == 0:
                    return None

                return {
                    "avg": float(row['avg_value'] or 0),
                    "min": float(row['min_value'] or 0),
                    "max": float(row['max_value'] or 0),
                    "latest": float(row['latest_value'] or 0),
                    "samples": int(row['sample_count'])
                }

        except Exception as e:
            logger.error(f"[Phase4History] Failed to aggregate metric {metric}: {e}")
            return None

    # ==========================================================================
    # SNAPSHOTS TRACKING
    # ==========================================================================

    async def track_snapshot(
        self,
        topic: str,
        momentum: float,
        sentiment: float,
        volume: int = 0,
        user_id: Optional[str] = None,
        time_window: str = "1h",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Track a topic snapshot (momentum + sentiment).

        Args:
            topic: Topic/keyword
            momentum: Momentum score (-1.0 to 1.0)
            sentiment: Sentiment score (-1.0 to 1.0)
            volume: Article count
            user_id: User ID
            time_window: Time window
            metadata: Additional metadata

        Returns:
            True if successful
        """
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO phase4_snapshots (ts, user_id, topic, momentum, sentiment, volume, time_window, metadata)
                    VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7)
                    """,
                    user_id,
                    topic,
                    momentum,
                    sentiment,
                    volume,
                    time_window,
                    metadata or {}
                )

            logger.debug(f"[Phase4History] Tracked snapshot: {topic} (momentum={momentum:.2f}, sentiment={sentiment:.2f})")
            return True

        except Exception as e:
            logger.error(f"[Phase4History] Failed to track snapshot {topic}: {e}")
            return False

    async def get_snapshots(
        self,
        user_id: Optional[str] = None,
        topic: Optional[str] = None,
        hours_back: int = 168,  # 1 week default
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Query topic snapshots.

        Args:
            user_id: Filter by user
            topic: Filter by topic
            hours_back: How many hours back
            limit: Max results

        Returns:
            List of snapshot records
        """
        try:
            pool = await self._get_pool()

            since = datetime.utcnow() - timedelta(hours=hours_back)

            async with pool.acquire() as conn:
                query = """
                    SELECT ts, topic, momentum, sentiment, volume, time_window, metadata
                    FROM phase4_snapshots
                    WHERE ts >= $1
                """
                params = [since]

                if user_id:
                    query += " AND user_id = $" + str(len(params) + 1)
                    params.append(user_id)

                if topic:
                    query += " AND topic ILIKE $" + str(len(params) + 1)
                    params.append(f"%{topic}%")

                query += " ORDER BY ts DESC LIMIT $" + str(len(params) + 1)
                params.append(limit)

                rows = await conn.fetch(query, *params)

                return [
                    {
                        "ts": row['ts'].isoformat() + "Z",
                        "topic": row['topic'],
                        "momentum": float(row['momentum']),
                        "sentiment": float(row['sentiment']),
                        "volume": int(row['volume']),
                        "time_window": row['time_window'],
                        "metadata": row['metadata']
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"[Phase4History] Failed to get snapshots: {e}")
            return []

    async def get_top_topics(
        self,
        user_id: Optional[str] = None,
        hours_back: int = 24,
        limit: int = 10,
        sort_by: str = "momentum"  # 'momentum', 'sentiment', 'volume'
    ) -> List[Dict[str, Any]]:
        """
        Get top trending topics.

        Args:
            user_id: Filter by user
            hours_back: Time range
            limit: Max results
            sort_by: Sort field

        Returns:
            List of top topics with scores
        """
        try:
            pool = await self._get_pool()

            since = datetime.utcnow() - timedelta(hours=hours_back)

            # Validate sort_by
            if sort_by not in ('momentum', 'sentiment', 'volume'):
                sort_by = 'momentum'

            async with pool.acquire() as conn:
                query = f"""
                    SELECT
                        topic,
                        AVG(momentum) as avg_momentum,
                        AVG(sentiment) as avg_sentiment,
                        SUM(volume) as total_volume,
                        COUNT(*) as sample_count
                    FROM phase4_snapshots
                    WHERE ts >= $1
                """
                params = [since]

                if user_id:
                    query += " AND user_id = $2"
                    params.append(user_id)

                query += f" GROUP BY topic ORDER BY avg_{sort_by} DESC LIMIT ${len(params) + 1}"
                params.append(limit)

                rows = await conn.fetch(query, *params)

                return [
                    {
                        "topic": row['topic'],
                        "momentum": float(row['avg_momentum']),
                        "sentiment": float(row['avg_sentiment']),
                        "volume": int(row['total_volume']),
                        "samples": int(row['sample_count'])
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"[Phase4History] Failed to get top topics: {e}")
            return []

    # ==========================================================================
    # BATCH OPERATIONS
    # ==========================================================================

    async def track_metrics_batch(
        self,
        metrics: List[Dict[str, Any]],
        user_id: Optional[str] = None
    ) -> int:
        """
        Track multiple metrics at once.

        Args:
            metrics: List of dicts with keys: metric, value, time_window, source
            user_id: User ID for all metrics

        Returns:
            Number of successfully tracked metrics
        """
        if not metrics:
            return 0

        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                async with conn.transaction():
                    inserted = 0
                    for m in metrics:
                        try:
                            await conn.execute(
                                """
                                INSERT INTO phase4_metrics (ts, user_id, metric, value, time_window, source)
                                VALUES (NOW(), $1, $2, $3, $4, $5)
                                """,
                                user_id,
                                m['metric'],
                                m['value'],
                                m.get('time_window', '1h'),
                                m.get('source', 'batch')
                            )
                            inserted += 1
                        except Exception as e:
                            logger.warning(f"[Phase4History] Failed to insert metric: {e}")

                    logger.info(f"[Phase4History] Tracked {inserted}/{len(metrics)} metrics in batch")
                    return inserted

        except Exception as e:
            logger.error(f"[Phase4History] Batch metrics failed: {e}")
            return 0


# Singleton instance
_history_service: Optional[Phase4HistoryService] = None


def get_phase4_history_service() -> Phase4HistoryService:
    """Get or create Phase4HistoryService singleton"""
    global _history_service
    if _history_service is None:
        _history_service = Phase4HistoryService()
    return _history_service
