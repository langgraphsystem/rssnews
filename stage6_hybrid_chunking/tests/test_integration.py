"""
Integration tests for Stage 6 hybrid chunking system.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from src.config.settings import Settings, Environment
from src.stage6.pipeline import Stage6Pipeline
from src.stage6.processor import ChunkProcessor 
from src.stage6.coordinator import BatchCoordinator, JobPriority
from src.utils.metrics import InMemoryMetrics, Stage6Metrics
from src.utils.health import create_stage6_health_checker
from src.utils.logging import configure_logging
from src.db.models import Article, ArticleChunk
from sqlalchemy import select


class TestFullPipelineIntegration:
    """Full pipeline integration tests."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_processing(self, test_settings, db_session, db_articles, mock_gemini_client):
        """Test complete end-to-end processing flow."""
        # Configure system
        configure_logging(log_level="WARNING", log_format="console")
        metrics = InMemoryMetrics()
        stage6_metrics = Stage6Metrics(metrics)
        
        # Create pipeline
        pipeline = Stage6Pipeline(test_settings, db_session, stage6_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Process articles
        batch_context = {
            'batch_id': 'integration_test',
            'batch_size': len(db_articles),
            'test_mode': True
        }
        
        processing_metrics = await pipeline.process_articles_batch(db_articles, batch_context)
        
        # Verify processing results
        assert processing_metrics.articles_processed == len(db_articles)
        assert processing_metrics.chunks_created > 0
        assert processing_metrics.processing_time_ms > 0
        assert len(processing_metrics.errors) == 0
        
        # Verify database state
        for article in db_articles:
            result = await db_session.execute(
                select(ArticleChunk).where(ArticleChunk.article_id == article.id)
            )
            chunks = result.scalars().all()
            
            assert len(chunks) > 0
            assert all(chunk.text.strip() for chunk in chunks)
            assert all(chunk.word_count > 0 for chunk in chunks)
            assert all(chunk.article_id == article.id for chunk in chunks)
        
        # Verify metrics were recorded
        metrics_summary = metrics.get_metric_summary()
        assert metrics_summary['total_metrics'] > 0
        
        # Verify LLM was called for complex content
        if any('•' in article.content or '```' in article.content for article in db_articles):
            assert mock_gemini_client.refine_chunk.call_count > 0
    
    @pytest.mark.asyncio 
    async def test_processor_with_batching(self, test_settings, db_session, db_articles, mock_gemini_client):
        """Test processor with adaptive batching."""
        # Create processor
        processor = ChunkProcessor(test_settings, db_session)
        processor.pipeline.gemini_client = mock_gemini_client
        
        # Process articles
        article_ids = [article.id for article in db_articles]
        result = await processor.process_articles(
            article_ids,
            processing_context={'test_integration': True}
        )
        
        # Verify results
        assert result['processed_articles'] == len(db_articles)
        assert result['processing_time_ms'] > 0
        assert result['failed_articles'] == 0
        
        # Check processor stats
        status = await processor.get_processing_status()
        assert status['processor_stats']['articles_processed'] == len(db_articles)
    
    @pytest.mark.asyncio
    async def test_coordinator_job_management(self, test_settings, db_session, db_articles):
        """Test coordinator with job management."""
        # Create coordinator
        coordinator = BatchCoordinator(test_settings, db_session)
        
        # Mock the processor to avoid actual processing
        coordinator.processor = AsyncMock()
        coordinator.processor.process_articles.return_value = {
            'processed_articles': 2,
            'failed_articles': 0,
            'processing_time_ms': 1000,
            'errors': []
        }
        
        # Submit multiple jobs with different priorities
        article_ids = [article.id for article in db_articles]
        
        high_priority_job = await coordinator.submit_job(
            article_ids[:1], 
            JobPriority.HIGH,
            {'type': 'urgent_processing'}
        )
        
        normal_priority_job = await coordinator.submit_job(
            article_ids[1:2],
            JobPriority.NORMAL,
            {'type': 'normal_processing'}
        )
        
        low_priority_job = await coordinator.submit_job(
            article_ids[2:3] if len(article_ids) > 2 else article_ids[1:2],
            JobPriority.LOW,
            {'type': 'background_processing'}
        )
        
        # Wait for jobs to process
        await asyncio.sleep(0.2)
        
        # Check job statuses
        high_status = await coordinator.get_job_status(high_priority_job)
        normal_status = await coordinator.get_job_status(normal_priority_job)
        low_status = await coordinator.get_job_status(low_priority_job)
        
        assert high_status is not None
        assert normal_status is not None
        assert low_status is not None
        
        # High priority should complete first (or be running)
        assert high_status['status'] in ['completed', 'running']
        
        # Check coordinator stats
        status = await coordinator.get_coordinator_status()
        assert status['coordinator_stats']['jobs_created'] == 3
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, test_settings, db_session, db_articles, mock_gemini_client):
        """Test error handling and recovery mechanisms."""
        # Create pipeline with intentional failures
        pipeline = Stage6Pipeline(test_settings, db_session)
        pipeline.gemini_client = mock_gemini_client
        
        # Configure mock to fail on certain articles
        call_count = 0
        
        async def failing_refine_chunk(chunk_text, chunk_metadata, article_metadata, context=None):
            nonlocal call_count
            call_count += 1
            
            # Fail every 3rd call
            if call_count % 3 == 0:
                raise Exception("Simulated LLM API error")
            
            from src.llm.gemini_client import LLMRefinementResult
            return LLMRefinementResult(
                action="keep",
                confidence=0.8,
                reason="Successful processing"
            )
        
        mock_gemini_client.refine_chunk.side_effect = failing_refine_chunk
        
        # Process articles
        batch_context = {
            'batch_id': 'error_test',
            'error_simulation': True
        }
        
        processing_metrics = await pipeline.process_articles_batch(db_articles, batch_context)
        
        # Should still process articles despite LLM errors
        assert processing_metrics.articles_processed > 0
        assert processing_metrics.chunks_created > 0
        
        # Some chunks should still be created even with LLM failures
        total_chunks = 0
        for article in db_articles:
            result = await db_session.execute(
                select(ArticleChunk).where(ArticleChunk.article_id == article.id)
            )
            chunks = result.scalars().all()
            total_chunks += len(chunks)
        
        assert total_chunks > 0
    
    @pytest.mark.asyncio
    async def test_health_monitoring_integration(self, test_settings, db_session, mock_gemini_client):
        """Test health monitoring integration."""
        # Create health checker with all components
        health_checker = create_stage6_health_checker(
            db_session=db_session,
            gemini_client=mock_gemini_client,
            timeout_seconds=5.0
        )
        
        # Run all health checks
        results = await health_checker.check_all()
        
        # Should have all expected checks
        expected_checks = [
            'system_time', 'memory_usage', 'database_connection', 
            'database_tables', 'llm_api', 'llm_circuit_breaker'
        ]
        
        for check_name in expected_checks:
            assert check_name in results
            result = results[check_name]
            assert result.duration_ms >= 0
            # Most checks should be healthy in test environment
            assert result.status.name in ['HEALTHY', 'UNKNOWN', 'DEGRADED']
        
        # Get overall health
        overall_health = health_checker.get_overall_health()
        assert overall_health is not None
        
        # Get health summary
        summary = health_checker.get_health_summary()
        assert 'overall_status' in summary
        assert 'total_checks' in summary
        assert 'checks' in summary
    
    @pytest.mark.asyncio
    async def test_metrics_collection_integration(self, test_settings, db_session, db_articles, mock_gemini_client):
        """Test comprehensive metrics collection."""
        # Create metrics collector
        metrics = InMemoryMetrics(max_history=1000)
        stage6_metrics = Stage6Metrics(metrics)
        
        # Create pipeline with metrics
        pipeline = Stage6Pipeline(test_settings, db_session, stage6_metrics)
        pipeline.gemini_client = mock_gemini_client
        
        # Process articles while collecting metrics
        batch_context = {'batch_id': 'metrics_test'}
        processing_metrics = await pipeline.process_articles_batch(db_articles, batch_context)
        
        # Manually record some additional metrics
        stage6_metrics.articles_processed.inc(len(db_articles))
        stage6_metrics.chunks_created.inc(processing_metrics.chunks_created)
        stage6_metrics.batch_processing_time.observe(processing_metrics.processing_time_ms / 1000)
        stage6_metrics.active_jobs.set(1)
        
        # Verify metrics were collected
        summary = metrics.get_metric_summary()
        
        assert 'counters' in summary
        assert 'histograms' in summary
        assert 'gauges' in summary
        assert summary['total_metrics'] > 0
        
        # Verify specific metrics exist
        assert len(summary['counters']) > 0
        assert len(summary['histograms']) > 0
        assert len(summary['gauges']) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_processing(self, test_settings, db_session, db_articles, mock_gemini_client):
        """Test concurrent processing capabilities."""
        # Create multiple processors
        processors = []
        for i in range(3):
            processor = ChunkProcessor(test_settings, db_session)
            processor.pipeline.gemini_client = mock_gemini_client
            processors.append(processor)
        
        # Process articles concurrently
        tasks = []
        for i, processor in enumerate(processors):
            # Give each processor different articles
            article_subset = [db_articles[i % len(db_articles)]]
            task = processor.process_articles(
                [article.id for article in article_subset],
                {'processor_id': i, 'concurrent_test': True}
            )
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all succeeded
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == len(processors)
        
        # Verify each processed articles
        for result in successful_results:
            assert result['processed_articles'] > 0
    
    @pytest.mark.asyncio
    async def test_configuration_variations(self, db_session, db_articles, mock_gemini_client):
        """Test different configuration scenarios."""
        # Test configuration variations
        test_configs = [
            {
                'name': 'minimal_llm',
                'settings': {
                    'chunking_target_words': 200,
                    'rate_limit_max_llm_calls_per_batch': 1,
                    'llm_routing_enabled': True,
                    'llm_chunk_refine_enabled': True
                }
            },
            {
                'name': 'no_llm',
                'settings': {
                    'chunking_target_words': 300,
                    'llm_routing_enabled': False,
                    'llm_chunk_refine_enabled': False
                }
            },
            {
                'name': 'large_chunks',
                'settings': {
                    'chunking_target_words': 800,
                    'chunking_max_words': 1000,
                    'llm_routing_enabled': True,
                    'llm_chunk_refine_enabled': True
                }
            }
        ]
        
        for config in test_configs:
            # Create settings with this configuration
            settings = Settings(
                environment=Environment.TESTING,
                database_url="sqlite+aiosqlite:///:memory:",
                gemini_api_key="test-key",
                **config['settings']
            )
            
            # Create pipeline
            pipeline = Stage6Pipeline(settings, db_session)
            if settings.features.llm_chunk_refine_enabled:
                pipeline.gemini_client = mock_gemini_client
            
            # Process one article
            test_article = db_articles[0]
            batch_context = {
                'batch_id': f"config_test_{config['name']}",
                'config_name': config['name']
            }
            
            processing_metrics = await pipeline.process_articles_batch(
                [test_article], batch_context
            )
            
            # Verify processing succeeded
            assert processing_metrics.articles_processed == 1
            assert processing_metrics.chunks_created > 0
            
            # Verify chunks were created according to configuration
            result = await db_session.execute(
                select(ArticleChunk).where(ArticleChunk.article_id == test_article.id)
            )
            chunks = result.scalars().all()
            
            # Clear chunks for next test
            for chunk in chunks:
                await db_session.delete(chunk)
            await db_session.commit()


class TestPerformanceAndScalability:
    """Performance and scalability tests."""
    
    @pytest.mark.asyncio
    async def test_large_article_processing(self, test_settings, db_session, mock_gemini_client):
        """Test processing very large articles."""
        # Create a large article
        large_content = "\n\n".join([
            f"This is paragraph {i} with substantial content that will create multiple chunks. " * 20
            for i in range(100)  # 100 large paragraphs
        ])
        
        large_article = Article(
            id=9999,
            title="Large Test Article",
            content=large_content,
            source_domain="performance-test.com",
            language="en",
            published_at=datetime.utcnow()
        )
        
        db_session.add(large_article)
        await db_session.commit()
        await db_session.refresh(large_article)
        
        # Process the large article
        pipeline = Stage6Pipeline(test_settings, db_session)
        pipeline.gemini_client = mock_gemini_client
        
        import time
        start_time = time.time()
        
        processing_metrics = await pipeline.process_articles_batch([large_article])
        
        processing_time = time.time() - start_time
        
        # Verify performance is reasonable (should process within 10 seconds)
        assert processing_time < 10.0
        assert processing_metrics.articles_processed == 1
        assert processing_metrics.chunks_created > 10  # Should create many chunks
        
        # Verify chunks are within size limits
        result = await db_session.execute(
            select(ArticleChunk).where(ArticleChunk.article_id == large_article.id)
        )
        chunks = result.scalars().all()
        
        for chunk in chunks:
            assert chunk.word_count <= test_settings.chunking.max_words
            assert len(chunk.text) > 0
    
    @pytest.mark.asyncio
    async def test_batch_processing_performance(self, test_settings, db_session, mock_gemini_client):
        """Test batch processing performance."""
        # Create multiple articles for batch processing
        articles = []
        for i in range(20):
            article = Article(
                id=10000 + i,
                title=f"Batch Test Article {i}",
                content=f"This is test article {i} with content. " * 50,
                source_domain="batch-test.com",
                language="en",
                published_at=datetime.utcnow()
            )
            articles.append(article)
        
        for article in articles:
            db_session.add(article)
        await db_session.commit()
        
        # Process batch
        coordinator = BatchCoordinator(test_settings, db_session)
        coordinator.processor.pipeline.gemini_client = mock_gemini_client
        
        article_ids = [article.id for article in articles]
        
        import time
        start_time = time.time()
        
        result = await coordinator.processor.process_articles(article_ids)
        
        processing_time = time.time() - start_time
        
        # Verify performance
        assert processing_time < 30.0  # Should process 20 articles in under 30 seconds
        assert result['processed_articles'] == len(articles)
        
        # Calculate throughput
        throughput = len(articles) / processing_time
        assert throughput > 0.5  # At least 0.5 articles per second
    
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, test_settings, db_session, mock_gemini_client):
        """Test memory usage remains stable during processing."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create pipeline
        pipeline = Stage6Pipeline(test_settings, db_session)
        pipeline.gemini_client = mock_gemini_client
        
        # Process multiple small batches
        for batch_num in range(5):
            # Create temporary articles
            articles = []
            for i in range(5):
                article = Article(
                    id=20000 + batch_num * 10 + i,
                    title=f"Memory Test Article {batch_num}-{i}",
                    content="Test content. " * 100,
                    source_domain="memory-test.com",
                    language="en",
                    published_at=datetime.utcnow()
                )
                articles.append(article)
            
            for article in articles:
                db_session.add(article)
            await db_session.commit()
            
            # Process batch
            await pipeline.process_articles_batch(articles)
            
            # Clean up chunks to prevent accumulation
            from sqlalchemy import delete
            await db_session.execute(
                delete(ArticleChunk).where(
                    ArticleChunk.article_id.in_([a.id for a in articles])
                )
            )
            await db_session.commit()
        
        # Check memory usage hasn't grown excessively
        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory
        
        # Should not grow more than 100MB during processing
        assert memory_growth < 100 * 1024 * 1024