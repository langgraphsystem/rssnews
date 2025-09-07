"""
Stage 6 Pipeline: Hybrid chunking orchestrator that coordinates deterministic 
base chunking with selective LLM refinement for production workloads.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.chunking.base_chunker import BaseChunker, RawChunk
from src.chunking.quality_router import QualityRouter, RoutingDecision
from src.config.settings import Settings
from src.db.models import Article, ArticleChunk
from src.llm.gemini_client import GeminiClient, LLMRefinementResult
from src.utils.metrics import MetricsCollector

logger = structlog.get_logger(__name__)


@dataclass
class ProcessingMetrics:
    """Metrics for batch processing."""
    batch_id: str
    articles_processed: int = 0
    chunks_created: int = 0
    llm_requests: int = 0
    llm_success: int = 0
    processing_time_ms: float = 0
    errors: List[str] = field(default_factory=list)
    
    def add_error(self, error: str):
        """Add error to metrics."""
        self.errors.append(error)


@dataclass 
class ChunkRefinementPlan:
    """Plan for refining chunks with LLM."""
    chunk_id: str
    raw_chunk: RawChunk
    routing_decision: RoutingDecision
    context: Dict
    priority: float = 0.5


class Stage6Pipeline:
    """
    Hybrid chunking pipeline that combines deterministic base chunking 
    with selective LLM refinement.
    
    Architecture:
    1. Base Chunker: Fast deterministic chunking (paragraph-aware + sliding window)
    2. Quality Router: Intelligent routing decisions (which chunks need LLM?)
    3. LLM Client: Selective refinement with circuit breaker protection
    4. Database: Persistent storage with optimization metadata
    
    Key Features:
    - Batch processing with backpressure management
    - Circuit breaker protection for LLM calls
    - Comprehensive error handling and fallback strategies
    - Real-time metrics and observability
    - Cost optimization through selective LLM usage
    """
    
    def __init__(self, 
                 settings: Settings,
                 db_session: AsyncSession,
                 metrics_collector: Optional[MetricsCollector] = None):
        
        self.settings = settings
        self.db_session = db_session
        self.metrics = metrics_collector
        
        # Core components
        self.base_chunker = BaseChunker(settings)
        self.quality_router = QualityRouter(settings)
        self.gemini_client = GeminiClient(settings) if settings.features.llm_chunk_refine_enabled else None
        
        # Processing state
        self.active_batches: Set[str] = set()
        self.total_articles_processed = 0
        self.total_chunks_created = 0
        
        logger.info("Stage6Pipeline initialized", 
                   llm_enabled=bool(self.gemini_client),
                   target_words=settings.chunking.target_words)
    
    async def process_articles_batch(self, 
                                   articles: List[Article], 
                                   batch_context: Optional[Dict] = None) -> ProcessingMetrics:
        """
        Process a batch of articles through the hybrid chunking pipeline.
        
        Args:
            articles: List of articles to process
            batch_context: Optional batch processing context
            
        Returns:
            ProcessingMetrics with detailed results
        """
        batch_id = f"batch_{uuid4().hex[:8]}"
        batch_context = batch_context or {}
        
        logger.info("Starting batch processing", 
                   batch_id=batch_id, 
                   article_count=len(articles))
        
        metrics = ProcessingMetrics(batch_id=batch_id)
        start_time = datetime.utcnow()
        
        try:
            self.active_batches.add(batch_id)
            
            # Process each article
            for article in articles:
                try:
                    chunks_created = await self._process_single_article(
                        article, batch_context, batch_id
                    )
                    
                    metrics.articles_processed += 1
                    metrics.chunks_created += chunks_created
                    
                    # Update global counters
                    self.total_articles_processed += 1
                    self.total_chunks_created += chunks_created
                    
                except Exception as e:
                    error_msg = f"Article {article.id} failed: {str(e)}"
                    logger.error("Article processing failed", 
                               article_id=article.id, error=str(e))
                    metrics.add_error(error_msg)
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            metrics.processing_time_ms = processing_time
            
            # Commit database changes
            await self.db_session.commit()
            
            logger.info("Batch processing completed", 
                       batch_id=batch_id,
                       articles_processed=metrics.articles_processed,
                       chunks_created=metrics.chunks_created,
                       llm_requests=metrics.llm_requests,
                       processing_time_ms=processing_time)
            
            # Record metrics
            if self.metrics:
                await self._record_batch_metrics(metrics)
            
            return metrics
            
        except Exception as e:
            await self.db_session.rollback()
            error_msg = f"Batch processing failed: {str(e)}"
            logger.error("Batch processing error", batch_id=batch_id, error=str(e))
            metrics.add_error(error_msg)
            raise
        
        finally:
            self.active_batches.discard(batch_id)
    
    async def _process_single_article(self, 
                                    article: Article, 
                                    batch_context: Dict,
                                    batch_id: str) -> int:
        """Process a single article through the pipeline."""
        
        logger.debug("Processing article", article_id=article.id, title=article.title[:50])
        
        # Step 1: Base chunking (deterministic)
        article_metadata = {
            'title': article.title,
            'source_domain': article.source_domain,
            'language': article.language,
            'published_at': article.published_at.isoformat() if article.published_at else None,
            'content_length': len(article.content),
            'total_chunks': 0  # Will be updated
        }
        
        raw_chunks = self.base_chunker.chunk_text(article.content, article_metadata)
        article_metadata['total_chunks'] = len(raw_chunks)
        
        if not raw_chunks:
            logger.warning("No chunks created for article", article_id=article.id)
            return 0
        
        logger.debug("Base chunking completed", 
                    article_id=article.id, 
                    chunks_created=len(raw_chunks))
        
        # Step 2: Quality routing (decide which chunks need LLM)
        routing_decisions = []
        if self.settings.features.llm_routing_enabled and self.gemini_client:
            try:
                routing_decisions = self.quality_router.route_chunks(
                    raw_chunks, article_metadata, batch_context
                )
                logger.debug("Quality routing completed", 
                           article_id=article.id,
                           llm_candidates=len([r for r in routing_decisions if r[1].needs_llm]))
            except Exception as e:
                logger.error("Quality routing failed, skipping LLM", 
                           article_id=article.id, error=str(e))
                # Fallback: no LLM processing
                routing_decisions = [(chunk, RoutingDecision(needs_llm=False)) for chunk in raw_chunks]
        else:
            # No LLM processing
            routing_decisions = [(chunk, RoutingDecision(needs_llm=False)) for chunk in raw_chunks]
        
        # Step 3: Prepare refinement plans for LLM processing
        refinement_plans = []
        for raw_chunk, decision in routing_decisions:
            if decision.needs_llm and self.gemini_client:
                context = self._build_chunk_context(raw_chunk, raw_chunks, article_metadata)
                plan = ChunkRefinementPlan(
                    chunk_id=f"{article.id}_{raw_chunk.index}",
                    raw_chunk=raw_chunk,
                    routing_decision=decision,
                    context=context,
                    priority=decision.priority
                )
                refinement_plans.append(plan)
        
        # Step 4: Execute LLM refinement (if any)
        refined_chunks = await self._execute_refinement_plans(
            refinement_plans, article_metadata
        )
        
        # Step 5: Create final chunks (merge refined + unrefined)
        final_chunks = self._merge_refined_chunks(
            raw_chunks, routing_decisions, refined_chunks
        )
        
        # Step 6: Save to database
        await self._save_chunks_to_database(article, final_chunks, routing_decisions)
        
        return len(final_chunks)
    
    def _build_chunk_context(self, 
                           target_chunk: RawChunk,
                           all_chunks: List[RawChunk],
                           article_metadata: Dict) -> Dict:
        """Build context for chunk refinement."""
        
        # Find previous and next chunks
        prev_chunk = None
        next_chunk = None
        
        for i, chunk in enumerate(all_chunks):
            if chunk.index == target_chunk.index:
                if i > 0:
                    prev_chunk = all_chunks[i - 1]
                if i < len(all_chunks) - 1:
                    next_chunk = all_chunks[i + 1]
                break
        
        context = {
            'prev_context': prev_chunk.text[-120:] if prev_chunk else '',
            'next_context': next_chunk.text[:120] if next_chunk else '',
            'article_metadata': article_metadata,
            'chunk_position': f"{target_chunk.index + 1}/{len(all_chunks)}"
        }
        
        return context
    
    async def _execute_refinement_plans(self, 
                                      plans: List[ChunkRefinementPlan],
                                      article_metadata: Dict) -> Dict[str, LLMRefinementResult]:
        """Execute LLM refinement plans with rate limiting and error handling."""
        
        if not plans or not self.gemini_client:
            return {}
        
        logger.debug("Executing LLM refinement", plan_count=len(plans))
        
        # Sort plans by priority (highest first)
        plans.sort(key=lambda p: p.priority, reverse=True)
        
        # Execute with concurrency control
        max_concurrent = min(self.settings.rate_limit.max_llm_calls_per_batch, len(plans))
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def refine_chunk(plan: ChunkRefinementPlan) -> Tuple[str, Optional[LLMRefinementResult]]:
            async with semaphore:
                try:
                    result = await self.gemini_client.refine_chunk(
                        chunk_text=plan.raw_chunk.text,
                        chunk_metadata={
                            'index': plan.raw_chunk.index,
                            'word_count': plan.raw_chunk.word_count,
                            'char_start': plan.raw_chunk.char_start,
                            'char_end': plan.raw_chunk.char_end,
                            'quality_issues': plan.routing_decision.reasons
                        },
                        article_metadata=article_metadata,
                        context=plan.context
                    )
                    return plan.chunk_id, result
                    
                except Exception as e:
                    logger.error("LLM refinement failed", 
                               chunk_id=plan.chunk_id, error=str(e))
                    return plan.chunk_id, None
        
        # Execute all refinements concurrently
        tasks = [refine_chunk(plan) for plan in plans]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        refined_chunks = {}
        success_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                logger.error("Refinement task exception", error=str(result))
                continue
            
            chunk_id, refinement_result = result
            if refinement_result:
                refined_chunks[chunk_id] = refinement_result
                success_count += 1
        
        logger.debug("LLM refinement completed", 
                    plans=len(plans),
                    successful=success_count,
                    failed=len(plans) - success_count)
        
        return refined_chunks
    
    def _merge_refined_chunks(self, 
                            raw_chunks: List[RawChunk],
                            routing_decisions: List[Tuple[RawChunk, RoutingDecision]],
                            refined_results: Dict[str, LLMRefinementResult]) -> List[RawChunk]:
        """Merge refined chunks with original chunks."""
        
        # For now, we apply simple refinement logic
        # In a full implementation, this would handle merging, splitting, etc.
        
        final_chunks = []
        routing_dict = {chunk.index: decision for chunk, decision in routing_decisions}
        
        for chunk in raw_chunks:
            chunk_id = f"__{chunk.index}"  # Simplified ID matching
            
            # Check if chunk was refined
            refined = None
            for result_id, result in refined_results.items():
                if chunk_id in result_id:
                    refined = result
                    break
            
            if refined and refined.action == "drop":
                # Skip dropped chunks
                logger.debug("Dropping chunk", chunk_index=chunk.index, reason=refined.reason)
                continue
            elif refined and refined.action == "merge_prev" and final_chunks:
                # Merge with previous chunk
                prev_chunk = final_chunks[-1]
                merged_text = prev_chunk.text + " " + chunk.text
                merged_chunk = RawChunk(
                    index=prev_chunk.index,
                    text=merged_text,
                    char_start=prev_chunk.char_start,
                    char_end=chunk.char_end,
                    word_count=len(merged_text.split()),
                    metadata=prev_chunk.metadata
                )
                final_chunks[-1] = merged_chunk
                logger.debug("Merged chunk with previous", chunk_index=chunk.index)
            else:
                # Keep chunk (possibly with offset adjustments)
                final_chunk = chunk
                if refined and refined.offset_adjust != 0:
                    # Apply offset adjustments (simplified)
                    adjusted_end = min(len(chunk.text), 
                                     max(0, len(chunk.text) + refined.offset_adjust))
                    final_chunk = RawChunk(
                        index=chunk.index,
                        text=chunk.text[:adjusted_end],
                        char_start=chunk.char_start,
                        char_end=chunk.char_start + adjusted_end,
                        word_count=len(chunk.text[:adjusted_end].split()),
                        metadata=chunk.metadata
                    )
                    logger.debug("Applied offset adjustment", 
                               chunk_index=chunk.index, 
                               adjustment=refined.offset_adjust)
                
                final_chunks.append(final_chunk)
        
        # Re-index chunks
        for i, chunk in enumerate(final_chunks):
            chunk.index = i
        
        return final_chunks
    
    async def _save_chunks_to_database(self, 
                                     article: Article,
                                     chunks: List[RawChunk],
                                     routing_decisions: List[Tuple[RawChunk, RoutingDecision]]) -> None:
        """Save processed chunks to database."""
        
        routing_dict = {chunk.index: decision for chunk, decision in routing_decisions}
        
        for i, chunk in enumerate(chunks):
            decision = routing_dict.get(i, RoutingDecision())
            
            # Create database record
            db_chunk = ArticleChunk(
                id=f"{article.id}_{i}",
                article_id=article.id,
                chunk_index=i,
                text=chunk.text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                word_count=chunk.word_count,
                
                # LLM processing metadata
                llm_used=decision.needs_llm,
                llm_action=getattr(chunk, 'refined_action', None),
                llm_confidence=getattr(chunk, 'confidence', None),
                
                # Processing metadata
                created_at=datetime.utcnow(),
                processing_version="stage6_v1.0"
            )
            
            self.db_session.add(db_chunk)
        
        logger.debug("Saved chunks to database", 
                    article_id=article.id, 
                    chunk_count=len(chunks))
    
    async def _record_batch_metrics(self, metrics: ProcessingMetrics) -> None:
        """Record batch processing metrics."""
        if not self.metrics:
            return
        
        # Record metrics
        self.metrics.counter("stage6_articles_processed").inc(metrics.articles_processed)
        self.metrics.counter("stage6_chunks_created").inc(metrics.chunks_created)
        self.metrics.counter("stage6_llm_requests").inc(metrics.llm_requests)
        self.metrics.counter("stage6_llm_success").inc(metrics.llm_success)
        
        self.metrics.histogram("stage6_batch_processing_time_ms").observe(metrics.processing_time_ms)
        self.metrics.histogram("stage6_chunks_per_article").observe(
            metrics.chunks_created / max(1, metrics.articles_processed)
        )
        
        if metrics.errors:
            self.metrics.counter("stage6_batch_errors").inc(len(metrics.errors))
    
    async def get_pipeline_status(self) -> Dict:
        """Get current pipeline status."""
        status = {
            "active_batches": len(self.active_batches),
            "total_articles_processed": self.total_articles_processed,
            "total_chunks_created": self.total_chunks_created,
            "llm_enabled": bool(self.gemini_client),
            "components": {
                "base_chunker": "healthy",
                "quality_router": "healthy",
                "gemini_client": "healthy" if self.gemini_client else "disabled"
            }
        }
        
        # Check Gemini client health
        if self.gemini_client:
            try:
                health = await self.gemini_client.health_check()
                status["components"]["gemini_client"] = "healthy" if health else "unhealthy"
                status["gemini_stats"] = self.gemini_client.get_stats()
            except Exception as e:
                status["components"]["gemini_client"] = f"error: {str(e)}"
        
        return status
    
    async def cleanup(self):
        """Cleanup pipeline resources."""
        if self.gemini_client:
            await self.gemini_client.close()
        
        logger.info("Stage6Pipeline cleaned up")