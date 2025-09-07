"""
Production-grade Batch Planner for RSS Processing System
Handles intelligent batch formation with dynamic sizing, prioritization, and load balancing.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field

from monitoring import MetricsCollector
from config import Config

logger = logging.getLogger(__name__)


class BatchPriority(Enum):
    """Batch priority levels"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class BatchStatus(Enum):
    """Batch processing status"""
    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class LoadMetrics:
    """System load metrics for intelligent sizing"""
    active_workers: int = 0
    avg_batch_time_seconds: float = 0.0
    queue_depth: int = 0
    error_rate_1h: float = 0.0
    memory_usage_percent: float = 0.0
    cpu_usage_percent: float = 0.0
    disk_io_wait_percent: float = 0.0
    
    def load_factor(self) -> float:
        """Calculate overall load factor (0.0 - 1.0+)"""
        factors = [
            min(self.cpu_usage_percent / 80.0, 1.0),  # 80% CPU is high load
            min(self.memory_usage_percent / 90.0, 1.0),  # 90% memory is high load
            min(self.disk_io_wait_percent / 20.0, 1.0),  # 20% IO wait is high
            min(self.queue_depth / 1000.0, 1.0),  # 1000+ queue items is high
            self.error_rate_1h * 2.0  # Error rate multiplier
        ]
        return sum(factors) / len(factors)


@dataclass
class FeedHealthMetrics:
    """Feed health and performance metrics"""
    feed_id: int
    domain: str
    trust_score: int
    health_score: int
    avg_response_time_ms: int
    error_rate_24h: float
    duplicate_rate_24h: float
    content_quality_score: float
    daily_quota: int
    daily_processed: int
    consecutive_failures: int
    last_success: Optional[datetime]
    
    @property
    def priority_score(self) -> float:
        """Calculate priority score for batch inclusion (higher = better)"""
        # Base score from trust and health
        base_score = (self.trust_score + self.health_score) / 2.0
        
        # Penalty for high error rates
        error_penalty = min(self.error_rate_24h * 10, 50)
        
        # Penalty for high duplicate rates
        dup_penalty = min(self.duplicate_rate_24h * 0.5, 25)
        
        # Penalty for slow response times
        speed_penalty = min(self.avg_response_time_ms / 100, 25)
        
        # Penalty for consecutive failures
        failure_penalty = min(self.consecutive_failures * 5, 30)
        
        # Bonus for good content quality
        quality_bonus = self.content_quality_score * 20
        
        # Quota exhaustion penalty
        quota_penalty = 0
        if self.daily_quota > 0:
            quota_usage = self.daily_processed / self.daily_quota
            if quota_usage > 0.9:
                quota_penalty = 40  # Severe penalty if near quota limit
            elif quota_usage > 0.7:
                quota_penalty = 20
        
        final_score = base_score - error_penalty - dup_penalty - speed_penalty - failure_penalty + quality_bonus - quota_penalty
        return max(0.0, min(100.0, final_score))
    
    @property
    def is_healthy(self) -> bool:
        """Check if feed is healthy enough for processing"""
        return (
            self.health_score >= 50 
            and self.consecutive_failures < 5
            and self.error_rate_24h < 50.0
            and (self.daily_quota == 0 or self.daily_processed < self.daily_quota)
        )


@dataclass
class BatchCandidate:
    """Article candidate for batch processing"""
    id: int
    feed_id: int
    url: str
    url_hash: str
    text_hash: Optional[str]
    title: Optional[str]
    fetched_at: datetime
    retry_count: int
    priority_score: float
    estimated_processing_time_ms: int = 1000
    
    @property
    def age_hours(self) -> float:
        """Age of article in hours"""
        return (datetime.utcnow() - self.fetched_at).total_seconds() / 3600
    
    @property
    def is_retry(self) -> bool:
        """Check if this is a retry"""
        return self.retry_count > 0
    
    @property
    def urgency_score(self) -> float:
        """Calculate urgency score (0-100, higher = more urgent)"""
        # Fresh articles get higher urgency
        age_score = max(0, 100 - (self.age_hours * 2))  # Decay over 50 hours
        
        # Retry articles get lower urgency unless they're very fresh
        retry_penalty = self.retry_count * 10 if self.age_hours > 1 else 0
        
        return max(0, age_score - retry_penalty)


class BatchConfiguration(BaseModel):
    """Batch configuration parameters"""
    target_size: int = Field(200, ge=50, le=500, description="Target batch size")
    min_size: int = Field(100, ge=10, description="Minimum batch size")
    max_size: int = Field(300, le=1000, description="Maximum batch size")
    priority: BatchPriority = BatchPriority.NORMAL
    max_age_hours: float = Field(72.0, description="Maximum article age in hours")
    min_quality_score: float = Field(0.3, description="Minimum feed quality score")
    max_retry_articles_percent: float = Field(30.0, description="Max % of retry articles")
    diversity_factor: float = Field(0.2, description="Domain diversity factor (0-1)")
    source_filter: Optional[Dict] = None
    processing_timeout_seconds: int = 3600
    
    class Config:
        use_enum_values = True


class BatchPlanner:
    """
    Intelligent batch planner with adaptive sizing and prioritization.
    
    Features:
    - Dynamic batch sizing based on system load
    - Feed prioritization by health and trust scores
    - Domain diversity to prevent single-source overload
    - Hot/warm/cold article classification
    - Quota management per domain
    - Circuit breaker for problematic feeds
    """
    
    def __init__(self, 
                 db_pool: asyncpg.Pool,
                 redis_client: redis.Redis,
                 metrics: MetricsCollector,
                 config: Config):
        self.db_pool = db_pool
        self.redis = redis_client
        self.metrics = metrics
        self.config = config
        
        # Adaptive sizing parameters
        self.sizing_history: List[Tuple[float, int, float]] = []  # (load_factor, batch_size, success_rate)
        self.max_history_size = 100
        
        # Circuit breaker state
        self.circuit_breakers: Dict[int, Dict] = {}  # feed_id -> {failures, last_failure, state}
        
        # Caches
        self._feed_metrics_cache: Dict[int, FeedHealthMetrics] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
        self._last_cache_refresh = 0
        
    async def create_batch(self, 
                          config: BatchConfiguration,
                          worker_id: str,
                          correlation_id: Optional[str] = None) -> Optional[str]:
        """
        Create an optimally-sized batch for processing.
        
        Args:
            config: Batch configuration
            worker_id: Unique worker identifier
            correlation_id: Optional correlation ID for tracing
            
        Returns:
            Batch ID if successful, None if no work available
        """
        start_time = time.time()
        
        try:
            # Acquire distributed lock for batch creation
            lock_key = "batch_creation"
            lock_acquired = await self._acquire_lock(lock_key, worker_id, timeout_seconds=30)
            
            if not lock_acquired:
                logger.debug(f"Worker {worker_id} failed to acquire batch creation lock")
                await self.metrics.increment("batch.creation.lock_failed")
                return None
            
            try:
                # Get current system load metrics
                load_metrics = await self._get_load_metrics()
                
                # Adjust batch size based on load
                optimal_size = self._calculate_optimal_batch_size(config, load_metrics)
                
                # Get feed health metrics
                feed_metrics = await self._get_feed_health_metrics()
                
                # Select articles for the batch
                candidates = await self._select_batch_candidates(
                    target_size=optimal_size,
                    config=config,
                    feed_metrics=feed_metrics
                )
                
                if not candidates:
                    logger.info("No suitable articles found for batch creation")
                    await self.metrics.increment("batch.creation.no_candidates")
                    return None
                
                # Create batch in database
                batch_id = await self._create_batch_record(
                    candidates=candidates,
                    config=config,
                    worker_id=worker_id,
                    correlation_id=correlation_id,
                    load_metrics=load_metrics
                )
                
                # Lock selected articles
                await self._lock_articles(candidates, batch_id, worker_id)
                
                # Record batch creation metrics
                creation_time = time.time() - start_time
                await self.metrics.timing("batch.creation.duration", creation_time)
                await self.metrics.histogram("batch.size", len(candidates))
                await self.metrics.gauge("batch.load_factor", load_metrics.load_factor())
                
                logger.info(f"Created batch {batch_id} with {len(candidates)} articles "
                          f"in {creation_time:.2f}s (worker: {worker_id})")
                
                return batch_id
                
            finally:
                await self._release_lock(lock_key, worker_id)
                
        except Exception as e:
            logger.error(f"Failed to create batch for worker {worker_id}: {e}", exc_info=True)
            await self.metrics.increment("batch.creation.error")
            return None
    
    def _calculate_optimal_batch_size(self, 
                                    config: BatchConfiguration,
                                    load_metrics: LoadMetrics) -> int:
        """Calculate optimal batch size based on system load and historical performance"""
        base_size = config.target_size
        load_factor = load_metrics.load_factor()
        
        # Reduce batch size under high load
        if load_factor > 0.8:
            size_reduction = int(base_size * 0.4)  # Reduce by 40%
        elif load_factor > 0.6:
            size_reduction = int(base_size * 0.2)  # Reduce by 20%
        elif load_factor > 0.4:
            size_reduction = int(base_size * 0.1)  # Reduce by 10%
        else:
            # Low load - can increase batch size slightly
            size_reduction = -int(base_size * 0.1)  # Increase by 10%
        
        optimal_size = base_size - size_reduction
        
        # Apply historical learning
        if self.sizing_history:
            # Find similar load conditions from history
            similar_conditions = [
                (size, success_rate) for load, size, success_rate in self.sizing_history
                if abs(load - load_factor) < 0.1
            ]
            
            if similar_conditions:
                # Use the size that gave the best success rate in similar conditions
                best_size = max(similar_conditions, key=lambda x: x[1])[0]
                optimal_size = int(0.7 * optimal_size + 0.3 * best_size)
        
        # Apply constraints
        optimal_size = max(config.min_size, min(config.max_size, optimal_size))
        
        logger.debug(f"Calculated optimal batch size: {optimal_size} "
                    f"(base: {base_size}, load: {load_factor:.2f})")
        
        return optimal_size
    
    async def _select_batch_candidates(self,
                                     target_size: int,
                                     config: BatchConfiguration,
                                     feed_metrics: Dict[int, FeedHealthMetrics]) -> List[BatchCandidate]:
        """Select articles for batch processing with intelligent prioritization"""
        
        # Build selection query with prioritization
        query = """
        WITH feed_priorities AS (
            SELECT 
                f.id,
                f.domain,
                f.trust_score,
                f.health_score,
                f.daily_quota,
                f.daily_processed,
                CASE 
                    WHEN f.trust_score >= 90 THEN 1
                    WHEN f.trust_score >= 70 THEN 2
                    WHEN f.trust_score >= 50 THEN 3
                    ELSE 4
                END as priority_tier
            FROM feeds f
            WHERE f.status = 'active'
              AND f.health_score >= $1
        ),
        article_candidates AS (
            SELECT 
                ra.id,
                ra.feed_id,
                ra.url,
                ra.url_hash,
                ra.text_hash,
                ra.title,
                ra.fetched_at,
                ra.retry_count,
                fp.domain,
                fp.priority_tier,
                fp.trust_score,
                fp.health_score,
                fp.daily_quota,
                fp.daily_processed,
                -- Calculate priority score
                (
                    fp.trust_score * 0.4 +
                    fp.health_score * 0.3 +
                    CASE 
                        WHEN ra.retry_count = 0 THEN 20  -- Bonus for new articles
                        WHEN ra.retry_count = 1 THEN 10  -- Small bonus for first retry
                        ELSE -ra.retry_count * 5         -- Penalty for multiple retries
                    END +
                    -- Freshness bonus (decay over 24 hours)
                    GREATEST(0, 30 - EXTRACT(EPOCH FROM (NOW() - ra.fetched_at)) / 3600.0) +
                    -- Hot window bonus (last 2 hours)
                    CASE 
                        WHEN ra.fetched_at > NOW() - INTERVAL '2 hours' THEN 15
                        ELSE 0
                    END
                ) as priority_score,
                -- Estimate processing time based on content size and retry count
                CASE 
                    WHEN LENGTH(ra.title) > 200 OR LENGTH(ra.content) > 50000 THEN 2000
                    WHEN ra.retry_count > 1 THEN 1500  -- Retries might be slower
                    ELSE 1000
                END as estimated_processing_time_ms,
                ROW_NUMBER() OVER (
                    PARTITION BY fp.domain 
                    ORDER BY priority_score DESC, ra.fetched_at ASC
                ) as domain_rank
            FROM raw_articles ra
            JOIN feed_priorities fp ON ra.feed_id = fp.id
            WHERE ra.status = 'pending'
              AND ra.lock_owner IS NULL
              AND ra.fetched_at > NOW() - INTERVAL '$2 hours'
              AND (fp.daily_quota = 0 OR fp.daily_processed < fp.daily_quota * 0.95)  -- Leave some quota buffer
        )
        SELECT 
            id, feed_id, url, url_hash, text_hash, title, fetched_at,
            retry_count, priority_score, estimated_processing_time_ms,
            domain, priority_tier
        FROM article_candidates
        WHERE domain_rank <= $3  -- Limit articles per domain for diversity
        ORDER BY 
            priority_tier ASC,           -- Higher trust feeds first
            priority_score DESC,         -- Higher priority articles first
            fetched_at ASC              -- FIFO within same priority
        LIMIT $4
        FOR UPDATE SKIP LOCKED;
        """
        
        # Parameters
        min_quality = config.min_quality_score * 100  # Convert to 0-100 scale
        max_age_hours = config.max_age_hours
        max_per_domain = max(1, int(target_size * config.diversity_factor))
        limit = int(target_size * 1.5)  # Get extra candidates for filtering
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, min_quality, max_age_hours, max_per_domain, limit)
        
        # Convert to candidates
        candidates = []
        domain_counts = {}
        retry_count = 0
        
        for row in rows:
            # Apply retry limit
            if row['retry_count'] > 0:
                retry_count += 1
                retry_percent = (retry_count / len(candidates)) * 100 if candidates else 100
                if retry_percent > config.max_retry_articles_percent:
                    continue
            
            # Apply domain diversity
            domain = row['domain']
            if domain_counts.get(domain, 0) >= max_per_domain:
                continue
            
            # Skip if circuit breaker is open for this feed
            if self._is_circuit_breaker_open(row['feed_id']):
                continue
            
            candidate = BatchCandidate(
                id=row['id'],
                feed_id=row['feed_id'],
                url=row['url'],
                url_hash=row['url_hash'],
                text_hash=row['text_hash'],
                title=row['title'],
                fetched_at=row['fetched_at'],
                retry_count=row['retry_count'],
                priority_score=row['priority_score'],
                estimated_processing_time_ms=row['estimated_processing_time_ms']
            )
            
            candidates.append(candidate)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            
            # Stop when we have enough candidates
            if len(candidates) >= target_size:
                break
        
        logger.info(f"Selected {len(candidates)} candidates from {len(domain_counts)} domains "
                   f"(retry articles: {retry_count}, {(retry_count/len(candidates)*100):.1f}%)")
        
        return candidates
    
    async def _create_batch_record(self,
                                  candidates: List[BatchCandidate],
                                  config: BatchConfiguration,
                                  worker_id: str,
                                  correlation_id: Optional[str],
                                  load_metrics: LoadMetrics) -> str:
        """Create batch record in database"""
        batch_id = f"batch_{int(time.time())}_{uuid4().hex[:8]}"
        correlation_id = correlation_id or f"corr_{uuid4().hex[:16]}"
        
        # Calculate batch metadata
        total_estimated_time = sum(c.estimated_processing_time_ms for c in candidates)
        avg_priority_score = sum(c.priority_score for c in candidates) / len(candidates)
        retry_articles = sum(1 for c in candidates if c.is_retry)
        
        # Create configuration hash for reproducibility
        config_hash = hashlib.sha256(
            json.dumps(config.dict(), sort_keys=True).encode()
        ).hexdigest()[:16]
        
        query = """
        INSERT INTO batches (
            batch_id, batch_size, articles_total, status, current_stage,
            priority, worker_id, correlation_id, idempotency_key,
            estimated_completion, processing_config, config_hash,
            processing_version, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW()
        )
        """
        
        estimated_completion = datetime.utcnow() + timedelta(
            seconds=total_estimated_time / 1000.0 / max(1, load_metrics.active_workers)
        )
        
        processing_config = {
            "target_size": config.target_size,
            "actual_size": len(candidates),
            "avg_priority_score": avg_priority_score,
            "retry_articles_count": retry_articles,
            "retry_articles_percent": (retry_articles / len(candidates)) * 100,
            "load_factor": load_metrics.load_factor(),
            "diversity_domains": len(set(c.url.split('/')[2] for c in candidates if c.url)),
            "estimated_total_time_ms": total_estimated_time
        }
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                batch_id,
                len(candidates),
                len(candidates),
                BatchStatus.READY.value,
                "ready",
                config.priority.value,
                worker_id,
                correlation_id,
                f"{batch_id}_{worker_id}",
                estimated_completion,
                json.dumps(processing_config),
                config_hash,
                "1.0"
            )
        
        return batch_id
    
    async def _lock_articles(self, 
                           candidates: List[BatchCandidate],
                           batch_id: str,
                           worker_id: str) -> None:
        """Lock selected articles for processing"""
        article_ids = [c.id for c in candidates]
        
        query = """
        UPDATE raw_articles 
        SET 
            status = 'processing',
            batch_id = $1,
            lock_owner = $2,
            lock_acquired_at = NOW(),
            lock_expires_at = NOW() + INTERVAL '2 hours',
            updated_at = NOW()
        WHERE id = ANY($3::bigint[])
          AND status = 'pending'
          AND lock_owner IS NULL
        """
        
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(query, batch_id, worker_id, article_ids)
            locked_count = int(result.split()[-1])
            
            if locked_count != len(candidates):
                logger.warning(f"Only locked {locked_count} of {len(candidates)} articles in batch {batch_id}")
                # Update batch record with actual locked count
                await conn.execute(
                    "UPDATE batches SET articles_total = $1, batch_size = $1 WHERE batch_id = $2",
                    locked_count, batch_id
                )
    
    async def _get_load_metrics(self) -> LoadMetrics:
        """Get current system load metrics"""
        try:
            # Get from Redis cache first
            cached_metrics = await self.redis.hgetall("system:load_metrics")
            if cached_metrics:
                return LoadMetrics(
                    active_workers=int(cached_metrics.get(b'active_workers', 0)),
                    avg_batch_time_seconds=float(cached_metrics.get(b'avg_batch_time_seconds', 0)),
                    queue_depth=int(cached_metrics.get(b'queue_depth', 0)),
                    error_rate_1h=float(cached_metrics.get(b'error_rate_1h', 0)),
                    memory_usage_percent=float(cached_metrics.get(b'memory_usage_percent', 0)),
                    cpu_usage_percent=float(cached_metrics.get(b'cpu_usage_percent', 0)),
                    disk_io_wait_percent=float(cached_metrics.get(b'disk_io_wait_percent', 0))
                )
            
            # Calculate from database if not cached
            async with self.db_pool.acquire() as conn:
                # Active workers
                active_workers = await conn.fetchval(
                    "SELECT COUNT(DISTINCT worker_id) FROM batches WHERE status = 'processing'"
                )
                
                # Queue depth
                queue_depth = await conn.fetchval(
                    "SELECT COUNT(*) FROM raw_articles WHERE status = 'pending'"
                )
                
                # Average batch time from recent batches
                avg_batch_time = await conn.fetchval("""
                    SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FROM batches 
                    WHERE completed_at IS NOT NULL 
                      AND started_at > NOW() - INTERVAL '1 hour'
                """) or 0.0
                
                # Error rate from recent batches
                error_rate = await conn.fetchval("""
                    SELECT 
                        COALESCE(
                            (SUM(articles_failed)::float / NULLIF(SUM(articles_total), 0)) * 100,
                            0
                        ) as error_rate
                    FROM batches 
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                """) or 0.0
            
            metrics = LoadMetrics(
                active_workers=active_workers or 0,
                avg_batch_time_seconds=avg_batch_time,
                queue_depth=queue_depth or 0,
                error_rate_1h=error_rate
            )
            
            # Cache for 1 minute
            await self.redis.hmset("system:load_metrics", {
                "active_workers": metrics.active_workers,
                "avg_batch_time_seconds": metrics.avg_batch_time_seconds,
                "queue_depth": metrics.queue_depth,
                "error_rate_1h": metrics.error_rate_1h,
                "timestamp": time.time()
            })
            await self.redis.expire("system:load_metrics", 60)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get load metrics: {e}")
            return LoadMetrics()  # Return defaults on error
    
    async def _get_feed_health_metrics(self) -> Dict[int, FeedHealthMetrics]:
        """Get feed health metrics with caching"""
        current_time = time.time()
        
        # Use cache if fresh
        if (current_time - self._last_cache_refresh) < self._cache_ttl_seconds and self._feed_metrics_cache:
            return self._feed_metrics_cache
        
        query = """
        SELECT 
            id, domain, trust_score, health_score, avg_response_time_ms,
            error_rate_24h, duplicate_rate_24h, content_quality_score,
            daily_quota, daily_processed, consecutive_failures, last_success
        FROM feeds
        WHERE status = 'active'
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        metrics = {}
        for row in rows:
            metrics[row['id']] = FeedHealthMetrics(
                feed_id=row['id'],
                domain=row['domain'],
                trust_score=row['trust_score'],
                health_score=row['health_score'],
                avg_response_time_ms=row['avg_response_time_ms'],
                error_rate_24h=row['error_rate_24h'] or 0.0,
                duplicate_rate_24h=row['duplicate_rate_24h'] or 0.0,
                content_quality_score=row['content_quality_score'] or 1.0,
                daily_quota=row['daily_quota'] or 0,
                daily_processed=row['daily_processed'] or 0,
                consecutive_failures=row['consecutive_failures'] or 0,
                last_success=row['last_success']
            )
        
        self._feed_metrics_cache = metrics
        self._last_cache_refresh = current_time
        
        return metrics
    
    def _is_circuit_breaker_open(self, feed_id: int) -> bool:
        """Check if circuit breaker is open for a feed"""
        breaker = self.circuit_breakers.get(feed_id)
        if not breaker:
            return False
        
        # Circuit breaker states: CLOSED, OPEN, HALF_OPEN
        if breaker['state'] == 'CLOSED':
            return False
        elif breaker['state'] == 'OPEN':
            # Check if we should transition to HALF_OPEN
            if time.time() - breaker['last_failure'] > breaker.get('timeout', 300):  # 5 min default
                breaker['state'] = 'HALF_OPEN'
                return False
            return True
        else:  # HALF_OPEN
            return False  # Allow some traffic through
    
    async def record_batch_outcome(self,
                                  batch_id: str,
                                  success_rate: float,
                                  processing_time_seconds: float,
                                  load_factor: float,
                                  batch_size: int) -> None:
        """Record batch outcome for adaptive learning"""
        # Store in sizing history for future optimization
        self.sizing_history.append((load_factor, batch_size, success_rate))
        
        # Keep only recent history
        if len(self.sizing_history) > self.max_history_size:
            self.sizing_history.pop(0)
        
        # Update circuit breakers based on feed performance in this batch
        # This would be implemented based on per-feed outcomes within the batch
        
        # Record metrics
        await self.metrics.histogram("batch.success_rate", success_rate)
        await self.metrics.histogram("batch.processing_time", processing_time_seconds)
        await self.metrics.histogram("batch.size_actual", batch_size)
    
    async def _acquire_lock(self, lock_key: str, owner: str, timeout_seconds: int = 30) -> bool:
        """Acquire distributed lock"""
        try:
            # Try to acquire lock in Redis first (faster)
            redis_key = f"lock:{lock_key}"
            acquired = await self.redis.set(
                redis_key, owner, nx=True, ex=timeout_seconds
            )
            
            if acquired:
                return True
            
            # Fall back to PostgreSQL advisory locks
            async with self.db_pool.acquire() as conn:
                # Use hash of lock_key as lock ID
                lock_id = hash(lock_key) % (2**31)  # 32-bit signed int
                
                result = await conn.fetchval(
                    "SELECT pg_try_advisory_lock($1)",
                    lock_id
                )
                
                if result:
                    # Store lock info for cleanup
                    await conn.execute(
                        """INSERT INTO distributed_locks (lock_key, owner, expires_at, metadata)
                           VALUES ($1, $2, NOW() + INTERVAL '%s seconds', $3)
                           ON CONFLICT (lock_key) DO UPDATE SET
                           owner = $2, acquired_at = NOW(), expires_at = NOW() + INTERVAL '%s seconds'""" % (timeout_seconds, timeout_seconds),
                        lock_key, owner, json.dumps({"type": "advisory", "lock_id": lock_id})
                    )
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Failed to acquire lock {lock_key}: {e}")
            return False
    
    async def _release_lock(self, lock_key: str, owner: str) -> bool:
        """Release distributed lock"""
        try:
            # Release Redis lock
            redis_key = f"lock:{lock_key}"
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await self.redis.eval(script, 1, redis_key, owner)
            
            # Release PostgreSQL lock
            async with self.db_pool.acquire() as conn:
                lock_info = await conn.fetchrow(
                    "SELECT metadata FROM distributed_locks WHERE lock_key = $1 AND owner = $2",
                    lock_key, owner
                )
                
                if lock_info and lock_info['metadata']:
                    metadata = json.loads(lock_info['metadata'])
                    if metadata.get('type') == 'advisory':
                        lock_id = metadata.get('lock_id')
                        if lock_id:
                            await conn.fetchval("SELECT pg_advisory_unlock($1)", lock_id)
                
                # Clean up lock record
                await conn.execute(
                    "DELETE FROM distributed_locks WHERE lock_key = $1 AND owner = $2",
                    lock_key, owner
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to release lock {lock_key}: {e}")
            return False
    
    async def cleanup_expired_locks(self) -> int:
        """Clean up expired locks and reset article states"""
        try:
            async with self.db_pool.acquire() as conn:
                # Reset articles with expired locks
                reset_count = await conn.fetchval("""
                    WITH expired_articles AS (
                        UPDATE raw_articles 
                        SET 
                            status = 'pending',
                            batch_id = NULL,
                            lock_owner = NULL,
                            lock_acquired_at = NULL,
                            lock_expires_at = NULL,
                            updated_at = NOW()
                        WHERE lock_expires_at < NOW() 
                          AND lock_owner IS NOT NULL
                        RETURNING id
                    )
                    SELECT COUNT(*) FROM expired_articles
                """)
                
                # Clean up expired distributed locks
                await conn.execute("DELETE FROM distributed_locks WHERE expires_at < NOW()")
                
                # Update batch statuses for orphaned batches
                await conn.execute("""
                    UPDATE batches 
                    SET status = 'failed', 
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE status IN ('processing', 'ready')
                      AND (
                          started_at IS NULL OR started_at < NOW() - INTERVAL '4 hours'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM raw_articles 
                          WHERE batch_id = batches.batch_id 
                            AND lock_owner IS NOT NULL
                      )
                """)
                
                if reset_count > 0:
                    logger.info(f"Reset {reset_count} articles with expired locks")
                    await self.metrics.increment("locks.expired_cleaned", reset_count)
                
                return reset_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired locks: {e}")
            return 0
    
    async def get_batch_queue_status(self) -> Dict:
        """Get current batch queue status"""
        try:
            async with self.db_pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status = 'pending') as pending_articles,
                        COUNT(*) FILTER (WHERE status = 'processing') as processing_articles,
                        COUNT(DISTINCT batch_id) FILTER (WHERE batch_id IS NOT NULL) as active_batches,
                        COUNT(DISTINCT lock_owner) FILTER (WHERE lock_owner IS NOT NULL) as active_workers,
                        AVG(EXTRACT(EPOCH FROM (NOW() - fetched_at))) FILTER (WHERE status = 'pending') as avg_queue_age_seconds
                    FROM raw_articles 
                    WHERE fetched_at > NOW() - INTERVAL '24 hours'
                """)
                
                batch_stats = await conn.fetch("""
                    SELECT 
                        status,
                        COUNT(*) as count,
                        AVG(articles_total) as avg_size,
                        AVG(EXTRACT(EPOCH FROM (NOW() - created_at))) as avg_age_seconds
                    FROM batches 
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                    GROUP BY status
                    ORDER BY status
                """)
                
                return {
                    "pending_articles": stats['pending_articles'] or 0,
                    "processing_articles": stats['processing_articles'] or 0,
                    "active_batches": stats['active_batches'] or 0,
                    "active_workers": stats['active_workers'] or 0,
                    "avg_queue_age_hours": (stats['avg_queue_age_seconds'] or 0) / 3600,
                    "batch_status_distribution": {
                        row['status']: {
                            "count": row['count'],
                            "avg_size": float(row['avg_size'] or 0),
                            "avg_age_hours": (row['avg_age_seconds'] or 0) / 3600
                        }
                        for row in batch_stats
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get batch queue status: {e}")
            return {}


# Utility functions for batch management
async def create_emergency_batch(planner: BatchPlanner, 
                                worker_id: str,
                                max_size: int = 50) -> Optional[str]:
    """Create a small emergency batch for urgent processing"""
    config = BatchConfiguration(
        target_size=max_size,
        min_size=10,
        max_size=max_size,
        priority=BatchPriority.CRITICAL,
        max_age_hours=1.0,  # Only very fresh articles
        min_quality_score=0.7,  # Higher quality threshold
        diversity_factor=0.5  # More diversity for emergency batch
    )
    
    return await planner.create_batch(config, worker_id, f"emergency_{int(time.time())}")


async def create_cleanup_batch(planner: BatchPlanner,
                              worker_id: str,
                              max_age_hours: float = 168.0) -> Optional[str]:
    """Create a batch for processing old/retry articles"""
    config = BatchConfiguration(
        target_size=100,
        min_size=50,
        max_size=150,
        priority=BatchPriority.LOW,
        max_age_hours=max_age_hours,  # Up to 1 week old
        min_quality_score=0.2,  # Lower quality threshold
        max_retry_articles_percent=80.0,  # Mostly retry articles
        diversity_factor=0.1  # Less diversity needed
    )
    
    return await planner.create_batch(config, worker_id, f"cleanup_{int(time.time())}")


if __name__ == "__main__":
    # Example usage and testing
    import asyncio
    from config import Config
    from monitoring import MetricsCollector
    
    async def test_batch_planner():
        config = Config()
        
        # Mock database and Redis connections
        # In real usage, these would be properly initialized
        db_pool = None  # asyncpg.create_pool(...)
        redis_client = None  # redis.Redis(...)
        metrics = MetricsCollector()
        
        planner = BatchPlanner(db_pool, redis_client, metrics, config)
        
        # Test configuration
        batch_config = BatchConfiguration(
            target_size=200,
            priority=BatchPriority.NORMAL,
            max_age_hours=24.0
        )
        
        # This would work with real connections
        # batch_id = await planner.create_batch(batch_config, "test_worker_1")
        # print(f"Created batch: {batch_id}")
        
        print("Batch planner initialized successfully")
    
    # asyncio.run(test_batch_planner())