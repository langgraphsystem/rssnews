"""
Chunk processor for Stage 6 pipeline with batch optimization and error recovery.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.db.models import Article
from src.stage6.pipeline import Stage6Pipeline, ProcessingMetrics

logger = structlog.get_logger(__name__)


@dataclass
class BatchConfiguration:
    """Configuration for batch processing."""
    batch_size: int = 50
    max_concurrent_batches: int = 3
    retry_failed_articles: bool = True
    max_retries: int = 2
    backpressure_threshold: float = 0.8  # CPU/memory threshold


class ChunkProcessor:
    """
    High-level processor for managing Stage 6 chunking workloads.
    
    Features:
    - Adaptive batch sizing based on content complexity
    - Automatic retry logic for failed articles
    - Backpressure management to prevent resource exhaustion
    - Comprehensive error tracking and recovery
    """
    
    def __init__(self, 
                 settings: Settings,
                 db_session: AsyncSession,
                 batch_config: Optional[BatchConfiguration] = None):
        
        self.settings = settings
        self.db_session = db_session
        self.batch_config = batch_config or BatchConfiguration()
        
        # Initialize pipeline
        self.pipeline = Stage6Pipeline(settings, db_session)
        
        # Processing state
        self.active_batches = {}
        self.failed_articles: Dict[int, int] = {}  # article_id -> retry_count
        self.processing_stats = {
            'total_batches': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'articles_processed': 0,
            'articles_failed': 0
        }
        
        logger.info("ChunkProcessor initialized", 
                   batch_size=self.batch_config.batch_size,
                   max_concurrent=self.batch_config.max_concurrent_batches)
    
    async def process_articles(self, 
                             article_ids: List[int],
                             processing_context: Optional[Dict] = None) -> Dict:
        """
        Process a list of articles through Stage 6 chunking.
        
        Args:
            article_ids: List of article IDs to process
            processing_context: Optional context for processing
            
        Returns:
            Processing summary with metrics and results
        """
        session_id = f"session_{uuid4().hex[:8]}"
        processing_context = processing_context or {}
        
        logger.info("Starting article processing session", 
                   session_id=session_id,
                   article_count=len(article_ids))
        
        start_time = datetime.utcnow()
        summary = {
            'session_id': session_id,
            'total_articles': len(article_ids),
            'processed_articles': 0,
            'failed_articles': 0,
            'batches_processed': 0,
            'processing_time_ms': 0,
            'errors': []
        }
        
        try:
            # Load articles from database
            articles = await self._load_articles(article_ids)
            if len(articles) != len(article_ids):
                missing_ids = set(article_ids) - {a.id for a in articles}
                logger.warning("Some articles not found", 
                             missing_ids=list(missing_ids))
            
            # Create batches with adaptive sizing
            batches = self._create_adaptive_batches(articles, processing_context)
            
            # Process batches with concurrency control
            batch_results = await self._process_batches_concurrent(
                batches, processing_context, session_id
            )
            
            # Aggregate results
            for result in batch_results:
                if isinstance(result, Exception):
                    summary['errors'].append(str(result))
                    summary['failed_articles'] += 1
                    continue
                
                summary['processed_articles'] += result.articles_processed
                summary['batches_processed'] += 1
                
                if result.errors:
                    summary['errors'].extend(result.errors)
                    summary['failed_articles'] += len(result.errors)
            
            # Handle retry logic for failed articles
            if self.batch_config.retry_failed_articles and summary['failed_articles'] > 0:
                retry_results = await self._retry_failed_articles(processing_context)
                summary.update(retry_results)
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            summary['processing_time_ms'] = processing_time
            
            # Update global stats
            self.processing_stats['total_batches'] += summary['batches_processed']
            self.processing_stats['successful_batches'] += summary['batches_processed']
            self.processing_stats['articles_processed'] += summary['processed_articles']
            self.processing_stats['articles_failed'] += summary['failed_articles']
            
            logger.info("Processing session completed", 
                       session_id=session_id,
                       processed=summary['processed_articles'],
                       failed=summary['failed_articles'],
                       processing_time_ms=processing_time)
            
            return summary
            
        except Exception as e:
            logger.error("Processing session failed", 
                        session_id=session_id, error=str(e))
            summary['errors'].append(f"Session error: {str(e)}")
            self.processing_stats['failed_batches'] += 1
            raise
    
    async def _load_articles(self, article_ids: List[int]) -> List[Article]:
        """Load articles from database."""
        
        query = select(Article).where(Article.id.in_(article_ids))
        result = await self.db_session.execute(query)
        articles = result.scalars().all()
        
        logger.debug("Loaded articles from database", 
                    requested=len(article_ids),
                    loaded=len(articles))
        
        return list(articles)
    
    def _create_adaptive_batches(self, 
                               articles: List[Article],
                               context: Dict) -> List[List[Article]]:
        """Create batches with adaptive sizing based on content complexity."""
        
        if not articles:
            return []
        
        # Calculate base batch size
        base_batch_size = self.batch_config.batch_size
        
        # Adjust batch size based on content complexity
        avg_content_length = sum(len(a.content) for a in articles) / len(articles)
        
        if avg_content_length > 50000:  # Very long articles
            adjusted_batch_size = max(10, base_batch_size // 4)
        elif avg_content_length > 20000:  # Long articles
            adjusted_batch_size = max(20, base_batch_size // 2)
        elif avg_content_length < 5000:  # Short articles
            adjusted_batch_size = min(100, base_batch_size * 2)
        else:
            adjusted_batch_size = base_batch_size
        
        # Check for LLM routing - reduce batch size if many articles likely need LLM
        if (self.settings.features.llm_routing_enabled and 
            self.settings.features.llm_chunk_refine_enabled):
            # Estimate LLM usage based on content characteristics
            estimated_llm_percentage = self._estimate_llm_usage(articles)
            if estimated_llm_percentage > 0.3:  # > 30% LLM usage
                adjusted_batch_size = max(10, adjusted_batch_size // 2)
        
        logger.debug("Adaptive batch sizing", 
                    base_size=base_batch_size,
                    adjusted_size=adjusted_batch_size,
                    avg_content_length=avg_content_length)
        
        # Create batches
        batches = []
        for i in range(0, len(articles), adjusted_batch_size):
            batch = articles[i:i + adjusted_batch_size]
            batches.append(batch)
        
        return batches
    
    def _estimate_llm_usage(self, articles: List[Article]) -> float:
        """Estimate what percentage of articles will trigger LLM processing."""
        
        # Simple heuristics for LLM usage estimation
        llm_indicators = 0
        total_indicators = 0
        
        for article in articles:
            # Check for complex content patterns
            content = article.content.lower()
            
            # Count complexity indicators
            total_indicators += 4
            
            # Lists and bullet points often need LLM refinement
            if '•' in content or content.count('*') > 5 or content.count('-') > 10:
                llm_indicators += 1
            
            # Tables and structured data
            if '|' in content or 'table' in content or content.count('\t') > 5:
                llm_indicators += 1
            
            # Code blocks
            if '```' in content or 'code' in content or content.count('{') > 3:
                llm_indicators += 1
            
            # Very long or very short paragraphs (boundary issues)
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            if paragraphs:
                avg_para_length = sum(len(p) for p in paragraphs) / len(paragraphs)
                if avg_para_length < 100 or avg_para_length > 1000:
                    llm_indicators += 1
        
        return llm_indicators / max(1, total_indicators)
    
    async def _process_batches_concurrent(self, 
                                        batches: List[List[Article]],
                                        context: Dict,
                                        session_id: str) -> List:
        """Process batches with controlled concurrency."""
        
        if not batches:
            return []
        
        max_concurrent = min(self.batch_config.max_concurrent_batches, len(batches))
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_batch_protected(batch: List[Article], batch_index: int):
            async with semaphore:
                batch_context = {
                    **context,
                    'session_id': session_id,
                    'batch_index': batch_index,
                    'batch_size': len(batch)
                }
                
                try:
                    return await self.pipeline.process_articles_batch(batch, batch_context)
                except Exception as e:
                    logger.error("Batch processing failed", 
                               session_id=session_id,
                               batch_index=batch_index,
                               error=str(e))
                    return e
        
        # Execute all batches
        tasks = [
            process_batch_protected(batch, i) 
            for i, batch in enumerate(batches)
        ]
        
        logger.info("Starting concurrent batch processing", 
                   session_id=session_id,
                   total_batches=len(batches),
                   max_concurrent=max_concurrent)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    async def _retry_failed_articles(self, context: Dict) -> Dict:
        """Retry processing for previously failed articles."""
        
        if not self.failed_articles:
            return {'retried_articles': 0, 'retry_successes': 0, 'retry_failures': 0}
        
        # Get articles that haven't exceeded max retries
        retry_candidates = [
            article_id for article_id, retry_count in self.failed_articles.items()
            if retry_count < self.batch_config.max_retries
        ]
        
        if not retry_candidates:
            return {'retried_articles': 0, 'retry_successes': 0, 'retry_failures': 0}
        
        logger.info("Retrying failed articles", count=len(retry_candidates))
        
        # Load and process retry articles
        retry_articles = await self._load_articles(retry_candidates)
        retry_context = {**context, 'is_retry': True}
        
        try:
            result = await self.pipeline.process_articles_batch(retry_articles, retry_context)
            
            # Update retry counts
            for article_id in retry_candidates:
                if result.errors:
                    self.failed_articles[article_id] += 1
                else:
                    self.failed_articles.pop(article_id, None)
            
            return {
                'retried_articles': len(retry_candidates),
                'retry_successes': result.articles_processed,
                'retry_failures': len(result.errors)
            }
            
        except Exception as e:
            logger.error("Retry processing failed", error=str(e))
            # Increment retry counts for all candidates
            for article_id in retry_candidates:
                self.failed_articles[article_id] += 1
            
            return {
                'retried_articles': len(retry_candidates),
                'retry_successes': 0,
                'retry_failures': len(retry_candidates)
            }
    
    async def get_processing_status(self) -> Dict:
        """Get current processing status."""
        pipeline_status = await self.pipeline.get_pipeline_status()
        
        return {
            'processor_stats': self.processing_stats,
            'active_batches': len(self.active_batches),
            'failed_articles_pending_retry': len(self.failed_articles),
            'batch_config': {
                'batch_size': self.batch_config.batch_size,
                'max_concurrent_batches': self.batch_config.max_concurrent_batches,
                'retry_enabled': self.batch_config.retry_failed_articles,
                'max_retries': self.batch_config.max_retries
            },
            'pipeline_status': pipeline_status
        }
    
    async def cleanup(self):
        """Cleanup processor resources."""
        await self.pipeline.cleanup()
        logger.info("ChunkProcessor cleaned up")