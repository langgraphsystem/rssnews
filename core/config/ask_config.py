"""
Configuration Module for /ask Command
Centralized settings with environment variable support
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AskCommandConfig:
    """Configuration for /ask command behavior"""

    # Time windows
    default_time_window: str = "7d"
    max_time_window: str = "1y"
    allow_custom_windows: bool = True

    # Retrieval settings
    k_final: int = 10
    max_k_final: int = 50
    use_cache: bool = False  # Disabled for fresh results

    # Intent routing
    intent_router_enabled: bool = True
    default_intent: str = "news_current_events"
    confidence_threshold: float = 0.5  # Minimum confidence for routing

    # Query parsing
    query_parser_enabled: bool = True
    search_operators_enabled: bool = True
    validate_domains: bool = True
    max_domains_per_query: int = 5

    # Filtering
    filter_offtopic_enabled: bool = True
    min_cosine_threshold: float = 0.28
    category_penalties_enabled: bool = True
    date_penalties_enabled: bool = True
    date_penalty_factor: float = 0.3

    # Deduplication
    dedup_enabled: bool = True
    use_etld_plus_one: bool = True
    normalize_urls: bool = True
    lsh_threshold: float = 0.7
    num_perm: int = 128

    # Domain diversity
    domain_diversity_enabled: bool = True
    max_per_domain: int = 2
    mmr_lambda: float = 0.7  # Balance relevance vs diversity

    # Auto-recovery
    auto_expand_window: bool = True
    relax_filters_on_empty: bool = True
    fallback_rerank_false_on_empty: bool = True
    max_expansion_attempts: int = 5

    # Scoring weights
    semantic_weight: float = 0.45
    fts_weight: float = 0.30
    freshness_weight: float = 0.20
    source_weight: float = 0.05

    # General-QA mode
    general_qa_model: str = "gpt-5-mini"
    general_qa_max_tokens: int = 500
    general_qa_reasoning_effort: str = "minimal"

    # News mode
    news_mode_depth: int = 3
    news_mode_max_iterations: int = 5
    news_mode_budget_cents: int = 50

    # Performance
    response_timeout_seconds: int = 30
    llm_timeout_seconds: int = 15
    db_timeout_seconds: int = 10

    # Metrics
    metrics_enabled: bool = True
    log_metrics_interval_seconds: int = 300  # Log every 5 minutes

    # Feature flags
    experimental_features_enabled: bool = False
    debug_mode: bool = False

    @classmethod
    def from_env(cls) -> "AskCommandConfig":
        """Load configuration from environment variables"""
        config = cls()

        # Time windows
        config.default_time_window = os.getenv(
            "ASK_DEFAULT_TIME_WINDOW", config.default_time_window
        )
        config.max_time_window = os.getenv(
            "ASK_MAX_TIME_WINDOW", config.max_time_window
        )
        config.allow_custom_windows = _parse_bool(
            os.getenv("ASK_ALLOW_CUSTOM_WINDOWS"), config.allow_custom_windows
        )

        # Retrieval settings
        config.k_final = _parse_int(
            os.getenv("ASK_K_FINAL"), config.k_final
        )
        config.max_k_final = _parse_int(
            os.getenv("ASK_MAX_K_FINAL"), config.max_k_final
        )
        config.use_cache = _parse_bool(
            os.getenv("ASK_USE_CACHE"), config.use_cache
        )

        # Intent routing
        config.intent_router_enabled = _parse_bool(
            os.getenv("ASK_INTENT_ROUTER_ENABLED"), config.intent_router_enabled
        )
        config.confidence_threshold = _parse_float(
            os.getenv("ASK_INTENT_CONFIDENCE_THRESHOLD"), config.confidence_threshold
        )

        # Filtering
        config.filter_offtopic_enabled = _parse_bool(
            os.getenv("ASK_FILTER_OFFTOPIC_ENABLED"), config.filter_offtopic_enabled
        )
        config.min_cosine_threshold = _parse_float(
            os.getenv("ASK_MIN_COSINE_THRESHOLD"), config.min_cosine_threshold
        )
        config.category_penalties_enabled = _parse_bool(
            os.getenv("ASK_CATEGORY_PENALTIES_ENABLED"), config.category_penalties_enabled
        )
        config.date_penalties_enabled = _parse_bool(
            os.getenv("ASK_DATE_PENALTIES_ENABLED"), config.date_penalties_enabled
        )
        config.date_penalty_factor = _parse_float(
            os.getenv("ASK_DATE_PENALTY_FACTOR"), config.date_penalty_factor
        )

        # Domain diversity
        config.domain_diversity_enabled = _parse_bool(
            os.getenv("ASK_DOMAIN_DIVERSITY_ENABLED"), config.domain_diversity_enabled
        )
        config.max_per_domain = _parse_int(
            os.getenv("ASK_MAX_PER_DOMAIN"), config.max_per_domain
        )
        config.mmr_lambda = _parse_float(
            os.getenv("ASK_MMR_LAMBDA"), config.mmr_lambda
        )

        # Auto-recovery
        config.auto_expand_window = _parse_bool(
            os.getenv("ASK_AUTO_EXPAND_WINDOW"), config.auto_expand_window
        )
        config.max_expansion_attempts = _parse_int(
            os.getenv("ASK_MAX_EXPANSION_ATTEMPTS"), config.max_expansion_attempts
        )

        # Scoring weights
        config.semantic_weight = _parse_float(
            os.getenv("ASK_SEMANTIC_WEIGHT"), config.semantic_weight
        )
        config.fts_weight = _parse_float(
            os.getenv("ASK_FTS_WEIGHT"), config.fts_weight
        )
        config.freshness_weight = _parse_float(
            os.getenv("ASK_FRESHNESS_WEIGHT"), config.freshness_weight
        )
        config.source_weight = _parse_float(
            os.getenv("ASK_SOURCE_WEIGHT"), config.source_weight
        )

        # General-QA mode
        config.general_qa_model = os.getenv(
            "ASK_GENERAL_QA_MODEL", config.general_qa_model
        )
        config.general_qa_max_tokens = _parse_int(
            os.getenv("ASK_GENERAL_QA_MAX_TOKENS"), config.general_qa_max_tokens
        )

        # Metrics
        config.metrics_enabled = _parse_bool(
            os.getenv("ASK_METRICS_ENABLED"), config.metrics_enabled
        )
        config.log_metrics_interval_seconds = _parse_int(
            os.getenv("ASK_LOG_METRICS_INTERVAL"), config.log_metrics_interval_seconds
        )

        # Feature flags
        config.experimental_features_enabled = _parse_bool(
            os.getenv("ASK_EXPERIMENTAL_FEATURES"), config.experimental_features_enabled
        )
        config.debug_mode = _parse_bool(
            os.getenv("ASK_DEBUG_MODE"), config.debug_mode
        )

        logger.info(f"AskCommandConfig loaded from environment: "
                   f"window={config.default_time_window}, "
                   f"k_final={config.k_final}, "
                   f"intent_router={config.intent_router_enabled}")

        return config

    def validate(self) -> bool:
        """Validate configuration values"""
        errors = []

        # Validate k_final
        if self.k_final <= 0 or self.k_final > self.max_k_final:
            errors.append(f"k_final must be between 1 and {self.max_k_final}, got {self.k_final}")

        # Validate weights sum to 1.0
        total_weight = (
            self.semantic_weight + self.fts_weight +
            self.freshness_weight + self.source_weight
        )
        if abs(total_weight - 1.0) > 0.01:
            errors.append(f"Scoring weights must sum to 1.0, got {total_weight:.3f}")

        # Validate thresholds
        if not (0.0 <= self.min_cosine_threshold <= 1.0):
            errors.append(f"min_cosine_threshold must be 0-1, got {self.min_cosine_threshold}")

        if not (0.0 <= self.confidence_threshold <= 1.0):
            errors.append(f"confidence_threshold must be 0-1, got {self.confidence_threshold}")

        if not (0.0 <= self.mmr_lambda <= 1.0):
            errors.append(f"mmr_lambda must be 0-1, got {self.mmr_lambda}")

        # Validate date penalty factor
        if not (0.0 < self.date_penalty_factor <= 1.0):
            errors.append(f"date_penalty_factor must be 0-1, got {self.date_penalty_factor}")

        if errors:
            for error in errors:
                logger.error(f"Config validation error: {error}")
            return False

        return True

    def to_dict(self) -> dict:
        """Convert config to dictionary"""
        return {
            "time_windows": {
                "default": self.default_time_window,
                "max": self.max_time_window,
                "allow_custom": self.allow_custom_windows,
            },
            "retrieval": {
                "k_final": self.k_final,
                "max_k_final": self.max_k_final,
                "use_cache": self.use_cache,
            },
            "intent_routing": {
                "enabled": self.intent_router_enabled,
                "default_intent": self.default_intent,
                "confidence_threshold": self.confidence_threshold,
            },
            "filtering": {
                "offtopic_enabled": self.filter_offtopic_enabled,
                "min_cosine_threshold": self.min_cosine_threshold,
                "category_penalties_enabled": self.category_penalties_enabled,
                "date_penalties_enabled": self.date_penalties_enabled,
                "date_penalty_factor": self.date_penalty_factor,
            },
            "deduplication": {
                "enabled": self.dedup_enabled,
                "use_etld_plus_one": self.use_etld_plus_one,
                "normalize_urls": self.normalize_urls,
                "lsh_threshold": self.lsh_threshold,
            },
            "domain_diversity": {
                "enabled": self.domain_diversity_enabled,
                "max_per_domain": self.max_per_domain,
                "mmr_lambda": self.mmr_lambda,
            },
            "auto_recovery": {
                "auto_expand_window": self.auto_expand_window,
                "relax_filters_on_empty": self.relax_filters_on_empty,
                "max_expansion_attempts": self.max_expansion_attempts,
            },
            "scoring_weights": {
                "semantic": self.semantic_weight,
                "fts": self.fts_weight,
                "freshness": self.freshness_weight,
                "source": self.source_weight,
            },
            "general_qa": {
                "model": self.general_qa_model,
                "max_tokens": self.general_qa_max_tokens,
                "reasoning_effort": self.general_qa_reasoning_effort,
            },
            "performance": {
                "response_timeout_seconds": self.response_timeout_seconds,
                "llm_timeout_seconds": self.llm_timeout_seconds,
                "db_timeout_seconds": self.db_timeout_seconds,
            },
            "feature_flags": {
                "metrics_enabled": self.metrics_enabled,
                "experimental_features": self.experimental_features_enabled,
                "debug_mode": self.debug_mode,
            },
        }


# ==========================================================================
# HELPER FUNCTIONS
# ==========================================================================

def _parse_bool(value: Optional[str], default: bool) -> bool:
    """Parse boolean from environment variable"""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on", "enabled")


def _parse_int(value: Optional[str], default: int) -> int:
    """Parse integer from environment variable"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid integer value: {value}, using default {default}")
        return default


def _parse_float(value: Optional[str], default: float) -> float:
    """Parse float from environment variable"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid float value: {value}, using default {default}")
        return default


# ==========================================================================
# GLOBAL CONFIG INSTANCE
# ==========================================================================

_config: Optional[AskCommandConfig] = None


def get_ask_config() -> AskCommandConfig:
    """Get global ask config instance (singleton)"""
    global _config

    if _config is None:
        _config = AskCommandConfig.from_env()

        if not _config.validate():
            logger.error("Configuration validation failed, using defaults")
            _config = AskCommandConfig()  # Fallback to defaults

    return _config


def reload_config():
    """Reload configuration from environment"""
    global _config
    _config = None
    return get_ask_config()
