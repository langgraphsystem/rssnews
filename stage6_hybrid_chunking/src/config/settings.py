"""Configuration management for Stage 6 Hybrid Chunking using Pydantic Settings."""

import secrets
from functools import lru_cache
from typing import Dict, List, Optional, Set

# Pydantic v2 moved BaseSettings to pydantic-settings.
try:
    from pydantic_settings import BaseSettings  # type: ignore
except Exception:
    # Fallback for environments pinned to pydantic<2
    from pydantic import BaseSettings  # type: ignore
from pydantic import Field, validator
from pydantic.types import PositiveInt, SecretStr


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""
    
    url: str = Field(
        default="postgresql+asyncpg://user:pass@host:port/db",
        env=["DATABASE_URL", "PG_DSN"],
        description="Database URL for async SQLAlchemy"
    )
    pool_size: int = Field(default=10, env="DB_POOL_SIZE", ge=1, le=50)
    max_overflow: int = Field(default=20, env="DB_MAX_OVERFLOW", ge=0, le=100)
    pool_timeout: int = Field(default=30, env="DB_POOL_TIMEOUT", ge=5, le=120)
    echo_sql: bool = Field(default=False, env="DB_ECHO_SQL")

    class Config:
        env_prefix = "DB_"


class RedisSettings(BaseSettings):
    """Redis configuration settings."""
    
    url: str = Field(
        default="redis://localhost:6379/0",
        env="REDIS_URL", 
        description="Redis URL for caching and locks"
    )
    max_connections: int = Field(default=50, env="REDIS_MAX_CONNECTIONS", ge=1, le=200)
    socket_timeout: int = Field(default=30, env="REDIS_SOCKET_TIMEOUT", ge=1, le=120)

    class Config:
        env_prefix = "REDIS_"


class GeminiSettings(BaseSettings):
    """Gemini 2.5 Flash API configuration."""
    
    api_key: SecretStr = Field(
        ...,
        env="GEMINI_API_KEY",
        description="Gemini API key"
    )
    model: str = Field(
        default="gemini-2.5-flash",
        env=["CHUNK_LLM_MODEL", "GEMINI_MODEL"],
        description="Gemini model to use"
    )
    embedding_model: str = Field(
        default="embedding-001",
        env=["GEMINI_EMBEDDING_MODEL", "EMBEDDING_MODEL"],
        description="Gemini model to use for embeddings"
    )
    base_url: str = Field(
        default="https://generativelanguage.googleapis.com",
        env="GEMINI_BASE_URL",
        description="Gemini API base URL"
    )
    
    # Request settings
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    
    # Retry settings
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_delay_base: float = Field(default=1.0, ge=0.1, le=10.0)
    retry_delay_max: float = Field(default=60.0, ge=1.0, le=300.0)
    
    # Circuit breaker settings
    circuit_breaker_threshold: int = Field(default=5, ge=1, le=20)
    circuit_breaker_timeout: int = Field(default=60, ge=10, le=300)

    class Config:
        env_prefix = "GEMINI_"


class ChunkingSettings(BaseSettings):
    """Chunking algorithm configuration."""
    
    # Target chunk sizes
    target_words: int = Field(default=400, ge=100, le=1000, description="Target chunk size in words")
    overlap_words: int = Field(default=80, ge=0, le=200, description="Overlap between chunks in words") 
    min_words: int = Field(default=200, ge=50, le=500, description="Minimum chunk size in words")
    max_words: int = Field(default=600, ge=400, le=2000, description="Maximum chunk size in words")
    
    # Character-based thresholds
    min_chars: int = Field(default=800, ge=200, le=2000, description="Minimum chunk size in characters")
    max_offset: int = Field(default=120, ge=50, le=200, description="Maximum offset adjustment")
    # Contextual overlap for reading only (does not change char offsets)
    overlap_tokens: int = Field(default=0, env="CHUNK_OVERLAP_TOKENS", ge=0, le=400, description="Contextual overlap size in characters")
    
    # Quality thresholds
    confidence_min: float = Field(default=0.60, ge=0.0, le=1.0, description="Minimum LLM confidence to apply")
    
    # Semantic type priorities (higher = more important)
    semantic_priorities: Dict[str, float] = Field(default={
        "intro": 1.0,
        "conclusion": 0.9,
        "quote": 0.7,
        "body": 0.5,
        "list": 0.4,
        "code": 0.6
    })
    
    @validator("overlap_words")
    def overlap_less_than_target(cls, v, values):
        target = values.get("target_words", 400)
        if v >= target:
            raise ValueError(f"overlap_words ({v}) must be less than target_words ({target})")
        return v
    
    @validator("min_words")
    def min_less_than_max(cls, v, values):
        max_words = values.get("max_words", 600)
        if v >= max_words:
            raise ValueError(f"min_words ({v}) must be less than max_words ({max_words})")
        return v

    class Config:
        env_prefix = "CHUNKING_"


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration for LLM calls."""
    
    # Per-minute quotas
    max_llm_calls_per_min: int = Field(default=60, ge=1, le=1000, description="Max LLM calls per minute globally")
    max_llm_calls_per_domain: int = Field(default=10, ge=1, le=100, description="Max LLM calls per domain per minute")
    
    # Batch limits
    max_llm_calls_per_batch: int = Field(default=100, ge=1, le=500, description="Max LLM calls per batch")
    max_llm_percentage_per_batch: float = Field(default=0.3, ge=0.0, le=1.0, description="Max % of chunks that can use LLM per batch", env="LLM_MAX_SHARE")
    
    # Cost controls
    daily_cost_limit_usd: float = Field(default=10.0, ge=0.1, le=1000.0, description="Daily cost limit in USD", env="LLM_DAILY_COST_CAP_USD")
    cost_per_token_input: float = Field(default=0.000125, ge=0.0, description="Cost per input token in USD")
    cost_per_token_output: float = Field(default=0.000375, ge=0.0, description="Cost per output token in USD")
    embedding_daily_cost_limit_usd: float = Field(default=10.0, ge=0.1, le=1000.0, description="Daily embeddings cost cap in USD", env="EMB_DAILY_COST_CAP_USD")
    
    class Config:
        env_prefix = "RATE_LIMIT_"


class FeatureFlags(BaseSettings):
    """Feature flags for enabling/disabling functionality."""
    
    llm_routing_enabled: bool = Field(default=True, env="LLM_ROUTING_ENABLED", description="Enable LLM quality routing")
    llm_chunk_refine_enabled: bool = Field(default=True, env="LLM_CHUNK_REFINE_ENABLED", description="Enable LLM chunk refinement")
    apply_chunk_edits: bool = Field(default=False, env="STAGE6_APPLY_EDITS", description="Apply LLM edit actions to boundaries")
    
    # Chunking strategies
    paragraph_chunking_enabled: bool = Field(default=True, description="Enable paragraph-based chunking")
    sliding_window_enabled: bool = Field(default=True, description="Enable sliding window as fallback")
    
    # Quality detection
    boilerplate_detection_enabled: bool = Field(default=True, description="Enable boilerplate detection")
    sentence_boundary_detection: bool = Field(default=True, description="Enable sentence boundary validation")
    
    # Performance features
    batch_processing_enabled: bool = Field(default=True, description="Enable batch processing")
    parallel_llm_calls: bool = Field(default=True, description="Enable parallel LLM calls")
    
    class Config:
        env_prefix = "FEATURE_"


class ObservabilitySettings(BaseSettings):
    """Observability and monitoring configuration."""
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT", pattern=r"^(json|text)$")
    
    # Metrics
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    metrics_port: int = Field(default=8000, env="METRICS_PORT", ge=1024, le=65535)
    
    # Tracing
    tracing_enabled: bool = Field(default=True, env="TRACING_ENABLED")
    trace_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, env="TRACE_SAMPLE_RATE")
    jaeger_endpoint: Optional[str] = Field(default=None, env="JAEGER_ENDPOINT")
    
    # Health checks
    health_check_enabled: bool = Field(default=True, env="HEALTH_CHECK_ENABLED")
    health_check_port: int = Field(default=8001, env="HEALTH_CHECK_PORT", ge=1024, le=65535)

    class Config:
        env_prefix = "OBSERVABILITY_"


class Settings(BaseSettings):
    """Main application settings."""
    
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT", pattern=r"^(development|testing|staging|production)$")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Application
    app_name: str = Field(default="stage6-hybrid-chunking", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    worker_id: str = Field(default_factory=lambda: f"worker-{secrets.token_hex(4)}", env="WORKER_ID")
    
    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    # Budgeting / LLM participation limits
    llm_max_share: float = Field(
        default=0.3,
        env="LLM_MAX_SHARE",
        ge=0.0,
        le=1.0,
        description="Max fraction of items allowed to use LLM in Stage 6"
    )
    
    # Quality router thresholds
    quality_router_thresholds: Dict[str, float] = Field(default={
        "too_short_ratio": 0.5,      # Chunk is <50% of target size
        "too_long_ratio": 1.5,       # Chunk is >150% of target size
        "sentence_incomplete": 0.8,   # Probability chunk ends mid-sentence
        "boilerplate_score": 0.3,     # Boilerplate detection score
        "quality_score_min": 0.4,     # Minimum article quality score
        "language_confidence_min": 0.7, # Minimum language detection confidence
    })
    
    # Domains that should never use LLM (too expensive/unreliable)
    llm_blacklist_domains: Set[str] = Field(default={
        "reddit.com",
        "twitter.com", 
        "facebook.com",
        "instagram.com",
        "tiktok.com"
    })
    
    # Domains that always use LLM (high quality sources)
    llm_whitelist_domains: Set[str] = Field(default={
        "reuters.com",
        "bbc.com",
        "apnews.com", 
        "bloomberg.com",
        "wsj.com"
    })
    
    @validator("quality_router_thresholds")
    def validate_thresholds(cls, v):
        required_keys = {
            "too_short_ratio", "too_long_ratio", "sentence_incomplete", 
            "boilerplate_score", "quality_score_min", "language_confidence_min"
        }
        missing = required_keys - set(v.keys())
        if missing:
            raise ValueError(f"Missing required threshold keys: {missing}")
        
        for key, value in v.items():
            if not 0.0 <= value <= 2.0:  # Reasonable bounds
                raise ValueError(f"Threshold {key}={value} must be between 0.0 and 2.0")
        
        return v
    
    @property
    def database_url(self) -> str:
        """Get database URL."""
        return self.database.url
    
    @property
    def redis_url(self) -> str:
        """Get Redis URL."""
        return self.redis.url
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"
    
    def should_use_llm_for_domain(self, domain: str) -> Optional[bool]:
        """
        Check if domain should use LLM.
        
        Returns:
            True if whitelisted
            False if blacklisted  
            None if no preference (use normal routing)
        """
        if domain in self.llm_blacklist_domains:
            return False
        if domain in self.llm_whitelist_domains:
            return True
        return None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
