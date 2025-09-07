"""
Production-grade Celery Task Queue System for RSS Processing
Handles distributed task execution with prioritization, retry logic, and comprehensive monitoring.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from celery import Celery, Task
from celery.exceptions import Retry, WorkerLostError
from celery.signals import task_prerun, task_postrun, task_failure, task_success
from kombu import Queue, Exchange

from batch_planner import BatchPlanner, BatchConfiguration, BatchPriority
from pipeline_processor import PipelineProcessor
from monitoring import MetricsCollector, AlertManager
from config import Config

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class TaskType(Enum):
    """Types of tasks in the system"""
    PROCESS_BATCH = "process_batch"
    FEED_DISCOVERY = "feed_discovery"
    FEED_HEALTH_CHECK = "feed_health_check"
    CLEANUP_EXPIRED_LOCKS = "cleanup_expired_locks"
    MAINTENANCE = "maintenance"
    EMERGENCY_BATCH = "emergency_batch"


# Celery configuration
celery_config = {
    'broker_url': 'redis://localhost:6379/1',
    'result_backend': 'redis://localhost:6379/2',
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'UTC',
    'enable_utc': True,
    
    # Task routing
    'task_routes': {
        'rss_pipeline.process_batch': {'queue': 'batch_processing'},
        'rss_pipeline.feed_discovery': {'queue': 'feed_management'},
        'rss_pipeline.feed_health_check': {'queue': 'maintenance'},
        'rss_pipeline.cleanup_expired_locks': {'queue': 'maintenance'},
        'rss_pipeline.emergency_batch': {'queue': 'emergency'},
    },
    
    # Queue definitions with priorities
    'task_default_queue': 'default',
    'task_queues': (
        Queue('emergency', Exchange('emergency'), routing_key='emergency',
              queue_arguments={'x-max-priority': 10}),
        Queue('batch_processing', Exchange('batch_processing'), routing_key='batch_processing',
              queue_arguments={'x-max-priority': 5}),
        Queue('feed_management', Exchange('feed_management'), routing_key='feed_management',
              queue_arguments={'x-max-priority': 3}),
        Queue('maintenance', Exchange('maintenance'), routing_key='maintenance',
              queue_arguments={'x-max-priority': 1}),
        Queue('default', Exchange('default'), routing_key='default'),
    ),
    
    # Worker configuration
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
    'task_reject_on_worker_lost': True,
    
    # Retry configuration
    'task_default_retry_delay': 60,
    'task_max_retries': 3,
    
    # Monitoring
    'worker_send_task_events': True,
    'task_send_sent_event': True,
    
    # Result expiration
    'result_expires': 3600,  # 1 hour
    
    # Task time limits
    'task_time_limit': 1800,  # 30 minutes
    'task_soft_time_limit': 1500,  # 25 minutes
}

# Initialize Celery app
celery_app = Celery('rss_pipeline', **celery_config)


class BaseTask(Task):
    """Base task class with enhanced error handling and monitoring"""
    
    abstract = True
    autoretry_for = (Exception,)
    default_retry_delay = 60
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3
    
    def __init__(self):
        self.metrics: Optional[MetricsCollector] = None
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        
    def retry(self, args=None, kwargs=None, exc=None, throw=True,
              eta=None, countdown=None, max_retries=None, **options):
        """Enhanced retry with exponential backoff and jitter"""
        
        if self.request.retries >= (max_retries or self.max_retries):
            logger.error(f"Task {self.name} exhausted retries after {self.request.retries} attempts")
            if self.metrics:
                asyncio.create_task(self.metrics.increment(
                    'task.retries_exhausted',
                    tags={'task_type': self.name, 'exception': str(type(exc).__name__)}
                ))
            raise exc
        
        # Calculate exponential backoff with jitter
        base_delay = self.default_retry_delay
        exponential_delay = base_delay * (2 ** self.request.retries)
        max_delay = min(exponential_delay, self.retry_backoff_max)
        
        if self.retry_jitter:
            import random
            jitter = random.uniform(0.8, 1.2)
            delay = max_delay * jitter
        else:
            delay = max_delay
        
        logger.warning(f"Retrying task {self.name} in {delay:.1f}s (attempt {self.request.retries + 1})")
        
        if self.metrics:
            asyncio.create_task(self.metrics.increment(
                'task.retry',
                tags={'task_type': self.name, 'retry_count': str(self.request.retries)}
            ))
        
        return super().retry(
            args=args, kwargs=kwargs, exc=exc, throw=throw,
            countdown=int(delay), max_retries=max_retries, **options
        )
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success"""
        if self.metrics:
            asyncio.create_task(self.metrics.increment(
                'task.success',
                tags={'task_type': self.name}
            ))
        
        logger.info(f"Task {self.name} ({task_id}) completed successfully")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure"""
        if self.metrics:
            asyncio.create_task(self.metrics.increment(
                'task.failure',
                tags={'task_type': self.name, 'exception': str(type(exc).__name__)}
            ))
        
        logger.error(f"Task {self.name} ({task_id}) failed: {exc}", exc_info=einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called on task retry"""
        logger.warning(f"Task {self.name} ({task_id}) retry {self.request.retries}: {exc}")


@celery_app.task(base=BaseTask, bind=True, name='rss_pipeline.process_batch')
def process_batch_task(self, batch_id: str, worker_id: str = None) -> Dict[str, Any]:
    """
    Process a complete batch through all pipeline stages
    
    Args:
        batch_id: Unique batch identifier
        worker_id: Worker identifier (generated if not provided)
        
    Returns:
        Dict with processing results and statistics
    """
    start_time = time.time()
    worker_id = worker_id or f"worker_{self.request.hostname}_{self.request.id[:8]}"
    
    logger.info(f"Starting batch processing: {batch_id} (worker: {worker_id})")
    
    try:
        # Initialize components (would be dependency-injected in production)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _process():
            # Initialize database connection
            db_pool = await asyncpg.create_pool(
                dsn=os.environ.get('PG_DSN'),
                min_size=2,
                max_size=10
            )
            
            # Initialize Redis client
            redis_client = redis.Redis.from_url('redis://localhost:6379/0')
            
            # Initialize metrics collector
            metrics = MetricsCollector(redis_client, db_pool)
            await metrics.initialize()
            
            # Initialize config (simplified)
            config = Config()
            
            # Initialize pipeline processor
            processor = PipelineProcessor(db_pool, redis_client, metrics, config)
            
            try:
                # Process the batch
                result = await processor.process_batch(batch_id, worker_id)
                
                # Record success metrics
                processing_time = time.time() - start_time
                await metrics.timing('task.process_batch.duration', processing_time)
                await metrics.increment('task.process_batch.success')
                
                logger.info(f"Batch {batch_id} processed successfully in {processing_time:.2f}s")
                
                return {
                    'success': True,
                    'batch_id': batch_id,
                    'worker_id': worker_id,
                    'processing_time': processing_time,
                    'articles_processed': result.get('articles_processed', 0),
                    'articles_successful': result.get('articles_successful', 0),
                    'completed_at': datetime.utcnow().isoformat()
                }
                
            finally:
                # Cleanup
                await metrics.shutdown()
                await redis_client.close()
                await db_pool.close()
        
        # Run async processing
        return loop.run_until_complete(_process())
        
    except Exception as exc:
        processing_time = time.time() - start_time
        logger.error(f"Batch processing failed for {batch_id}: {exc}", exc_info=True)
        
        # Determine if we should retry
        if isinstance(exc, (asyncpg.PostgresConnectionError, redis.ConnectionError)):
            # Connection issues - retry with backoff
            self.retry(exc=exc)
        elif processing_time > 1500:  # 25 minutes - soft time limit
            # Don't retry timeouts
            raise exc
        else:
            # Other errors - retry up to max_retries
            self.retry(exc=exc)
    
    finally:
        loop.close()


@celery_app.task(base=BaseTask, bind=True, name='rss_pipeline.create_batch')
def create_batch_task(self, 
                     worker_id: str = None,
                     batch_config: Dict[str, Any] = None,
                     priority: str = 'normal') -> Optional[str]:
    """
    Create a new batch for processing
    
    Args:
        worker_id: Worker identifier
        batch_config: Batch configuration parameters
        priority: Batch priority level
        
    Returns:
        Batch ID if created successfully, None otherwise
    """
    worker_id = worker_id or f"planner_{self.request.hostname}_{self.request.id[:8]}"
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _create():
            # Initialize components
            db_pool = await asyncpg.create_pool(
                dsn=os.environ.get('PG_DSN'),
                min_size=1,
                max_size=5
            )
            
            redis_client = redis.Redis.from_url('redis://localhost:6379/0')
            metrics = MetricsCollector(redis_client, db_pool)
            await metrics.initialize()
            
            config = Config()
            
            # Initialize batch planner
            planner = BatchPlanner(db_pool, redis_client, metrics, config)
            
            try:
                # Create batch configuration
                batch_priority = {
                    'critical': BatchPriority.CRITICAL,
                    'high': BatchPriority.HIGH,
                    'normal': BatchPriority.NORMAL,
                    'low': BatchPriority.LOW,
                    'background': BatchPriority.BACKGROUND
                }.get(priority, BatchPriority.NORMAL)
                
                config_obj = BatchConfiguration(
                    priority=batch_priority,
                    **(batch_config or {})
                )
                
                # Create batch
                batch_id = await planner.create_batch(
                    config_obj,
                    worker_id,
                    correlation_id=f"create_{self.request.id}"
                )
                
                if batch_id:
                    logger.info(f"Created batch {batch_id} with priority {priority}")
                    await metrics.increment('batch.created', tags={'priority': priority})
                    
                    # Schedule batch processing
                    process_batch_task.apply_async(
                        args=[batch_id, worker_id],
                        priority=batch_priority.value,
                        queue='batch_processing'
                    )
                    
                return batch_id
                
            finally:
                await metrics.shutdown()
                await redis_client.close()
                await db_pool.close()
        
        return loop.run_until_complete(_create())
        
    except Exception as exc:
        logger.error(f"Failed to create batch: {exc}", exc_info=True)
        self.retry(exc=exc)
    
    finally:
        loop.close()


@celery_app.task(base=BaseTask, bind=True, name='rss_pipeline.cleanup_expired_locks')
def cleanup_expired_locks_task(self) -> int:
    """
    Clean up expired locks and reset article states
    
    Returns:
        Number of locks cleaned up
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _cleanup():
            db_pool = await asyncpg.create_pool(
                dsn=os.environ.get('PG_DSN'),
                min_size=1,
                max_size=3
            )
            
            redis_client = redis.Redis.from_url('redis://localhost:6379/0')
            metrics = MetricsCollector(redis_client, db_pool)
            config = Config()
            
            # Initialize batch planner for cleanup functionality
            planner = BatchPlanner(db_pool, redis_client, metrics, config)
            
            try:
                cleaned_count = await planner.cleanup_expired_locks()
                
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} expired locks")
                    await metrics.increment('maintenance.locks_cleaned', cleaned_count)
                
                return cleaned_count
                
            finally:
                await redis_client.close()
                await db_pool.close()
        
        return loop.run_until_complete(_cleanup())
        
    except Exception as exc:
        logger.error(f"Lock cleanup failed: {exc}", exc_info=True)
        self.retry(exc=exc)
    
    finally:
        loop.close()


@celery_app.task(base=BaseTask, bind=True, name='rss_pipeline.emergency_batch')
def emergency_batch_task(self, max_size: int = 50, worker_id: str = None) -> Optional[str]:
    """
    Create and process an emergency batch for urgent articles
    
    Args:
        max_size: Maximum batch size
        worker_id: Worker identifier
        
    Returns:
        Batch ID if successful
    """
    worker_id = worker_id or f"emergency_{self.request.id[:8]}"
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _emergency():
            db_pool = await asyncpg.create_pool(
                dsn=os.environ.get('PG_DSN'),
                min_size=1,
                max_size=5
            )
            
            redis_client = redis.Redis.from_url('redis://localhost:6379/0')
            metrics = MetricsCollector(redis_client, db_pool)
            await metrics.initialize()
            
            config = Config()
            planner = BatchPlanner(db_pool, redis_client, metrics, config)
            
            try:
                # Import utility function
                from batch_planner import create_emergency_batch
                
                batch_id = await create_emergency_batch(planner, worker_id, max_size)
                
                if batch_id:
                    logger.warning(f"Created emergency batch {batch_id}")
                    await metrics.increment('batch.emergency_created')
                    
                    # Process immediately with highest priority
                    process_batch_task.apply_async(
                        args=[batch_id, worker_id],
                        priority=TaskPriority.CRITICAL.value,
                        queue='emergency'
                    )
                
                return batch_id
                
            finally:
                await metrics.shutdown()
                await redis_client.close()
                await db_pool.close()
        
        return loop.run_until_complete(_emergency())
        
    except Exception as exc:
        logger.error(f"Emergency batch creation failed: {exc}", exc_info=True)
        # Don't retry emergency batches - they're time-sensitive
        raise exc
    
    finally:
        loop.close()


@celery_app.task(base=BaseTask, bind=True, name='rss_pipeline.feed_health_check')
def feed_health_check_task(self, feed_ids: List[int] = None) -> Dict[str, Any]:
    """
    Check health of feeds and update scores
    
    Args:
        feed_ids: Specific feed IDs to check (None for all)
        
    Returns:
        Health check results
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _health_check():
            db_pool = await asyncpg.create_pool(
                dsn=os.environ.get('PG_DSN'),
                min_size=1,
                max_size=3
            )
            
            try:
                # Update feed health scores
                async with db_pool.acquire() as conn:
                    if feed_ids:
                        await conn.execute("""
                            SELECT update_feed_health_scores()
                            WHERE EXISTS (SELECT 1 FROM feeds WHERE id = ANY($1))
                        """, feed_ids)
                        updated_count = len(feed_ids)
                    else:
                        await conn.execute("SELECT update_feed_health_scores()")
                        updated_count = await conn.fetchval(
                            "SELECT COUNT(*) FROM feeds WHERE last_crawled > NOW() - INTERVAL '24 hours'"
                        )
                
                logger.info(f"Updated health scores for {updated_count} feeds")
                
                return {
                    'success': True,
                    'updated_feeds': updated_count,
                    'checked_at': datetime.utcnow().isoformat()
                }
                
            finally:
                await db_pool.close()
        
        return loop.run_until_complete(_health_check())
        
    except Exception as exc:
        logger.error(f"Feed health check failed: {exc}", exc_info=True)
        self.retry(exc=exc)
    
    finally:
        loop.close()


class TaskScheduler:
    """
    Intelligent task scheduler with automatic batch creation and priority management
    """
    
    def __init__(self, 
                 redis_client: redis.Redis,
                 metrics: MetricsCollector,
                 config: Config):
        self.redis = redis_client
        self.metrics = metrics
        self.config = config
        self.scheduler_id = f"scheduler_{uuid4().hex[:8]}"
        
        # Scheduling parameters
        self.batch_check_interval = 30  # seconds
        self.emergency_threshold = 1000  # pending articles
        self.cleanup_interval = 3600  # 1 hour
        self.health_check_interval = 1800  # 30 minutes
        
        # State
        self.running = False
        self.last_batch_created = time.time()
        
    async def start(self):
        """Start the task scheduler"""
        self.running = True
        
        # Schedule periodic tasks
        asyncio.create_task(self._batch_creation_loop())
        asyncio.create_task(self._maintenance_loop())
        asyncio.create_task(self._emergency_monitor_loop())
        
        logger.info(f"Task scheduler {self.scheduler_id} started")
    
    async def stop(self):
        """Stop the task scheduler"""
        self.running = False
        logger.info(f"Task scheduler {self.scheduler_id} stopped")
    
    async def _batch_creation_loop(self):
        """Periodically create new batches based on queue depth"""
        while self.running:
            try:
                await asyncio.sleep(self.batch_check_interval)
                
                # Check queue depth
                queue_depth = await self._get_queue_depth()
                
                if queue_depth > 0:
                    # Determine batch priority based on queue age and depth
                    priority = await self._determine_batch_priority(queue_depth)
                    
                    # Create batch
                    batch_id = await self._create_scheduled_batch(priority)
                    
                    if batch_id:
                        self.last_batch_created = time.time()
                        logger.info(f"Scheduled batch {batch_id} with priority {priority}")
                
            except Exception as e:
                logger.error(f"Error in batch creation loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _maintenance_loop(self):
        """Periodically run maintenance tasks"""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                # Schedule cleanup task
                cleanup_expired_locks_task.apply_async(
                    queue='maintenance',
                    priority=TaskPriority.LOW.value
                )
                
                # Schedule feed health check
                feed_health_check_task.apply_async(
                    queue='maintenance',
                    priority=TaskPriority.LOW.value
                )
                
                logger.info("Scheduled maintenance tasks")
                
            except Exception as e:
                logger.error(f"Error in maintenance loop: {e}", exc_info=True)
    
    async def _emergency_monitor_loop(self):
        """Monitor for emergency conditions and create emergency batches"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                queue_depth = await self._get_queue_depth()
                
                # Check for emergency conditions
                if queue_depth > self.emergency_threshold:
                    # Check if we haven't created a batch recently
                    time_since_last = time.time() - self.last_batch_created
                    
                    if time_since_last > 300:  # 5 minutes
                        logger.warning(f"Emergency condition detected: {queue_depth} pending articles")
                        
                        # Create emergency batch
                        emergency_batch_task.apply_async(
                            args=[100],  # Larger emergency batch
                            queue='emergency',
                            priority=TaskPriority.CRITICAL.value
                        )
                        
                        self.last_batch_created = time.time()
                        await self.metrics.increment('scheduler.emergency_batch_created')
                
            except Exception as e:
                logger.error(f"Error in emergency monitor loop: {e}", exc_info=True)
    
    async def _get_queue_depth(self) -> int:
        """Get current queue depth from Redis cache or database"""
        try:
            # Try Redis first
            cached_depth = await self.redis.get("queue:depth")
            if cached_depth:
                return int(cached_depth)
            
            # Fallback to database query
            # This would need a database connection - simplified for now
            return 0
            
        except Exception as e:
            logger.error(f"Failed to get queue depth: {e}")
            return 0
    
    async def _determine_batch_priority(self, queue_depth: int) -> str:
        """Determine batch priority based on queue conditions"""
        if queue_depth > 5000:
            return 'high'
        elif queue_depth > 1000:
            return 'normal'
        else:
            return 'low'
    
    async def _create_scheduled_batch(self, priority: str) -> Optional[str]:
        """Create a scheduled batch"""
        try:
            result = create_batch_task.apply_async(
                kwargs={
                    'worker_id': self.scheduler_id,
                    'priority': priority
                },
                queue='batch_processing',
                priority=TaskPriority.NORMAL.value
            )
            
            # Wait for batch creation (with timeout)
            batch_id = result.get(timeout=30)
            return batch_id
            
        except Exception as e:
            logger.error(f"Failed to create scheduled batch: {e}")
            return None


# Celery signal handlers for monitoring
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Record task start metrics"""
    logger.info(f"Task {task.name} ({task_id}) starting")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Record task completion metrics"""
    logger.info(f"Task {task.name} ({task_id}) completed with state: {state}")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Handle task failures"""
    logger.error(f"Task {sender.name} ({task_id}) failed: {exception}")


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Handle task success"""
    logger.debug(f"Task {sender.name} succeeded")


# Configuration class placeholder
class Config:
    """Simple configuration class - would be enhanced in production"""
    def get(self, key: str, default=None):
        return default


if __name__ == "__main__":
    # Example usage
    print("RSS Processing Task Queue System")
    print("Available tasks:")
    print("- process_batch_task: Process a batch through all pipeline stages")
    print("- create_batch_task: Create a new batch for processing")
    print("- cleanup_expired_locks_task: Clean up expired locks")
    print("- emergency_batch_task: Create emergency batch for urgent processing")
    print("- feed_health_check_task: Check and update feed health scores")
    print("\nTo run worker: celery -A task_queue worker --loglevel=info")
    print("To run scheduler: celery -A task_queue beat --loglevel=info")