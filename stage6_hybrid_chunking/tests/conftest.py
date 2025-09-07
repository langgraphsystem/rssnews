"""
Pytest configuration and fixtures for Stage 6 tests.
"""

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config.settings import Settings, Environment
from src.db.models import Base, Article, ArticleChunk
from src.utils.metrics import InMemoryMetrics
from src.utils.logging import configure_logging


# Configure logging for tests
configure_logging(log_level="WARNING", log_format="console", enable_tracing=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        environment=Environment.TESTING,
        debug=True,
        
        # Database settings
        database_url="sqlite+aiosqlite:///:memory:",
        db_pool_size=1,
        db_max_overflow=1,
        
        # Redis settings (mock)
        redis_url="redis://localhost:6379/15",
        
        # Gemini settings (mock)
        gemini_api_key="test-api-key",
        gemini_model="gemini-2.5-flash",
        
        # Chunking settings
        chunking_target_words=400,
        chunking_overlap_words=80,
        chunking_min_words=200,
        chunking_max_words=600,
        
        # Rate limiting
        rate_limit_max_llm_calls_per_min=10,
        rate_limit_max_llm_calls_per_batch=5,
        
        # Feature flags
        llm_routing_enabled=True,
        llm_chunk_refine_enabled=True,
        
        # Observability
        log_level="WARNING",
        log_format="console",
        metrics_enabled=False,
        tracing_enabled=False
    )


@pytest_asyncio.fixture
async def db_engine(test_settings):
    """Create test database engine."""
    engine = create_async_engine(
        test_settings.database_url,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False}
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    """Create test database session."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
def sample_articles() -> List[Dict]:
    """Create sample article data for testing."""
    return [
        {
            "id": 1,
            "title": "Sample News Article",
            "content": """This is a sample news article with multiple paragraphs.

The article discusses various topics including technology and science.

It has sufficient content to create multiple chunks during processing.

The content includes various formatting elements and should trigger different chunking strategies.

This final paragraph concludes the article content.""",
            "source_domain": "example.com",
            "language": "en",
            "published_at": datetime.utcnow()
        },
        {
            "id": 2, 
            "title": "Short Article",
            "content": "This is a very short article that might not need chunking.",
            "source_domain": "test.com",
            "language": "en",
            "published_at": datetime.utcnow()
        },
        {
            "id": 3,
            "title": "Complex Article with Lists",
            "content": """This article contains complex formatting:

• First bullet point
• Second bullet point  
• Third bullet point

And also has:
- Dash list item
- Another dash item

Plus some code:
```python
def example():
    return "hello"
```

And a table:
| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |

This complexity should trigger LLM processing.""",
            "source_domain": "complex.com", 
            "language": "en",
            "published_at": datetime.utcnow()
        }
    ]


@pytest_asyncio.fixture
async def db_articles(db_session: AsyncSession, sample_articles) -> List[Article]:
    """Create articles in test database."""
    articles = []
    
    for article_data in sample_articles:
        article = Article(
            id=article_data["id"],
            title=article_data["title"],
            content=article_data["content"],
            source_domain=article_data["source_domain"],
            language=article_data["language"],
            published_at=article_data["published_at"]
        )
        db_session.add(article)
        articles.append(article)
    
    await db_session.commit()
    
    # Refresh to get IDs
    for article in articles:
        await db_session.refresh(article)
    
    return articles


@pytest.fixture
def mock_gemini_client():
    """Create mock Gemini client for testing."""
    mock_client = AsyncMock()
    
    # Mock health check
    mock_client.health_check.return_value = True
    
    # Mock stats
    mock_client.get_stats.return_value = {
        'total_requests': 0,
        'total_tokens': 0,
        'circuit_breaker_state': 'closed',
        'circuit_breaker_failures': 0,
        'rate_limiter_calls_window': 0
    }
    
    # Mock refine_chunk method
    async def mock_refine_chunk(chunk_text, chunk_metadata, article_metadata, context=None):
        from src.llm.gemini_client import LLMRefinementResult
        
        # Return different responses based on chunk content
        if len(chunk_text.split()) < 50:
            action = "merge_next"
        elif "•" in chunk_text or "-" in chunk_text:
            action = "keep"
        elif "```" in chunk_text:
            action = "keep"
        else:
            action = "keep"
        
        return LLMRefinementResult(
            action=action,
            offset_adjust=0,
            semantic_type="body",
            confidence=0.8,
            reason=f"Mocked refinement for {action}"
        )
    
    mock_client.refine_chunk.side_effect = mock_refine_chunk
    mock_client.close = AsyncMock()
    
    return mock_client


@pytest.fixture
def test_metrics():
    """Create test metrics collector."""
    return InMemoryMetrics(max_history=100)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    mock_redis = MagicMock()
    
    # Mock basic Redis operations
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=False)
    
    return mock_redis


class MockLLMRefinementResult:
    """Mock LLM refinement result for testing."""
    
    def __init__(self, action="keep", offset_adjust=0, semantic_type="body", confidence=0.8, reason="test"):
        self.action = action
        self.offset_adjust = offset_adjust
        self.semantic_type = semantic_type
        self.confidence = confidence
        self.reason = reason


# Test data factories

def create_test_chunk(index: int = 0, 
                     text: str = "Test chunk content",
                     word_count: int = None) -> Dict:
    """Create test chunk data."""
    word_count = word_count or len(text.split())
    
    return {
        'index': index,
        'text': text,
        'char_start': index * 100,
        'char_end': (index * 100) + len(text),
        'word_count': word_count,
        'metadata': {}
    }


def create_test_article_metadata(title: str = "Test Article",
                               source_domain: str = "test.com",
                               language: str = "en") -> Dict:
    """Create test article metadata."""
    return {
        'title': title,
        'source_domain': source_domain, 
        'language': language,
        'published_at': datetime.utcnow().isoformat(),
        'content_length': 1000,
        'total_chunks': 3
    }


# Async test utilities

def async_test(coro):
    """Decorator to run async tests."""
    def wrapper():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro())
        finally:
            loop.close()
    return wrapper


# Test markers

pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.slow = pytest.mark.slow


# Test environment setup

def setup_test_environment():
    """Setup test environment variables."""
    os.environ.update({
        'ENVIRONMENT': 'testing',
        'DEBUG': 'true',
        'DATABASE_URL': 'sqlite+aiosqlite:///:memory:',
        'REDIS_URL': 'redis://localhost:6379/15',
        'GEMINI_API_KEY': 'test-api-key',
        'LOG_LEVEL': 'WARNING',
        'METRICS_ENABLED': 'false',
        'TRACING_ENABLED': 'false'
    })


# Call setup on module load
setup_test_environment()