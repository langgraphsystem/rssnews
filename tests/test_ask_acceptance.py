"""
Acceptance Tests for /ask Command Enhancement
Tests 5 key scenarios: S1-S5 from implementation plan
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Import modules under test
from core.routing.intent_router import get_intent_router
from core.rag.query_parser import get_query_parser
from core.metrics import get_metrics_collector, reset_metrics
from core.config import get_ask_config


class TestS1_IntentRouting:
    """
    S1: Intent routing correctly classifies general-QA vs news queries
    """

    def setup_method(self):
        """Reset metrics before each test"""
        reset_metrics()

    def test_general_qa_patterns(self):
        """Test general knowledge questions are classified as general_qa"""
        router = get_intent_router()

        # Test cases
        general_qa_queries = [
            "what is the difference between LLM and neural network?",
            "how does quantum computing work?",
            "why is the sky blue?",
            "explain the concept of recursion",
            "define machine learning",
            "what are the main differences between Python and JavaScript?",
        ]

        for query in general_qa_queries:
            result = router.classify(query)
            assert result.intent == "general_qa", \
                f"Query '{query}' should be general_qa, got {result.intent}"
            assert result.confidence >= 0.8, \
                f"Confidence for '{query}' should be >= 0.8, got {result.confidence}"

    def test_news_patterns(self):
        """Test news queries are classified as news_current_events"""
        router = get_intent_router()

        news_queries = [
            "Israel ceasefire talks today",
            "latest AI regulation updates",
            "what happened in Ukraine yesterday?",
            "EU policy changes this week",
            "Trump latest news",
            "Bitcoin price update",
        ]

        for query in news_queries:
            result = router.classify(query)
            assert result.intent == "news_current_events", \
                f"Query '{query}' should be news_current_events, got {result.intent}"
            assert result.confidence >= 0.6, \
                f"Confidence for '{query}' should be >= 0.6, got {result.confidence}"

    def test_search_operators_force_news(self):
        """Test search operators always force news mode"""
        router = get_intent_router()

        operator_queries = [
            "AI regulation site:europa.eu",
            "climate change after:2025-01-01",
            "elections before:2025-12-31",
            "what is LLM site:nytimes.com",  # Even with QA pattern
        ]

        for query in operator_queries:
            result = router.classify(query)
            assert result.intent == "news_current_events", \
                f"Query '{query}' with operators should be news, got {result.intent}"
            assert result.confidence == 1.0, \
                f"Operator queries should have confidence=1.0, got {result.confidence}"

    def test_metrics_recorded(self):
        """Test that metrics are recorded for classifications"""
        router = get_intent_router()
        metrics = get_metrics_collector()

        # Classify some queries
        router.classify("how does an LLM work?")
        router.classify("Israel news today")
        router.classify("what is AI site:bbc.com")

        summary = metrics.get_summary()

        assert summary["intent_routing"]["general_qa_total"] == 1
        assert summary["intent_routing"]["news_total"] == 2
        assert summary["intent_routing"]["avg_confidence"] > 0


class TestS2_QueryParsing:
    """
    S2: Query parser correctly extracts operators and time windows
    """

    def test_site_operator_extraction(self):
        """Test site: operator extraction and validation"""
        parser = get_query_parser()

        # Valid domains
        result = parser.parse("AI regulation site:europa.eu")
        assert "europa.eu" in result.domains
        assert result.clean_query == "AI regulation"

        # Multiple domains
        result = parser.parse("news site:reuters.com site:bbc.com")
        assert "reuters.com" in result.domains
        assert "bbc.com" in result.domains

        # Invalid domain (not in allow-list)
        result = parser.parse("test site:unknown-domain.xyz")
        assert len(result.domains) == 0  # Filtered out

    def test_after_date_parsing(self):
        """Test after: date operator parsing"""
        parser = get_query_parser()

        # Absolute date
        result = parser.parse("AI news after:2025-01-01")
        assert result.after_date is not None
        assert result.after_date.year == 2025
        assert result.after_date.month == 1
        assert result.after_date.day == 1

        # Relative date
        result = parser.parse("crypto after:3d")
        assert result.after_date is not None
        # Should be ~3 days ago
        expected = datetime.utcnow() - timedelta(days=3)
        assert abs((result.after_date - expected).days) <= 1

    def test_before_date_parsing(self):
        """Test before: date operator parsing"""
        parser = get_query_parser()

        result = parser.parse("elections before:2025-12-31")
        assert result.before_date is not None
        assert result.before_date.year == 2025
        assert result.before_date.month == 12
        assert result.before_date.day == 31

    def test_time_window_extraction(self):
        """Test time window extraction from natural language"""
        parser = get_query_parser()

        test_cases = [
            ("news today", "24h"),
            ("updates yesterday", "24h"),
            ("events this week", "7d"),
            ("сегодня новости", "24h"),  # Russian
        ]

        for query, expected_window in test_cases:
            result = parser.parse(query)
            assert result.time_window == expected_window, \
                f"Query '{query}' should extract '{expected_window}', got {result.time_window}"

    def test_combined_operators(self):
        """Test multiple operators in single query"""
        parser = get_query_parser()

        result = parser.parse(
            "AI regulation site:europa.eu after:2025-01-01 before:2025-02-01"
        )

        assert "europa.eu" in result.domains
        assert result.after_date.year == 2025
        assert result.after_date.month == 1
        assert result.before_date.month == 2
        assert "AI regulation" in result.clean_query


class TestS3_TimeWindowDefaults:
    """
    S3: Default time window is 7d for news, None for general-QA
    """

    def test_news_query_default_window(self):
        """Test news queries default to 7d window"""
        config = get_ask_config()
        assert config.default_time_window == "7d"

    def test_general_qa_no_window(self):
        """Test general-QA bypasses retrieval (no window needed)"""
        router = get_intent_router()

        result = router.classify("what is the difference between AI and ML?")
        assert result.intent == "general_qa"
        # General-QA should not use time window (retrieval bypassed)

    def test_explicit_window_override(self):
        """Test explicit time window overrides default"""
        parser = get_query_parser()

        result = parser.parse("AI news today")  # Should extract 24h
        assert result.time_window == "24h"  # Not default 7d


class TestS4_FilteringQuality:
    """
    S4: Filtering removes off-topic, applies penalties, enforces diversity
    """

    def test_config_filtering_enabled(self):
        """Test filtering is enabled by default"""
        config = get_ask_config()

        assert config.filter_offtopic_enabled is True
        assert config.min_cosine_threshold == 0.28
        assert config.category_penalties_enabled is True
        assert config.date_penalties_enabled is True
        assert config.domain_diversity_enabled is True

    def test_scoring_weights_sum_to_one(self):
        """Test scoring weights are valid"""
        config = get_ask_config()

        total = (
            config.semantic_weight +
            config.fts_weight +
            config.freshness_weight +
            config.source_weight
        )

        assert abs(total - 1.0) < 0.01, \
            f"Scoring weights should sum to 1.0, got {total}"

    def test_domain_diversity_settings(self):
        """Test domain diversity configuration"""
        config = get_ask_config()

        assert config.max_per_domain == 2  # Max 2 per domain in top-10
        assert 0.0 <= config.mmr_lambda <= 1.0  # Valid MMR parameter


class TestS5_AutoRecovery:
    """
    S5: Auto-recovery expands window on empty results
    """

    def test_window_expansion_sequence(self):
        """Test window expansion follows correct sequence"""
        from core.context.phase3_context_builder import WINDOW_EXPANSION

        # Test 7d → 14d → 30d expansion
        assert WINDOW_EXPANSION["7d"] == "14d"
        assert WINDOW_EXPANSION["14d"] == "30d"
        assert WINDOW_EXPANSION["30d"] == "3m"

        # Test equivalents
        assert WINDOW_EXPANSION["1w"] == "14d"  # 1w = 7d
        assert WINDOW_EXPANSION["2w"] == "30d"  # 2w = 14d

    def test_auto_recovery_enabled(self):
        """Test auto-recovery is enabled by default"""
        config = get_ask_config()

        assert config.auto_expand_window is True
        assert config.max_expansion_attempts == 5


class TestS6_MetricsCollection:
    """
    S6: Metrics are collected throughout the pipeline
    """

    def setup_method(self):
        """Reset metrics before each test"""
        reset_metrics()

    def test_metrics_collector_singleton(self):
        """Test metrics collector is singleton"""
        from core.metrics import get_metrics_collector

        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_metrics_summary_structure(self):
        """Test metrics summary has expected structure"""
        metrics = get_metrics_collector()

        summary = metrics.get_summary()

        # Check top-level keys
        assert "session" in summary
        assert "intent_routing" in summary
        assert "retrieval" in summary
        assert "filtering" in summary
        assert "deduplication" in summary
        assert "query_parsing" in summary
        assert "performance" in summary
        assert "quality" in summary
        assert "errors" in summary

    def test_metrics_recorded_during_classification(self):
        """Test metrics are recorded during intent classification"""
        router = get_intent_router()
        metrics = get_metrics_collector()

        # Reset and classify
        reset_metrics()
        router.classify("what is AI?")

        summary = metrics.get_summary()
        assert summary["intent_routing"]["general_qa_total"] == 1

    def test_histogram_percentiles(self):
        """Test histogram can calculate percentiles"""
        from core.metrics.ask_metrics import MetricHistogram

        hist = MetricHistogram("test")

        # Add values
        for i in range(100):
            hist.observe(i)

        # Test percentiles
        p50 = hist.get_percentile(50)
        p95 = hist.get_percentile(95)
        p99 = hist.get_percentile(99)

        assert 45 <= p50 <= 55  # ~50th value
        assert 90 <= p95 <= 99  # ~95th value
        assert 95 <= p99 <= 99  # ~99th value


class TestS7_Configuration:
    """
    S7: Configuration loads from environment and validates
    """

    def test_config_singleton(self):
        """Test config is singleton"""
        config1 = get_ask_config()
        config2 = get_ask_config()

        assert config1 is config2

    def test_config_validation(self):
        """Test config validation works"""
        from core.config.ask_config import AskCommandConfig

        # Valid config
        valid_config = AskCommandConfig()
        assert valid_config.validate() is True

        # Invalid config (weights don't sum to 1)
        invalid_config = AskCommandConfig()
        invalid_config.semantic_weight = 0.8
        invalid_config.fts_weight = 0.8  # Total > 1.0
        assert invalid_config.validate() is False

    def test_config_to_dict(self):
        """Test config can be serialized to dict"""
        config = get_ask_config()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert "time_windows" in config_dict
        assert "retrieval" in config_dict
        assert "scoring_weights" in config_dict


class TestS8_EndToEnd:
    """
    S8: End-to-end integration tests
    """

    def test_general_qa_flow(self):
        """Test complete general-QA flow"""
        # 1. Parse query
        parser = get_query_parser()
        parsed = parser.parse("what is the difference between AI and ML?")

        # 2. Classify intent
        router = get_intent_router()
        intent_result = router.classify(parsed.clean_query)

        # 3. Verify results
        assert intent_result.intent == "general_qa"
        assert parsed.time_window is None  # No time window for general-QA
        assert len(parsed.domains) == 0  # No domain filtering

    def test_news_flow_with_operators(self):
        """Test complete news flow with operators"""
        # 1. Parse query
        parser = get_query_parser()
        parsed = parser.parse("AI regulation site:europa.eu after:2025-01-01")

        # 2. Classify intent
        router = get_intent_router()
        intent_result = router.classify(parsed.original_query)

        # 3. Verify results
        assert intent_result.intent == "news_current_events"
        assert "europa.eu" in parsed.domains
        assert parsed.after_date is not None
        assert parsed.clean_query == "AI regulation"

    def test_metrics_collected_end_to_end(self):
        """Test metrics collected throughout pipeline"""
        reset_metrics()

        # Simulate full flow
        parser = get_query_parser()
        router = get_intent_router()
        metrics = get_metrics_collector()

        # Process multiple queries
        queries = [
            "what is AI?",
            "Israel news site:reuters.com",
            "crypto after:3d",
        ]

        for query in queries:
            parsed = parser.parse(query)
            router.classify(parsed.original_query)

        # Verify metrics
        summary = metrics.get_summary()
        assert summary["intent_routing"]["general_qa_total"] >= 1
        assert summary["intent_routing"]["news_total"] >= 2
        assert summary["query_parsing"]["site_operator_total"] >= 1
        assert summary["query_parsing"]["after_operator_total"] >= 1


# ==========================================================================
# PERFORMANCE BENCHMARKS
# ==========================================================================

class TestPerformance:
    """
    Performance benchmarks for /ask components
    """

    def test_intent_classification_speed(self, benchmark):
        """Benchmark intent classification speed"""
        router = get_intent_router()

        def classify():
            return router.classify("what is the difference between AI and ML?")

        result = benchmark(classify)
        assert result.intent == "general_qa"

    def test_query_parsing_speed(self, benchmark):
        """Benchmark query parsing speed"""
        parser = get_query_parser()

        def parse():
            return parser.parse("AI news site:europa.eu after:2025-01-01")

        result = benchmark(parse)
        assert "europa.eu" in result.domains


# ==========================================================================
# PYTEST CONFIGURATION
# ==========================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment before all tests"""
    import os

    # Set test environment variables
    os.environ["ASK_DEBUG_MODE"] = "true"
    os.environ["ASK_METRICS_ENABLED"] = "true"

    yield

    # Cleanup after tests
    reset_metrics()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
