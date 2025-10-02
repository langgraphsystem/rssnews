"""
Phase 2 Configuration — Extends Phase 1 with new agents, A/B testing, enhanced features
Adds: TrendForecaster, CompetitorNews, SynthesisAgent
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Import Phase 1 base classes
from infra.config.phase1_config import (
    ModelRoute,
    BudgetConfig,
    RetrievalConfig,
    AgentConfig,
    PolicyConfig,
    TelemetryConfig,
    Phase1Config
)


# ============================================================================
# Phase 2: Extended Model Routing
# ============================================================================

class Phase2ModelRoutingConfig(BaseModel):
    """Model routing rules for Phase 1 + Phase 2 agents"""
    # Phase 1 agents
    keyphrase_mining: ModelRoute = ModelRoute(
        primary="gemini-2.5-pro",
        fallback=["claude-4.5", "gpt-5"],
        timeout_seconds=10
    )
    query_expansion: ModelRoute = ModelRoute(
        primary="gemini-2.5-pro",
        fallback=["gpt-5"],
        timeout_seconds=8
    )
    sentiment_emotion: ModelRoute = ModelRoute(
        primary="gpt-5",
        fallback=["claude-4.5"],
        timeout_seconds=12
    )
    topic_modeler: ModelRoute = ModelRoute(
        primary="claude-4.5",
        fallback=["gpt-5", "gemini-2.5-pro"],
        timeout_seconds=15
    )

    # Phase 2: NEW agents
    trend_forecaster: ModelRoute = ModelRoute(
        primary="gpt-5",
        fallback=["claude-4.5"],
        timeout_seconds=15
    )
    competitor_news: ModelRoute = ModelRoute(
        primary="claude-4.5",
        fallback=["gpt-5", "gemini-2.5-pro"],
        timeout_seconds=18
    )
    synthesis_agent: ModelRoute = ModelRoute(
        primary="gpt-5",
        fallback=["claude-4.5"],
        timeout_seconds=12
    )


# ============================================================================
# Phase 2: A/B Testing Configuration
# ============================================================================

class ABTestConfig(BaseModel):
    """A/B testing configuration"""
    enable_ab_testing: bool = False  # Feature flag
    default_experiment: Optional[str] = None  # e.g., "sentiment_model_comparison"

    # Arm-specific overrides (experiment_name -> arm -> config)
    arm_overrides: Dict[str, Dict[str, Dict[str, any]]] = Field(default_factory=dict)

    # Traffic split
    default_traffic_split: Dict[str, float] = Field(
        default_factory=lambda: {"A": 0.5, "B": 0.5}
    )

    # Metrics to track per arm
    track_metrics: List[str] = Field(
        default_factory=lambda: ["latency", "cost", "confidence", "user_satisfaction"]
    )


# ============================================================================
# Phase 2: Enhanced Retrieval Configuration
# ============================================================================

class Phase2RetrievalConfig(RetrievalConfig):
    """Extended retrieval config with Phase 2 enhancements"""
    # Override: Enable reranking by default in Phase 2
    enable_rerank: bool = True

    # Phase 2: Domain filtering for competitors analysis
    enable_domain_extraction: bool = True
    min_domain_frequency: int = 3  # Min articles per domain for analysis


# ============================================================================
# Phase 2: Enhanced Feature Flags
# ============================================================================

class Phase2FeatureFlags(BaseModel):
    """Feature flags for Phase 2"""
    # Phase 1 commands (inherited)
    enable_trends_enhanced: bool = True
    enable_analyze_keywords: bool = True
    enable_analyze_sentiment: bool = True
    enable_analyze_topics: bool = True

    # Phase 2: NEW commands
    enable_predict_trends: bool = True
    enable_analyze_competitors: bool = True
    enable_synthesize: bool = True

    # Phase 2: Enhanced features
    enable_synthesis_in_trends: bool = False  # Auto-synthesis in /trends
    enable_forecast_in_trends: bool = False  # Auto-forecast in /trends

    # Advanced Phase 1 features
    enable_query_expansion: bool = True
    enable_aspect_sentiment: bool = True
    enable_timeline_sentiment: bool = True
    enable_emerging_topics: bool = True

    # Experimental
    enable_multi_language: bool = False
    enable_cross_lingual: bool = False


# ============================================================================
# Phase 2: Enhanced Budget Configuration
# ============================================================================

class Phase2BudgetConfig(BudgetConfig):
    """Extended budget config with Phase 2 command-specific limits"""
    # Override Phase 1 defaults with slightly higher limits for Phase 2
    max_tokens_per_command: int = 10000  # Increased for complex commands
    max_cost_cents_per_command: int = 75  # $0.75 (up from $0.50)

    # Per-command overrides
    predict_trends_max_tokens: int = 8000
    predict_trends_max_cost_cents: int = 60

    competitors_max_tokens: int = 12000
    competitors_max_cost_cents: int = 80

    synthesize_max_tokens: int = 8000
    synthesize_max_cost_cents: int = 50


# ============================================================================
# Main Phase 2 Configuration
# ============================================================================

class Phase2Config(BaseSettings):
    """Main configuration for Phase 2 orchestrator"""

    # Version
    version: str = "phase2-v1.0"
    environment: Literal["dev", "staging", "prod"] = "dev"

    # Sub-configs (Phase 2 versions)
    models: Phase2ModelRoutingConfig = Field(default_factory=Phase2ModelRoutingConfig)
    budget: Phase2BudgetConfig = Field(default_factory=Phase2BudgetConfig)
    retrieval: Phase2RetrievalConfig = Field(default_factory=Phase2RetrievalConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)  # Reuse Phase 1
    policy: PolicyConfig = Field(default_factory=PolicyConfig)  # Reuse Phase 1
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)  # Reuse Phase 1
    features: Phase2FeatureFlags = Field(default_factory=Phase2FeatureFlags)

    # Phase 2: A/B testing
    ab_test: ABTestConfig = Field(default_factory=ABTestConfig)

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


# ============================================================================
# Config Singleton
# ============================================================================

_phase2_config_instance: Optional[Phase2Config] = None


def get_phase2_config() -> Phase2Config:
    """Get singleton Phase 2 config instance"""
    global _phase2_config_instance
    if _phase2_config_instance is None:
        _phase2_config_instance = Phase2Config()
    return _phase2_config_instance


def reload_phase2_config() -> Phase2Config:
    """Reload Phase 2 config from environment"""
    global _phase2_config_instance
    _phase2_config_instance = Phase2Config()
    return _phase2_config_instance


# ============================================================================
# Config Helpers
# ============================================================================

def is_phase2_feature_enabled(feature_name: str) -> bool:
    """Check if Phase 2 feature is enabled"""
    config = get_phase2_config()
    return getattr(config.features, feature_name, False)


def get_phase2_model_route(task: str) -> Optional[ModelRoute]:
    """Get model routing for task (Phase 2)"""
    config = get_phase2_config()
    return getattr(config.models, task, None)


def assign_ab_test_arm(user_id: Optional[str] = None, correlation_id: Optional[str] = None) -> Optional[str]:
    """
    Assign A/B test arm based on user_id or correlation_id

    Args:
        user_id: User ID (deterministic assignment)
        correlation_id: Correlation ID (random assignment if no user_id)

    Returns:
        "A" or "B" or None if A/B testing disabled
    """
    config = get_phase2_config()

    if not config.ab_test.enable_ab_testing:
        return None

    # Deterministic assignment based on user_id
    if user_id:
        # Simple hash-based assignment
        hash_val = hash(user_id)
        return "A" if hash_val % 2 == 0 else "B"

    # Random assignment based on correlation_id
    if correlation_id:
        hash_val = hash(correlation_id)
        return "A" if hash_val % 2 == 0 else "B"

    # Default: random 50/50
    import random
    return random.choice(["A", "B"])


def get_ab_test_model_override(experiment: str, arm: str, task: str) -> Optional[str]:
    """
    Get model override for specific A/B test arm

    Args:
        experiment: Experiment name (e.g., "sentiment_model_comparison")
        arm: Arm identifier ("A" or "B")
        task: Task name (e.g., "sentiment_emotion")

    Returns:
        Model name or None if no override
    """
    config = get_phase2_config()

    if not config.ab_test.enable_ab_testing:
        return None

    # Check arm_overrides: {experiment: {arm: {task: model}}}
    arm_overrides = config.ab_test.arm_overrides
    if experiment in arm_overrides and arm in arm_overrides[experiment]:
        return arm_overrides[experiment][arm].get(task)

    return None


def get_phase2_budget_limit(command: str, limit_type: str = "tokens") -> int:
    """Get budget limit for specific Phase 2 command"""
    config = get_phase2_config()

    # Check command-specific overrides
    if command == "predict":
        if limit_type == "tokens":
            return config.budget.predict_trends_max_tokens
        elif limit_type == "cost":
            return config.budget.predict_trends_max_cost_cents

    elif command == "competitors":
        if limit_type == "tokens":
            return config.budget.competitors_max_tokens
        elif limit_type == "cost":
            return config.budget.competitors_max_cost_cents

    elif command == "synthesize":
        if limit_type == "tokens":
            return config.budget.synthesize_max_tokens
        elif limit_type == "cost":
            return config.budget.synthesize_max_cost_cents

    # Fallback to default
    if limit_type == "tokens":
        return config.budget.max_tokens_per_command
    elif limit_type == "cost":
        return config.budget.max_cost_cents_per_command

    return 0


def get_ab_test_arm(user_id: str, experiment: str) -> Literal["A", "B"]:
    """
    Assign user to A/B test arm (deterministic hash-based)

    Args:
        user_id: User identifier
        experiment: Experiment name

    Returns:
        "A" or "B"
    """
    # Simple hash-based assignment
    hash_value = hash(f"{user_id}:{experiment}")
    return "A" if hash_value % 2 == 0 else "B"


def get_ab_test_config_override(experiment: str, arm: Literal["A", "B"]) -> Dict[str, any]:
    """Get A/B test config override for experiment arm"""
    config = get_phase2_config()
    overrides = config.ab_test.arm_overrides.get(experiment, {})
    return overrides.get(arm, {})
