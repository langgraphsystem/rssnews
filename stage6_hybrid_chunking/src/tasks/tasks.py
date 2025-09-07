"""
Celery tasks for Stage 6 processing.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import structlog
from celery import Task
from celery.exceptions import Retry
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete

from src.celery_app import celery_app
from src.config.settings import Settings
from src.db.models import Article, ArticleChunk
from src.stage6.pipeline import Stage6Pipeline
from src.stage6.processor import ChunkProcessor, BatchConfiguration
from src.utils.metrics import InMemoryMetrics, Stage6Metrics
from src.utils.health import create_stage6_health_checker
from src.utils.tracing import initialize_tracing, traced_operation
from src.utils.logging import configure_logging, ComponentLogger

logger = structlog.get_logger(__name__)


class DatabaseTask(Task):
    """Base task with database session management."""
    
    _settings: Optional[Settings] = None
    _db_engine = None
    _session_factory = None
    
    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings()
            # Configure logging for tasks
            configure_logging(
                log_level=self._settings.observability.log_level,
                log_format=self._settings.observability.log_format,
                enable_tracing=self._settings.observability.tracing_enabled
            )
        return self._settings
    
    @property
    def db_engine(self):
        if self._db_engine is None:
            self._db_engine = create_async_engine(
                self.settings.database_url,
                echo=self.settings.db.echo_sql,
                pool_size=self.settings.db.pool_size,
                max_overflow=self.settings.db.max_overflow,
                pool_timeout=self.settings.db.pool_timeout,
                pool_pre_ping=True
            )
        return self._db_engine
    
    @property 
    def session_factory(self):
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                self.db_engine, 
                class_=AsyncSession, 
                expire_on_commit=False
            )
        return self._session_factory
    
    async def get_db_session(self) -> AsyncSession:
        """Create database session."""
        return self.session_factory()


def run_async_task(coro):
    """Helper to run async code in Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, base=DatabaseTask, name='stage6.tasks.process_articles_task')
def process_articles_task(self, article_ids: List[int], context: Optional[Dict] = None):
    """
    Process articles through Stage 6 pipeline.
    
    Args:
        article_ids: List of article IDs to process
        context: Optional processing context
        
    Returns:
        Processing result dictionary
    """
    task_logger = ComponentLogger("celery_task", task_id=self.request.id)
    task_logger.info("Starting article processing task", article_count=len(article_ids))
    
    async def _process_articles():
        # Initialize tracing if enabled
        if self.settings.observability.tracing_enabled:
            initialize_tracing(
                service_name="stage6-celery-worker",
                jaeger_endpoint=getattr(self.settings, 'jaeger_endpoint', None)
            )
        
        async with traced_operation("celery_process_articles_task", {
            "task_id": self.request.id,
            "article_count": len(article_ids)
        }):
            db_session = await self.get_db_session()
            
            try:
                # Create processor
                processor = ChunkProcessor(self.settings, db_session)
                
                # Add task context
                processing_context = {
                    **(context or {}),
                    'task_id': self.request.id,
                    'worker_task': True,
                    'started_at': datetime.utcnow().isoformat()
                }
                
                # Process articles
                result = await processor.process_articles(article_ids, processing_context)
                
                task_logger.info("Article processing completed", 
                               processed=result['processed_articles'],
                               failed=result['failed_articles'],
                               processing_time_ms=result['processing_time_ms'])
                
                return result
                
            except Exception as e:
                task_logger.error("Article processing failed", error=str(e))
                
                # Retry on transient errors
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    raise self.retry(countdown=60, max_retries=3)
                
                raise
                
            finally:
                await db_session.close()
    
    return run_async_task(_process_articles())


@celery_app.task(bind=True, base=DatabaseTask, name='stage6.tasks.batch_process_task')
def batch_process_task(self, 
                      article_ids: List[int], 
                      batch_config: Optional[Dict] = None,
                      context: Optional[Dict] = None):
    """
    Process a large batch of articles with advanced batching logic.
    
    Args:
        article_ids: List of article IDs to process
        batch_config: Batch configuration overrides
        context: Optional processing context
        
    Returns:
        Batch processing result
    """
    task_logger = ComponentLogger("batch_task", task_id=self.request.id)
    task_logger.info("Starting batch processing task", 
                    total_articles=len(article_ids))
    
    async def _batch_process():
        async with traced_operation("celery_batch_process_task", {
            "task_id": self.request.id,
            "total_articles": len(article_ids)
        }):
            db_session = await self.get_db_session()
            
            try:
                # Create batch configuration
                config_dict = batch_config or {}
                batch_configuration = BatchConfiguration(
                    batch_size=config_dict.get('batch_size', 50),
                    max_concurrent_batches=config_dict.get('max_concurrent_batches', 3),
                    retry_failed_articles=config_dict.get('retry_failed_articles', True),
                    max_retries=config_dict.get('max_retries', 2)
                )
                
                # Create processor with batch config
                processor = ChunkProcessor(self.settings, db_session, batch_configuration)
                
                # Add task context
                processing_context = {
                    **(context or {}),
                    'batch_task_id': self.request.id,
                    'total_articles': len(article_ids),
                    'batch_processing': True
                }
                
                # Process batch
                result = await processor.process_articles(article_ids, processing_context)
                
                task_logger.info("Batch processing completed",
                               processed=result['processed_articles'],
                               failed=result['failed_articles'],
                               batches=result.get('batches_processed', 0))
                
                return result
                
            except Exception as e:
                task_logger.error("Batch processing failed", error=str(e))
                raise
                
            finally:
                await db_session.close()
    
    return run_async_task(_batch_process())


@celery_app.task(bind=True, base=DatabaseTask, name='stage6.tasks.health_check_task')
def health_check_task(self, include_llm: bool = True):
    """
    Run comprehensive health checks.
    
    Args:
        include_llm: Whether to include LLM API health checks
        
    Returns:
        Health check results
    """
    task_logger = ComponentLogger("health_task", task_id=self.request.id)
    task_logger.info("Starting health check task")
    
    async def _health_check():
        async with traced_operation("celery_health_check_task", {
            "task_id": self.request.id,
            "include_llm": include_llm
        }):
            db_session = await self.get_db_session()
            
            try:
                # Create components for health check
                gemini_client = None
                if include_llm and self.settings.features.llm_chunk_refine_enabled:
                    from src.llm.gemini_client import GeminiClient
                    gemini_client = GeminiClient(self.settings)
                
                # Create health checker
                health_checker = create_stage6_health_checker(
                    db_session=db_session,
                    gemini_client=gemini_client,
                    timeout_seconds=30.0
                )
                
                # Run health checks
                results = await health_checker.check_all()
                
                # Get summary
                summary = health_checker.get_health_summary()
                
                task_logger.info("Health check completed", 
                               overall_status=summary['overall_status'],
                               total_checks=summary['total_checks'])
                
                # Clean up
                if gemini_client:
                    await gemini_client.close()
                
                return summary
                
            except Exception as e:
                task_logger.error("Health check failed", error=str(e))
                return {
                    'overall_status': 'error',
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }
                
            finally:
                await db_session.close()
    
    return run_async_task(_health_check())


@celery_app.task(bind=True, base=DatabaseTask, name='stage6.tasks.cleanup_task')
def cleanup_task(self, older_than_days: int = 7, dry_run: bool = False):
    """
    Clean up old processing results and temporary data.
    
    Args:
        older_than_days: Clean up data older than this many days
        dry_run: If True, only count what would be cleaned up
        
    Returns:
        Cleanup statistics
    """
    task_logger = ComponentLogger("cleanup_task", task_id=self.request.id)
    task_logger.info("Starting cleanup task", 
                    older_than_days=older_than_days, dry_run=dry_run)
    
    async def _cleanup():
        async with traced_operation("celery_cleanup_task", {
            "task_id": self.request.id,
            "older_than_days": older_than_days,
            "dry_run": dry_run
        }):
            db_session = await self.get_db_session()
            
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
                cleanup_stats = {
                    'cutoff_date': cutoff_date.isoformat(),
                    'dry_run': dry_run,
                    'cleaned_up': {}
                }
                
                # Clean up old chunks (if they have a cleanup timestamp)
                # This is a placeholder - implement based on your cleanup needs
                
                if hasattr(ArticleChunk, 'created_at'):
                    old_chunks_query = select(ArticleChunk).where(
                        ArticleChunk.created_at < cutoff_date
                    )
                    
                    result = await db_session.execute(old_chunks_query)
                    old_chunks = result.scalars().all()
                    
                    cleanup_stats['cleaned_up']['chunks'] = len(old_chunks)
                    
                    if not dry_run and old_chunks:
                        # Delete old chunks
                        await db_session.execute(
                            delete(ArticleChunk).where(
                                ArticleChunk.created_at < cutoff_date
                            )
                        )
                        await db_session.commit()
                        
                        task_logger.info("Cleaned up old chunks", count=len(old_chunks))
                
                # Clean up Celery task results (if using database backend)
                # This would depend on your Celery result backend configuration
                
                task_logger.info("Cleanup completed", stats=cleanup_stats)
                return cleanup_stats
                
            except Exception as e:
                task_logger.error("Cleanup failed", error=str(e))
                await db_session.rollback()
                raise
                
            finally:
                await db_session.close()
    
    return run_async_task(_cleanup())


@celery_app.task(bind=True, base=DatabaseTask, name='stage6.tasks.discover_articles_task')
def discover_articles_task(self, 
                          source_domain: Optional[str] = None,
                          max_articles: int = 1000,
                          days_back: int = 7):
    """
    Discover unprocessed articles and queue them for processing.
    
    Args:
        source_domain: Filter by source domain
        max_articles: Maximum articles to discover
        days_back: Look for articles this many days back
        
    Returns:
        Discovery and queuing results
    """
    task_logger = ComponentLogger("discovery_task", task_id=self.request.id)
    task_logger.info("Starting article discovery task")
    
    async def _discover():
        async with traced_operation("celery_discover_articles_task", {
            "task_id": self.request.id,
            "source_domain": source_domain,
            "max_articles": max_articles
        }):
            db_session = await self.get_db_session()
            
            try:
                # Find unprocessed articles
                cutoff_date = datetime.utcnow() - timedelta(days=days_back)
                
                # Subquery for articles that already have chunks
                processed_articles = select(ArticleChunk.article_id).distinct()
                
                # Main query for unprocessed articles
                query = select(Article).where(
                    Article.id.not_in(processed_articles),
                    Article.created_at >= cutoff_date
                ).limit(max_articles)
                
                if source_domain:
                    query = query.where(Article.source_domain == source_domain)
                
                result = await db_session.execute(query)
                unprocessed_articles = result.scalars().all()
                
                article_ids = [article.id for article in unprocessed_articles]
                
                task_logger.info("Discovered unprocessed articles", count=len(article_ids))
                
                # Queue articles for processing in batches
                batch_size = 50
                queued_jobs = []
                
                for i in range(0, len(article_ids), batch_size):
                    batch_ids = article_ids[i:i + batch_size]
                    
                    # Queue processing task
                    job = process_articles_task.delay(
                        batch_ids,
                        context={
                            'discovered_batch': True,
                            'discovery_task_id': self.request.id,
                            'batch_index': i // batch_size
                        }
                    )
                    
                    queued_jobs.append(job.id)
                
                result = {
                    'discovered_articles': len(article_ids),
                    'queued_jobs': len(queued_jobs),
                    'job_ids': queued_jobs,
                    'source_domain': source_domain,
                    'cutoff_date': cutoff_date.isoformat()
                }
                
                task_logger.info("Article discovery completed", 
                               discovered=len(article_ids),
                               jobs_queued=len(queued_jobs))
                
                return result
                
            except Exception as e:
                task_logger.error("Article discovery failed", error=str(e))
                raise
                
            finally:
                await db_session.close()
    
    return run_async_task(_discover())


@celery_app.task(bind=True, name='stage6.tasks.metrics_collection_task')
def metrics_collection_task(self):
    """
    Collect and report system metrics.
    
    Returns:
        Collected metrics
    """
    task_logger = ComponentLogger("metrics_task", task_id=self.request.id)
    
    try:
        # This is a simple metrics collection task
        # In a real implementation, you might:
        # - Collect metrics from various components
        # - Send metrics to monitoring systems
        # - Generate performance reports
        
        metrics = {
            'task_id': self.request.id,
            'timestamp': datetime.utcnow().isoformat(),
            'worker_id': self.request.hostname,
            'queue': self.request.delivery_info.get('routing_key', 'unknown')
        }
        
        task_logger.info("Metrics collection completed", metrics=metrics)
        return metrics
        
    except Exception as e:
        task_logger.error("Metrics collection failed", error=str(e))
        raise


# Task error handlers

@celery_app.task(bind=True)
def handle_task_failure(self, task_id, error, traceback):
    """Handle task failures with proper logging."""
    logger.error("Task failed", 
                task_id=task_id,
                error=str(error),
                traceback=traceback)


# Register error handler
celery_app.conf.task_annotations = {
    '*': {'on_failure': handle_task_failure}
}