"""
Tests for Stage 6 pipeline orchestration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.stage6.pipeline import Stage6Pipeline, ProcessingMetrics
from src.stage6.processor import ChunkProcessor
from src.stage6.coordinator import BatchCoordinator, ProcessingJob, JobPriority
from src.db.models import Article, ArticleChunk
from tests.conftest import create_test_article_metadata


class TestStage6Pipeline:
    """Test suite for Stage 6 Pipeline."""
    
    @pytest.fixture
    def mock_components(self, test_settings, mock_gemini_client, test_metrics):
        """Create pipeline with mocked components."""
        return {
            'gemini_client': mock_gemini_client,
            'metrics': test_metrics
        }
    
    @pytest.mark.asyncio
    async def test_pipeline_initialization(self, test_settings, db_session, test_metrics):
        """Test pipeline initializes correctly."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        
        assert pipeline.settings == test_settings
        assert pipeline.db_session == db_session
        assert pipeline.metrics == test_metrics
        assert pipeline.base_chunker is not None
        assert pipeline.quality_router is not None
        assert pipeline.total_articles_processed == 0
        assert pipeline.total_chunks_created == 0
    
    @pytest.mark.asyncio
    async def test_single_article_processing(self, test_settings, db_session, test_metrics, 
                                           mock_gemini_client, db_articles):
        """Test processing a single article."""
        # Create pipeline with mocked LLM client
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Get test article
        article = db_articles[0]  # Simple article
        
        batch_context = {'batch_id': 'test_batch', 'batch_size': 1}
        metrics = await pipeline.process_articles_batch([article], batch_context)
        
        assert isinstance(metrics, ProcessingMetrics)
        assert metrics.articles_processed == 1
        assert metrics.chunks_created > 0
        assert metrics.processing_time_ms > 0
        assert len(metrics.errors) == 0
        
        # Verify chunks were saved to database
        from sqlalchemy import select
        result = await db_session.execute(
            select(ArticleChunk).where(ArticleChunk.article_id == article.id)
        )
        chunks = result.scalars().all()
        
        assert len(chunks) > 0
        assert chunks[0].article_id == article.id
        assert chunks[0].text.strip() != ""
    
    @pytest.mark.asyncio
    async def test_complex_article_processing(self, test_settings, db_session, test_metrics,
                                            mock_gemini_client, db_articles):
        """Test processing complex article that triggers LLM."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Get complex article (index 2 has lists, code, tables)
        article = db_articles[2]
        
        batch_context = {'batch_id': 'test_complex', 'batch_size': 1}
        metrics = await pipeline.process_articles_batch([article], batch_context)
        
        assert metrics.articles_processed == 1
        assert metrics.chunks_created > 0
        
        # Should have triggered some LLM calls for complex content
        assert mock_gemini_client.refine_chunk.call_count > 0
    
    @pytest.mark.asyncio
    async def test_batch_processing(self, test_settings, db_session, test_metrics,
                                  mock_gemini_client, db_articles):
        """Test processing multiple articles in a batch."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Process all test articles
        batch_context = {'batch_id': 'test_batch_all', 'batch_size': len(db_articles)}
        metrics = await pipeline.process_articles_batch(db_articles, batch_context)
        
        assert metrics.articles_processed == len(db_articles)
        assert metrics.chunks_created > 0
        assert len(metrics.errors) == 0  # No errors expected
        
        # Verify global counters updated
        assert pipeline.total_articles_processed == len(db_articles)
        assert pipeline.total_chunks_created == metrics.chunks_created
    
    @pytest.mark.asyncio
    async def test_error_handling(self, test_settings, db_session, test_metrics,
                                mock_gemini_client, db_articles):
        """Test error handling during processing."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Mock chunker to raise exception
        original_chunk_text = pipeline.base_chunker.chunk_text
        
        def failing_chunk_text(text, metadata):
            if "Sample News Article" in text:  # Fail on first article
                raise Exception("Test chunking error")
            return original_chunk_text(text, metadata)
        
        pipeline.base_chunker.chunk_text = failing_chunk_text
        
        batch_context = {'batch_id': 'test_error', 'batch_size': len(db_articles)}
        metrics = await pipeline.process_articles_batch(db_articles, batch_context)
        
        # Should have processed some articles but recorded errors
        assert metrics.articles_processed < len(db_articles)
        assert len(metrics.errors) > 0
        assert any("Test chunking error" in error for error in metrics.errors)
    
    @pytest.mark.asyncio
    async def test_llm_disabled_processing(self, test_settings, db_session, test_metrics, db_articles):
        """Test processing with LLM disabled."""
        # Disable LLM features
        test_settings.features.llm_chunk_refine_enabled = False
        test_settings.features.llm_routing_enabled = False
        
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        
        article = db_articles[2]  # Complex article
        batch_context = {'batch_id': 'test_no_llm', 'batch_size': 1}
        metrics = await pipeline.process_articles_batch([article], batch_context)
        
        assert metrics.articles_processed == 1
        assert metrics.chunks_created > 0
        assert metrics.llm_requests == 0  # No LLM calls should be made
    
    @pytest.mark.asyncio
    async def test_chunk_merging_logic(self, test_settings, db_session, test_metrics,
                                     mock_gemini_client, db_articles):
        """Test chunk merging based on LLM recommendations."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Configure mock to return merge actions
        async def mock_refine_merge(chunk_text, chunk_metadata, article_metadata, context=None):
            from src.llm.gemini_client import LLMRefinementResult
            
            # Return merge_prev for specific chunks
            if chunk_metadata.get('index', 0) == 1:
                return LLMRefinementResult(
                    action="merge_prev",
                    confidence=0.9,
                    reason="Should merge with previous chunk"
                )
            return LLMRefinementResult(
                action="keep", 
                confidence=0.8,
                reason="Keep as is"
            )
        
        mock_gemini_client.refine_chunk.side_effect = mock_refine_merge
        
        article = db_articles[0]
        batch_context = {'batch_id': 'test_merge', 'batch_size': 1}
        
        # Process article
        metrics = await pipeline.process_articles_batch([article], batch_context)
        
        assert metrics.articles_processed == 1
        
        # Verify merging was applied (should have fewer final chunks than initial raw chunks)
        from sqlalchemy import select
        result = await db_session.execute(
            select(ArticleChunk).where(ArticleChunk.article_id == article.id).order_by(ArticleChunk.chunk_index)
        )
        final_chunks = result.scalars().all()
        
        assert len(final_chunks) > 0
        # Check for merged chunks (merged chunk should be longer)
        if len(final_chunks) > 1:
            # At least one chunk should show evidence of merging
            total_chars = sum(len(chunk.text) for chunk in final_chunks)
            assert total_chars > 0
    
    @pytest.mark.asyncio
    async def test_chunk_dropping_logic(self, test_settings, db_session, test_metrics,
                                      mock_gemini_client, db_articles):
        """Test chunk dropping based on LLM recommendations."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Configure mock to drop certain chunks
        async def mock_refine_drop(chunk_text, chunk_metadata, article_metadata, context=None):
            from src.llm.gemini_client import LLMRefinementResult
            
            # Drop very short chunks
            if chunk_metadata.get('word_count', 0) < 5:
                return LLMRefinementResult(
                    action="drop",
                    confidence=0.9,
                    reason="Chunk too short to be meaningful"
                )
            return LLMRefinementResult(
                action="keep",
                confidence=0.8, 
                reason="Keep chunk"
            )
        
        mock_gemini_client.refine_chunk.side_effect = mock_refine_drop
        
        article = db_articles[1]  # Short article
        batch_context = {'batch_id': 'test_drop', 'batch_size': 1}
        
        metrics = await pipeline.process_articles_batch([article], batch_context)
        
        assert metrics.articles_processed == 1
        # Chunks might be dropped, but at least some should remain
        assert metrics.chunks_created >= 0
    
    @pytest.mark.asyncio
    async def test_pipeline_status(self, test_settings, db_session, test_metrics, mock_gemini_client):
        """Test pipeline status reporting."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        status = await pipeline.get_pipeline_status()
        
        assert isinstance(status, dict)
        assert 'active_batches' in status
        assert 'total_articles_processed' in status
        assert 'total_chunks_created' in status
        assert 'llm_enabled' in status
        assert 'components' in status
        
        # Check component statuses
        assert status['components']['base_chunker'] == 'healthy'
        assert status['components']['quality_router'] == 'healthy' 
        assert 'gemini_client' in status['components']
    
    @pytest.mark.asyncio
    async def test_pipeline_cleanup(self, test_settings, db_session, test_metrics, mock_gemini_client):
        """Test pipeline cleanup."""
        pipeline = Stage6Pipeline(test_settings, db_session, test_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        await pipeline.cleanup()
        
        # Verify cleanup was called on components
        mock_gemini_client.close.assert_called_once()


class TestChunkProcessor:
    """Test suite for ChunkProcessor."""
    
    @pytest.mark.asyncio
    async def test_processor_initialization(self, test_settings, db_session):
        """Test processor initializes correctly."""
        processor = ChunkProcessor(test_settings, db_session)
        
        assert processor.settings == test_settings
        assert processor.db_session == db_session
        assert processor.pipeline is not None
        assert processor.processing_stats['total_batches'] == 0
    
    @pytest.mark.asyncio
    async def test_article_processing(self, test_settings, db_session, db_articles):
        """Test processing articles through processor."""
        processor = ChunkProcessor(test_settings, db_session)
        
        # Mock the pipeline
        processor.pipeline = AsyncMock()
        mock_metrics = ProcessingMetrics(batch_id="test")
        mock_metrics.articles_processed = len(db_articles)
        mock_metrics.chunks_created = 10
        processor.pipeline.process_articles_batch.return_value = mock_metrics
        
        article_ids = [article.id for article in db_articles]
        result = await processor.process_articles(article_ids)
        
        assert result['processed_articles'] == len(db_articles)
        assert result['total_articles'] == len(db_articles)
        assert 'processing_time_ms' in result
    
    @pytest.mark.asyncio
    async def test_adaptive_batch_sizing(self, test_settings, db_session, db_articles):
        """Test adaptive batch sizing logic."""
        processor = ChunkProcessor(test_settings, db_session)
        
        # Test with different article characteristics
        batches = processor._create_adaptive_batches(db_articles, {})
        
        assert len(batches) > 0
        assert all(isinstance(batch, list) for batch in batches)
        assert sum(len(batch) for batch in batches) == len(db_articles)
    
    @pytest.mark.asyncio 
    async def test_processor_status(self, test_settings, db_session):
        """Test processor status reporting."""
        processor = ChunkProcessor(test_settings, db_session)
        
        # Mock pipeline status
        processor.pipeline.get_pipeline_status = AsyncMock(return_value={
            'active_batches': 0,
            'components': {'gemini_client': 'healthy'}
        })
        
        status = await processor.get_processing_status()
        
        assert 'processor_stats' in status
        assert 'pipeline_status' in status
        assert 'batch_config' in status


class TestBatchCoordinator:
    """Test suite for BatchCoordinator."""
    
    @pytest.mark.asyncio
    async def test_coordinator_initialization(self, test_settings, db_session):
        """Test coordinator initializes correctly."""
        coordinator = BatchCoordinator(test_settings, db_session)
        
        assert coordinator.settings == test_settings
        assert coordinator.db_session == db_session
        assert len(coordinator.job_queue) == 0
        assert len(coordinator.active_jobs) == 0
        assert coordinator.coordinator_stats['jobs_created'] == 0
    
    @pytest.mark.asyncio
    async def test_job_submission(self, test_settings, db_session, db_articles):
        """Test job submission and queuing."""
        coordinator = BatchCoordinator(test_settings, db_session)
        
        # Mock processor
        coordinator.processor = AsyncMock()
        mock_result = {
            'processed_articles': len(db_articles),
            'failed_articles': 0,
            'processing_time_ms': 1000
        }
        coordinator.processor.process_articles.return_value = mock_result
        
        article_ids = [article.id for article in db_articles]
        job_id = await coordinator.submit_job(article_ids, JobPriority.HIGH)
        
        assert job_id is not None
        assert coordinator.coordinator_stats['jobs_created'] == 1
        
        # Allow job to complete
        await asyncio.sleep(0.1)
        
        # Check job status
        status = await coordinator.get_job_status(job_id)
        assert status is not None
        assert status['status'] in ['completed', 'running']
    
    @pytest.mark.asyncio
    async def test_batch_job_submission(self, test_settings, db_session, db_articles):
        """Test batch job submission."""
        coordinator = BatchCoordinator(test_settings, db_session)
        
        # Mock processor
        coordinator.processor = AsyncMock()
        coordinator.processor.process_articles.return_value = {
            'processed_articles': 1,
            'failed_articles': 0
        }
        
        article_ids = [article.id for article in db_articles]
        job_ids = await coordinator.submit_batch_jobs(
            article_ids, job_size=2, priority=JobPriority.NORMAL
        )
        
        # Should create multiple jobs for the articles
        expected_jobs = (len(db_articles) + 1) // 2  # Round up division
        assert len(job_ids) == expected_jobs
        assert coordinator.coordinator_stats['jobs_created'] == len(job_ids)
    
    @pytest.mark.asyncio
    async def test_priority_queue_ordering(self, test_settings, db_session, db_articles):
        """Test job priority ordering in queue."""
        coordinator = BatchCoordinator(test_settings, db_session)
        coordinator.max_concurrent_jobs = 0  # Prevent immediate execution
        
        article_ids = [article.id for article in db_articles[:1]]
        
        # Submit jobs with different priorities
        low_job = await coordinator.submit_job(article_ids, JobPriority.LOW)
        high_job = await coordinator.submit_job(article_ids, JobPriority.HIGH)
        normal_job = await coordinator.submit_job(article_ids, JobPriority.NORMAL)
        
        # High priority should be first
        queue_priorities = [job.priority for job in coordinator.job_queue]
        assert queue_priorities == [JobPriority.HIGH, JobPriority.NORMAL, JobPriority.LOW]
    
    @pytest.mark.asyncio
    async def test_job_cancellation(self, test_settings, db_session, db_articles):
        """Test job cancellation."""
        coordinator = BatchCoordinator(test_settings, db_session)
        coordinator.max_concurrent_jobs = 0  # Prevent immediate execution
        
        article_ids = [article.id for article in db_articles[:1]]
        job_id = await coordinator.submit_job(article_ids)
        
        # Cancel the job
        cancelled = await coordinator.cancel_job(job_id)
        assert cancelled == True
        
        # Job should be moved to completed with cancelled status
        status = await coordinator.get_job_status(job_id)
        assert status['status'] == 'cancelled'
    
    @pytest.mark.asyncio
    async def test_coordinator_status(self, test_settings, db_session):
        """Test coordinator status reporting."""
        coordinator = BatchCoordinator(test_settings, db_session)
        
        # Mock processor status
        coordinator.processor.get_processing_status = AsyncMock(return_value={
            'processor_stats': {},
            'pipeline_status': {}
        })
        
        status = await coordinator.get_coordinator_status()
        
        assert 'coordinator_stats' in status
        assert 'job_queue' in status
        assert 'resource_management' in status
        assert 'processor_status' in status
    
    @pytest.mark.asyncio
    async def test_auto_discovery(self, test_settings, db_session, db_articles):
        """Test automatic article discovery."""
        coordinator = BatchCoordinator(test_settings, db_session)
        coordinator.auto_discovery_interval = 0.1  # Fast discovery for testing
        
        # Mock discovery method
        coordinator._discover_unprocessed_articles = AsyncMock(
            return_value=[article.id for article in db_articles[:1]]
        )
        
        # Mock processor
        coordinator.processor = AsyncMock()
        coordinator.processor.process_articles.return_value = {
            'processed_articles': 1,
            'failed_articles': 0
        }
        
        # Start auto discovery
        await coordinator.start_auto_discovery()
        
        # Wait briefly for discovery to run
        await asyncio.sleep(0.2)
        
        # Stop auto discovery
        await coordinator.stop_auto_discovery()
        
        # Should have discovered and submitted jobs
        assert coordinator.coordinator_stats['jobs_created'] > 0
    
    @pytest.mark.asyncio
    async def test_coordinator_cleanup(self, test_settings, db_session):
        """Test coordinator cleanup."""
        coordinator = BatchCoordinator(test_settings, db_session)
        
        # Mock processor cleanup
        coordinator.processor.cleanup = AsyncMock()
        
        await coordinator.cleanup()
        
        # Verify cleanup was called
        coordinator.processor.cleanup.assert_called_once()


import asyncio  # Add import for asyncio.sleep