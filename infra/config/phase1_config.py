"""
Phase 1 Configuration — Feature flags, model routing, budgets, telemetry
Centralized config for all orchestrator components
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import os


# ============================================================================
# Model Routing Configuration
# ============================================================================

class ModelRoute(BaseModel):
    """Model routing for specific task"""
    primary: str
    fallback: List[str] = Field(default_factory=list)
    timeout_seconds: int = 12
    max_retries: int = 1


class ModelRoutingConfig(BaseModel):
    """Model routing rules for all agents"""
    keyphrase_mining: ModelRoute = ModelRoute(
        primary="gpt-5",
        fallback=["gpt-5-mini", "gpt-3.5-turbo"],
        timeout_seconds=30
    )
    query_expansion: ModelRoute = ModelRoute(
        primary="gpt-5-mini",
        fallback=["gpt-3.5-turbo"],
        timeout_seconds=20
    )
    sentiment_emotion: ModelRoute = ModelRoute(
        primary="gpt-5",
        fallback=["gpt-5-mini"],
        timeout_seconds=30
    )
    topic_modeler: ModelRoute = ModelRoute(
        primary="gpt-5",
        fallback=["gpt-5-mini", "gpt-3.5-turbo"],
        timeout_seconds=30
    )


# ============================================================================
# Budget & Limits Configuration
# ============================================================================

class BudgetConfig(BaseModel):
    """Budget and rate limit configuration"""
    # Per-command limits
    max_tokens_per_command: int = 8000
    max_cost_cents_per_command: int = 50  # $0.50

    # Per-user limits (daily)
    max_commands_per_user_daily: int = 100
    max_cost_per_user_daily_cents: int = 500  # $5.00

    # Global limits
    enable_budget_tracking: bool = True
    fallback_on_budget_exceeded: bool = True


# ============================================================================
# Retrieval Configuration
# ============================================================================

class RetrievalConfig(BaseModel):
    """Retrieval pipeline configuration"""
    # RRF parameters
    enable_rrf: bool = True
    rrf_k: int = 60  # RRF constant

    # Reranking
    enable_rerank: bool = False  # Feature flag
    rerank_model: str = "cohere-rerank-v3"
    rerank_top_n: int = 10

    # Retrieval limits
    pre_filter_limit: int = 50
    post_rrf_limit: int = 30
    default_k_final: int = 5  # Top-k for analysis
    max_k_final: int = 10

    # Caching
    enable_retrieval_cache: bool = True
    retrieval_cache_ttl_seconds: int = 300  # 5 minutes


# ============================================================================
# Agent Configuration
# ============================================================================

class AgentConfig(BaseModel):
    """Agent-specific configuration"""
    # Parallel execution
    enable_parallel_agents: bool = True
    max_parallel_agents: int = 4

    # Degradation settings
    enable_graceful_degradation: bool = True
    min_context_on_budget_exceeded: int = 3  # Minimum docs to keep

    # Cache
    enable_agent_cache: bool = True
    agent_cache_ttl_seconds: int = 900  # 15 minutes


# ============================================================================
# Validation & Policy Configuration
# ============================================================================

class PolicyConfig(BaseModel):
    """Policy layer configuration"""
    # Evidence requirements
    enforce_evidence_required: bool = True
    min_evidence_per_insight: int = 1

    # Length limits
    max_tldr_length: int = 220
    max_insight_length: int = 180
    max_snippet_length: int = 240

    # Safety
    enable_pii_check: bool = True
    enable_domain_whitelist: bool = True
    blacklisted_domains: List[str] = Field(
        default_factory=lambda: ["spam.com", "phishing.net"]
    )


# ============================================================================
# Telemetry Configuration
# ============================================================================

class TelemetryConfig(BaseModel):
    """Telemetry and monitoring configuration"""
    enable_correlation_tracking: bool = True
    enable_metrics: bool = True
    enable_detailed_logging: bool = True

    # Metrics to track
    track_latency: bool = True
    track_cost: bool = True
    track_cache_hits: bool = True
    track_fallbacks: bool = True

    # Log levels
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


# ============================================================================
# Feature Flags
# ============================================================================

class FeatureFlags(BaseModel):
    """Feature flags for Phase 1"""
    # Commands
    enable_trends_enhanced: bool = True
    enable_analyze_keywords: bool = True
    enable_analyze_sentiment: bool = True
    enable_analyze_topics: bool = True

    # Advanced features
    enable_query_expansion: bool = True
    enable_aspect_sentiment: bool = True
    enable_timeline_sentiment: bool = True
    enable_emerging_topics: bool = True

    # Experimental
    enable_multi_language: bool = False  # Future
    enable_cross_lingual: bool = False  # Future


# ============================================================================
# Main Phase 1 Configuration
# ============================================================================

class Phase1Config(BaseSettings):
    """Main configuration for Phase 1 orchestrator"""

    # Version
    version: str = "phase1-v1.0"
    environment: Literal["dev", "staging", "prod"] = "dev"

    # Sub-configs
    models: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    # Database
    pg_dsn: Optional[str] = Field(default=None, alias="PG_DSN")

    # API Keys (loaded from env)
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env variables not defined in model


# ============================================================================
# Config Singleton
# ============================================================================

_config_instance: Optional[Phase1Config] = None


def get_config() -> Phase1Config:
    """Get singleton config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Phase1Config()
    return _config_instance


def reload_config() -> Phase1Config:
    """Reload config from environment"""
    global _config_instance
    _config_instance = Phase1Config()
    return _config_instance


# ============================================================================
# Config Helpers
# ============================================================================

def is_feature_enabled(feature_name: str) -> bool:
    """Check if feature is enabled"""
    config = get_config()
    return getattr(config.features, feature_name, False)


def get_model_route(task: str) -> ModelRoute:
    """Get model routing for task"""
    config = get_config()
    return getattr(config.models, task, None)


def get_budget_limit(limit_type: str) -> int:
    """Get budget limit by type"""
    config = get_config()
    return getattr(config.budget, limit_type, 0)