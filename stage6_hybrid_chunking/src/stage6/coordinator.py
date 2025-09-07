"""
Batch coordinator for Stage 6 processing with advanced scheduling and resource management.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import uuid4

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.db.models import Article, ArticleChunk
from src.stage6.processor import ChunkProcessor, BatchConfiguration

logger = structlog.get_logger(__name__)


class JobPriority(Enum):
    """Job priority levels."""
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


class JobStatus(Enum):
    """Job status tracking."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProcessingJob:
    """Represents a processing job."""
    job_id: str
    article_ids: List[int]
    priority: JobPriority = JobPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: JobStatus = JobStatus.PENDING
    context: Dict = field(default_factory=dict)
    result: Optional[Dict] = None
    error_message: Optional[str] = None
    
    @property
    def processing_time_seconds(self) -> Optional[float]:
        """Calculate processing time if job is completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class BatchCoordinator:
    """
    Advanced batch coordinator for Stage 6 processing with:
    - Priority-based job scheduling
    - Resource-aware batch sizing  
    - Automatic article discovery and queuing
    - Real-time progress tracking
    - Advanced error recovery and retry logic
    """
    
    def __init__(self, 
                 settings: Settings,
                 db_session: AsyncSession,
                 batch_config: Optional[BatchConfiguration] = None):
        
        self.settings = settings
        self.db_session = db_session
        self.batch_config = batch_config or BatchConfiguration()
        
        # Initialize processor
        self.processor = ChunkProcessor(settings, db_session, batch_config)
        
        # Job management
        self.job_queue: List[ProcessingJob] = []
        self.active_jobs: Dict[str, ProcessingJob] = {}
        self.completed_jobs: Dict[str, ProcessingJob] = {}
        
        # Resource management
        self.max_concurrent_jobs = min(3, self.batch_config.max_concurrent_batches)
        self.current_resource_usage = 0.0
        
        # Discovery settings
        self.auto_discovery_enabled = False
        self.auto_discovery_interval = 300  # 5 minutes
        self.auto_discovery_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.coordinator_stats = {
            'jobs_created': 0,
            'jobs_completed': 0,
            'jobs_failed': 0,
            'articles_processed': 0,
            'total_processing_time_seconds': 0.0
        }
        
        logger.info("BatchCoordinator initialized", 
                   max_concurrent_jobs=self.max_concurrent_jobs,
                   batch_size=batch_config.batch_size)
    
    async def submit_job(self, 
                        article_ids: List[int],
                        priority: JobPriority = JobPriority.NORMAL,
                        context: Optional[Dict] = None) -> str:
        """
        Submit a processing job to the coordinator.
        
        Args:
            article_ids: List of article IDs to process
            priority: Job priority level
            context: Optional processing context
            
        Returns:
            Job ID for tracking
        """
        job_id = f"job_{uuid4().hex[:12]}"
        context = context or {}
        
        job = ProcessingJob(
            job_id=job_id,
            article_ids=article_ids,
            priority=priority,
            context=context
        )
        
        # Insert job into queue by priority
        self._insert_job_by_priority(job)
        
        self.coordinator_stats['jobs_created'] += 1
        
        logger.info("Job submitted", 
                   job_id=job_id,
                   article_count=len(article_ids),
                   priority=priority.name)
        
        # Start processing if capacity available
        await self._maybe_start_next_job()
        
        return job_id
    
    async def submit_batch_jobs(self, 
                              all_article_ids: List[int],
                              job_size: int = 100,
                              priority: JobPriority = JobPriority.NORMAL) -> List[str]:
        """
        Submit multiple jobs for a large batch of articles.
        
        Args:
            all_article_ids: All article IDs to process
            job_size: Number of articles per job
            priority: Priority for all jobs
            
        Returns:
            List of job IDs
        """
        if not all_article_ids:
            return []
        
        job_ids = []
        
        # Split into multiple jobs
        for i in range(0, len(all_article_ids), job_size):
            batch_ids = all_article_ids[i:i + job_size]
            job_id = await self.submit_job(
                batch_ids, 
                priority=priority,
                context={'batch_job': True, 'batch_index': i // job_size}
            )
            job_ids.append(job_id)
        
        logger.info("Batch jobs submitted", 
                   total_articles=len(all_article_ids),
                   jobs_created=len(job_ids),
                   job_size=job_size)
        
        return job_ids
    
    async def start_auto_discovery(self, 
                                 discovery_query: Optional[Dict] = None) -> None:
        """
        Start automatic discovery and queuing of unprocessed articles.
        
        Args:
            discovery_query: Optional query parameters for article discovery
        """
        if self.auto_discovery_enabled:
            logger.warning("Auto discovery already running")
            return
        
        self.auto_discovery_enabled = True
        discovery_query = discovery_query or {}
        
        async def discovery_loop():
            while self.auto_discovery_enabled:
                try:
                    # Discover unprocessed articles
                    article_ids = await self._discover_unprocessed_articles(discovery_query)
                    
                    if article_ids:
                        logger.info("Auto discovery found articles", count=len(article_ids))
                        
                        # Submit as batch jobs
                        await self.submit_batch_jobs(
                            article_ids,
                            job_size=50,  # Smaller jobs for auto discovery
                            priority=JobPriority.LOW
                        )
                    
                except Exception as e:
                    logger.error("Auto discovery error", error=str(e))
                
                # Wait for next discovery cycle
                await asyncio.sleep(self.auto_discovery_interval)
        
        self.auto_discovery_task = asyncio.create_task(discovery_loop())
        logger.info("Auto discovery started", 
                   interval_seconds=self.auto_discovery_interval)
    
    async def stop_auto_discovery(self) -> None:
        """Stop automatic discovery."""
        self.auto_discovery_enabled = False
        
        if self.auto_discovery_task:
            self.auto_discovery_task.cancel()
            try:
                await self.auto_discovery_task
            except asyncio.CancelledError:
                pass
            self.auto_discovery_task = None
        
        logger.info("Auto discovery stopped")
    
    async def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get status of a specific job."""
        
        # Check active jobs
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            return self._job_to_dict(job)
        
        # Check completed jobs
        if job_id in self.completed_jobs:
            job = self.completed_jobs[job_id]
            return self._job_to_dict(job)
        
        # Check queue
        for job in self.job_queue:
            if job.job_id == job_id:
                return self._job_to_dict(job)
        
        return None
    
    async def get_coordinator_status(self) -> Dict:
        """Get comprehensive coordinator status."""
        processor_status = await self.processor.get_processing_status()
        
        return {
            'coordinator_stats': self.coordinator_stats,
            'job_queue': {
                'pending_jobs': len(self.job_queue),
                'active_jobs': len(self.active_jobs),
                'completed_jobs': len(self.completed_jobs),
                'queue_by_priority': self._get_queue_priority_breakdown()
            },
            'resource_management': {
                'max_concurrent_jobs': self.max_concurrent_jobs,
                'current_resource_usage': self.current_resource_usage,
                'auto_discovery_enabled': self.auto_discovery_enabled
            },
            'processor_status': processor_status
        }
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        
        # Check if job is in queue
        for i, job in enumerate(self.job_queue):
            if job.job_id == job_id:
                job.status = JobStatus.CANCELLED
                self.job_queue.pop(i)
                self.completed_jobs[job_id] = job
                logger.info("Job cancelled from queue", job_id=job_id)
                return True
        
        # Cannot cancel active jobs (would require more complex coordination)
        if job_id in self.active_jobs:
            logger.warning("Cannot cancel active job", job_id=job_id)
            return False
        
        return False
    
    def _insert_job_by_priority(self, job: ProcessingJob) -> None:
        """Insert job into queue maintaining priority order."""
        
        # Find insertion point (higher priority first)
        insertion_index = 0
        for i, existing_job in enumerate(self.job_queue):
            if job.priority.value < existing_job.priority.value:
                insertion_index = i
                break
            insertion_index = i + 1
        
        self.job_queue.insert(insertion_index, job)
    
    async def _maybe_start_next_job(self) -> None:
        """Start next job if resources are available."""
        
        if len(self.active_jobs) >= self.max_concurrent_jobs:
            return
        
        if not self.job_queue:
            return
        
        if self.current_resource_usage > self.batch_config.backpressure_threshold:
            logger.debug("Resource usage too high, delaying job start",
                        usage=self.current_resource_usage)
            return
        
        # Get next job from queue
        job = self.job_queue.pop(0)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        
        self.active_jobs[job.job_id] = job
        
        logger.info("Starting job", 
                   job_id=job.job_id,
                   article_count=len(job.article_ids),
                   priority=job.priority.name)
        
        # Start processing task
        task = asyncio.create_task(self._execute_job(job))
        # Don't await - let it run in background
    
    async def _execute_job(self, job: ProcessingJob) -> None:
        """Execute a processing job."""
        
        try:
            # Process articles
            result = await self.processor.process_articles(
                job.article_ids, 
                job.context
            )
            
            # Job completed successfully
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.result = result
            
            # Update statistics
            self.coordinator_stats['jobs_completed'] += 1
            self.coordinator_stats['articles_processed'] += result.get('processed_articles', 0)
            
            if job.processing_time_seconds:
                self.coordinator_stats['total_processing_time_seconds'] += job.processing_time_seconds
            
            logger.info("Job completed successfully", 
                       job_id=job.job_id,
                       articles_processed=result.get('processed_articles', 0),
                       processing_time_seconds=job.processing_time_seconds)
            
        except Exception as e:
            # Job failed
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.error_message = str(e)
            
            self.coordinator_stats['jobs_failed'] += 1
            
            logger.error("Job failed", 
                        job_id=job.job_id, 
                        error=str(e))
        
        finally:
            # Move job from active to completed
            self.active_jobs.pop(job.job_id, None)
            self.completed_jobs[job.job_id] = job
            
            # Try to start next job
            await self._maybe_start_next_job()
    
    async def _discover_unprocessed_articles(self, query_params: Dict) -> List[int]:
        """Discover articles that haven't been processed by Stage 6."""
        
        # Base query for articles without chunks
        subquery = select(ArticleChunk.article_id).distinct()
        
        query = (
            select(Article.id)
            .where(and_(
                Article.id.not_in(subquery),
                Article.created_at >= datetime.utcnow() - timedelta(days=query_params.get('days_back', 7))
            ))
            .limit(query_params.get('limit', 1000))
        )
        
        # Add additional filters
        if 'source_domain' in query_params:
            query = query.where(Article.source_domain == query_params['source_domain'])
        
        if 'language' in query_params:
            query = query.where(Article.language == query_params['language'])
        
        result = await self.db_session.execute(query)
        article_ids = [row[0] for row in result.fetchall()]
        
        return article_ids
    
    def _job_to_dict(self, job: ProcessingJob) -> Dict:
        """Convert job to dictionary representation."""
        return {
            'job_id': job.job_id,
            'article_count': len(job.article_ids),
            'priority': job.priority.name,
            'status': job.status.value,
            'created_at': job.created_at.isoformat(),
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'processing_time_seconds': job.processing_time_seconds,
            'result': job.result,
            'error_message': job.error_message
        }
    
    def _get_queue_priority_breakdown(self) -> Dict:
        """Get breakdown of queue by priority."""
        breakdown = {priority.name: 0 for priority in JobPriority}
        
        for job in self.job_queue:
            breakdown[job.priority.name] += 1
        
        return breakdown
    
    async def cleanup(self) -> None:
        """Cleanup coordinator resources."""
        await self.stop_auto_discovery()
        await self.processor.cleanup()
        
        logger.info("BatchCoordinator cleaned up")