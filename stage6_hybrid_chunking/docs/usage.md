# Usage Guide

Complete guide for using Stage 6 Hybrid Chunking system in various scenarios.

## Quick Start Examples

### CLI Usage

#### Process Specific Articles
```bash
# Single article
stage6 process-articles --article-id 123

# Multiple articles  
stage6 process-articles --article-id 123 --article-id 456 --article-id 789

# With priority
stage6 process-articles --article-id 123 --priority urgent
```

#### Process by Source Domain
```bash
# Process latest articles from domain
stage6 process-articles --source-domain news.example.com --max-articles 50

# High priority processing for breaking news
stage6 process-articles --source-domain breaking.news --priority high

# Background processing for archived content
stage6 process-articles --source-domain archive.site --priority low --max-articles 1000
```

#### Batch Processing Options
```bash
# Custom batch size
stage6 process-articles --source-domain tech.blog --batch-size 25

# Direct processing (bypass coordinator)
stage6 process-articles --article-id 123 --no-use-coordinator

# Dry run to see what would be processed
stage6 process-articles --source-domain test.site --dry-run
```

### Python API Usage

#### Basic Processing

```python
import asyncio
from src.config.settings import Settings
from src.stage6.pipeline import Stage6Pipeline
from src.db.models import Article
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def process_articles():
    # Initialize
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession)
    
    async with async_session() as db_session:
        # Create pipeline
        pipeline = Stage6Pipeline(settings, db_session)
        
        # Get articles to process
        articles = await get_articles_from_database(db_session)
        
        # Process batch
        result = await pipeline.process_articles_batch(
            articles,
            context={'api_processing': True}
        )
        
        print(f"Processed {result.articles_processed} articles")
        print(f"Created {result.chunks_created} chunks")
        print(f"Processing time: {result.processing_time_ms}ms")

# Run
asyncio.run(process_articles())
```

#### Advanced Processing with Coordinator

```python
from src.stage6.coordinator import BatchCoordinator, JobPriority

async def process_with_coordinator():
    settings = Settings()
    async with get_db_session(settings) as db_session:
        # Create coordinator
        coordinator = BatchCoordinator(settings, db_session)
        
        # Submit high-priority job
        job_id = await coordinator.submit_job(
            article_ids=[1, 2, 3, 4, 5],
            priority=JobPriority.HIGH,
            context={'urgent_processing': True}
        )
        
        # Monitor job progress
        while True:
            status = await coordinator.get_job_status(job_id)
            if status['status'] == 'completed':
                print(f"Job completed: {status['result']}")
                break
            elif status['status'] == 'failed':
                print(f"Job failed: {status['error_message']}")
                break
            
            await asyncio.sleep(2)
```

## Celery Integration

### Start Workers

```bash
# Start default worker
stage6 worker

# Start with specific configuration
stage6 worker --queue stage6_processing --concurrency 8 --log-level INFO

# Start multiple workers for different queues
stage6 worker --queue stage6_processing &
stage6 worker --queue stage6_monitoring &
stage6 worker --queue stage6_maintenance &
```

### Submit Tasks Programmatically

```python
from src.tasks.tasks import process_articles_task, batch_process_task

# Submit single processing task
result = process_articles_task.delay(
    article_ids=[1, 2, 3],
    context={'celery_processing': True}
)

# Submit batch processing task
batch_result = batch_process_task.delay(
    article_ids=list(range(1, 101)),  # 100 articles
    batch_config={
        'batch_size': 25,
        'max_concurrent_batches': 4,
        'retry_failed_articles': True
    }
)

# Check results
print(f"Task ID: {result.id}")
print(f"Status: {result.status}")
print(f"Result: {result.result}")
```

### Monitoring Tasks

```bash
# Monitor Celery tasks
celery -A src.celery_app events

# Flower web monitoring
pip install flower
celery -A src.celery_app flower
# Visit http://localhost:5555
```

## System Monitoring

### Health Checks

```bash
# Basic health check
stage6 health-check

# Detailed health information
stage6 health-check --detailed --timeout 10

# Continuous monitoring
stage6 status --watch --interval 5

# Component-specific health
stage6 health-check | grep database
stage6 health-check | grep llm_api
```

### Performance Monitoring

```bash
# View current system status
stage6 status

# Watch metrics in real-time
stage6 status --watch

# Check processing statistics
stage6 status | grep -A5 "Processing Stats"
```

## Configuration Scenarios

### Development Setup

```bash
# .env.development
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
LOG_FORMAT=console

# Smaller chunks for faster testing
CHUNKING_TARGET_WORDS=200
CHUNKING_MIN_WORDS=100

# Limited LLM usage to save costs
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=10
RATE_LIMIT_DAILY_COST_LIMIT_USD=1.0

# Local services
DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/stage6_dev
REDIS_URL=redis://localhost:6379/0
```

### Testing Configuration

```python
# tests/conftest.py
import pytest
from src.config.settings import Settings, Environment

@pytest.fixture
def test_settings():
    return Settings(
        environment=Environment.TESTING,
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        gemini_api_key="test-key",
        chunking_target_words=100,
        llm_chunk_refine_enabled=False,  # Disable LLM in tests
        metrics_enabled=False,
        tracing_enabled=False
    )
```

### Production Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: stage6_prod
      POSTGRES_USER: stage6_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    
  worker:
    build: .
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://stage6_user:${DB_PASSWORD}@postgres:5432/stage6_prod
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      ENVIRONMENT: production
    command: ["stage6", "worker", "--concurrency", "4"]
    deploy:
      replicas: 3
      
  scheduler:
    build: .
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://stage6_user:${DB_PASSWORD}@postgres:5432/stage6_prod
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    command: ["celery", "-A", "src.celery_app", "beat"]
    
volumes:
  postgres_data:
```

## Advanced Usage Patterns

### Custom Processing Pipeline

```python
from src.chunking.base_chunker import BaseChunker
from src.chunking.quality_router import QualityRouter
from src.llm.gemini_client import GeminiClient

class CustomPipeline:
    def __init__(self, settings):
        self.settings = settings
        self.chunker = BaseChunker(settings)
        self.router = QualityRouter(settings)
        self.llm_client = GeminiClient(settings)
    
    async def process_with_custom_logic(self, article, custom_params):
        # Custom pre-processing
        processed_content = self.preprocess_article(article, custom_params)
        
        # Base chunking
        chunks = self.chunker.chunk_text(processed_content, article.metadata)
        
        # Custom routing logic
        routing_decisions = self.custom_routing(chunks, custom_params)
        
        # Selective LLM processing
        refined_chunks = []
        for chunk, decision in routing_decisions:
            if decision.needs_llm:
                refined = await self.llm_client.refine_chunk(
                    chunk.text, chunk.metadata, article.metadata
                )
                if refined:
                    chunk = self.apply_refinement(chunk, refined)
            refined_chunks.append(chunk)
        
        return refined_chunks
```

### Batch Processing with Custom Configuration

```python
from src.stage6.processor import ChunkProcessor, BatchConfiguration

async def custom_batch_processing():
    # Custom batch configuration
    batch_config = BatchConfiguration(
        batch_size=75,                    # Larger batches
        max_concurrent_batches=5,         # More concurrency
        retry_failed_articles=True,       # Enable retries
        max_retries=3,                   # More retry attempts
        backpressure_threshold=0.9       # Higher threshold
    )
    
    processor = ChunkProcessor(settings, db_session, batch_config)
    
    # Process with custom context
    result = await processor.process_articles(
        article_ids,
        processing_context={
            'custom_processing': True,
            'priority': 'high',
            'source': 'api_request',
            'user_id': 'user_123'
        }
    )
    
    return result
```

### Metrics and Observability Integration

```python
from src.utils.metrics import PrometheusMetrics, Stage6Metrics
from src.utils.tracing import initialize_tracing, traced_operation
from src.utils.logging import ComponentLogger

async def monitored_processing():
    # Initialize observability
    initialize_tracing(service_name="custom-processor")
    logger = ComponentLogger("custom_processor")
    
    # Set up metrics
    metrics_collector = PrometheusMetrics(namespace="custom")
    stage6_metrics = Stage6Metrics(metrics_collector)
    
    async with traced_operation("custom_article_processing"):
        logger.info("Starting custom processing")
        
        # Your processing logic
        start_time = time.time()
        result = await process_articles()
        processing_time = time.time() - start_time
        
        # Record metrics
        stage6_metrics.articles_processed.inc(result.articles_processed)
        stage6_metrics.chunks_created.inc(result.chunks_created)
        stage6_metrics.batch_processing_time.observe(processing_time)
        
        logger.info("Processing completed", 
                   articles=result.articles_processed,
                   chunks=result.chunks_created,
                   duration_seconds=processing_time)
```

## Error Handling and Recovery

### Handling Processing Errors

```python
from src.stage6.pipeline import Stage6Pipeline

async def robust_processing(articles):
    pipeline = Stage6Pipeline(settings, db_session)
    
    try:
        result = await pipeline.process_articles_batch(articles)
        
        if result.errors:
            logger.warning(f"Processing completed with {len(result.errors)} errors")
            for error in result.errors:
                logger.error(f"Processing error: {error}")
        
        return result
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        
        # Attempt recovery with reduced batch size
        if len(articles) > 1:
            logger.info("Attempting recovery with smaller batches")
            
            results = []
            for article in articles:
                try:
                    single_result = await pipeline.process_articles_batch([article])
                    results.append(single_result)
                except Exception as single_error:
                    logger.error(f"Failed to process article {article.id}: {single_error}")
            
            return combine_results(results)
        else:
            raise
```

### Circuit Breaker and Rate Limiting

```python
# Monitor circuit breaker status
status = await pipeline.get_pipeline_status()
circuit_breaker_state = status.get('gemini_stats', {}).get('circuit_breaker_state')

if circuit_breaker_state == 'open':
    logger.warning("Circuit breaker is open, waiting for recovery")
    await asyncio.sleep(60)  # Wait before retrying
elif circuit_breaker_state == 'half_open':
    logger.info("Circuit breaker is half-open, proceeding cautiously")
    # Process with reduced batch size
```

## Performance Tuning

### Optimizing for Throughput

```bash
# High-throughput configuration
CHUNKING_TARGET_WORDS=300           # Smaller chunks process faster
DB_POOL_SIZE=25                     # More database connections
REDIS_MAX_CONNECTIONS=100           # More Redis connections
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=150  # Higher API limits

# Worker configuration
stage6 worker --concurrency 8 --queue stage6_processing
```

### Optimizing for Quality

```bash
# Quality-focused configuration
CHUNKING_TARGET_WORDS=500           # Larger chunks for better context
CHUNKING_OVERLAP_WORDS=120          # More overlap for coherence
CHUNKING_CONFIDENCE_MIN=0.4         # Lower threshold = more LLM usage
RATE_LIMIT_MAX_LLM_PERCENTAGE_PER_BATCH=0.6  # Up to 60% LLM usage

# Use quality-focused prompts
LLM_ROUTING_ENABLED=true
GEMINI_TEMPERATURE=0.0              # More deterministic responses
```

### Cost Optimization

```bash
# Cost-optimized configuration  
CHUNKING_CONFIDENCE_MIN=0.8         # Higher threshold = fewer LLM calls
RATE_LIMIT_MAX_LLM_PERCENTAGE_PER_BATCH=0.15  # Max 15% LLM usage
RATE_LIMIT_DAILY_COST_LIMIT_USD=5.0 # Strict budget
GEMINI_MODEL=gemini-2.5-flash       # Most cost-effective model
```

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI, BackgroundTasks
from src.tasks.tasks import process_articles_task

app = FastAPI()

@app.post("/process-articles")
async def process_articles_endpoint(
    article_ids: List[int], 
    background_tasks: BackgroundTasks
):
    # Submit to Celery for background processing
    task = process_articles_task.delay(article_ids)
    
    return {
        "task_id": task.id,
        "status": "submitted",
        "article_count": len(article_ids)
    }

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task = process_articles_task.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result if task.ready() else None
    }
```

### Django Integration

```python
# models.py
from django.db import models

class ProcessingJob(models.Model):
    task_id = models.CharField(max_length=255)
    article_ids = models.JSONField()
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)

# tasks.py
from celery import shared_task
from .models import ProcessingJob

@shared_task(bind=True)
def django_process_articles(self, job_id, article_ids):
    from src.tasks.tasks import process_articles_task
    
    job = ProcessingJob.objects.get(id=job_id)
    job.status = 'processing'
    job.save()
    
    try:
        result = process_articles_task.delay(article_ids)
        job.result = result.get()
        job.status = 'completed'
    except Exception as e:
        job.status = 'failed'
        job.result = {'error': str(e)}
    finally:
        job.completed_at = timezone.now()
        job.save()
```

### Webhook Integration

```python
import httpx

async def process_with_webhook_notification(article_ids, webhook_url):
    """Process articles and send webhook notification."""
    
    try:
        # Start processing
        result = await process_articles(article_ids)
        
        # Send success notification
        notification = {
            "event": "processing_completed",
            "articles_processed": result.articles_processed,
            "chunks_created": result.chunks_created,
            "processing_time_ms": result.processing_time_ms,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=notification)
            
    except Exception as e:
        # Send error notification
        error_notification = {
            "event": "processing_failed",
            "error": str(e),
            "article_ids": article_ids,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=error_notification)
```

This usage guide covers the most common scenarios and integration patterns for Stage 6 Hybrid Chunking. For more specific use cases or advanced configurations, refer to the [Configuration Guide](configuration.md) and [API Documentation](api.md).