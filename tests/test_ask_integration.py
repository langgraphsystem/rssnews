"""
Integration Tests for /ask Command Components
Tests interaction between router, parser, config, and metrics
"""

import pytest
from core.routing.intent_router import get_intent_router, IntentRouter
from core.rag.query_parser import get_query_parser, QueryParser
from core.metrics import get_metrics_collector, reset_metrics
from core.config import get_ask_config


class TestIntentRouterIntegration:
    """Test IntentRouter integration with metrics"""

    def setup_method(self):
        reset_metrics()

    def test_router_records_metrics_for_all_paths(self):
        """Test that all classification paths record metrics"""
        router = get_intent_router()
        metrics = get_metrics_collector()

        # Test different classification paths
        test_cases = [
            ("what is AI?", "general_qa"),
            ("Israel news today", "news_current_events"),
            ("test site:bbc.com", "news_current_events"),  # Operators
            ("Trump", "news_current_events"),  # Entity
        ]

        for query, expected_intent in test_cases:
            reset_metrics()
            result = router.classify(query)

            assert result.intent == expected_intent

            # Verify metrics recorded
            summary = metrics.get_summary()
            if expected_intent == "general_qa":
                assert summary["intent_routing"]["general_qa_total"] == 1
            else:
                assert summary["intent_routing"]["news_total"] == 1

            # Confidence should be recorded
            assert summary["intent_routing"]["avg_confidence"] is not None


class TestQueryParserIntegration:
    """Test QueryParser integration with metrics"""

    def setup_method(self):
        reset_metrics()

    def test_parser_records_operator_metrics(self):
        """Test that parser records metrics for operators"""
        parser = get_query_parser()
        metrics = get_metrics_collector()

        # Test site: operator
        reset_metrics()
        result = parser.parse("test site:reuters.com")
        summary = metrics.get_summary()
        assert summary["query_parsing"]["site_operator_total"] == 1

        # Test after: operator
        reset_metrics()
        result = parser.parse("test after:2025-01-01")
        summary = metrics.get_summary()
        assert summary["query_parsing"]["after_operator_total"] == 1

        # Test before: operator
        reset_metrics()
        result = parser.parse("test before:2025-12-31")
        summary = metrics.get_summary()
        assert summary["query_parsing"]["before_operator_total"] == 1

    def test_parser_handles_invalid_domains(self):
        """Test parser gracefully handles invalid domains"""
        parser = get_query_parser()

        result = parser.parse("test site:invalid-domain.xyz")

        # Should return empty domains list (filtered out)
        assert len(result.domains) == 0
        # Clean query should still be extracted
        assert result.clean_query == "test"


class TestRouterParserPipeline:
    """Test complete router + parser pipeline"""

    def test_combined_flow_general_qa(self):
        """Test general-QA query through full pipeline"""
        parser = get_query_parser()
        router = get_intent_router()

        # General-QA query
        query = "what is the difference between AI and ML?"

        # Step 1: Parse
        parsed = parser.parse(query)
        assert parsed.clean_query == query  # No operators
        assert parsed.time_window is None
        assert len(parsed.domains) == 0

        # Step 2: Classify
        intent_result = router.classify(parsed.clean_query)
        assert intent_result.intent == "general_qa"
        assert intent_result.confidence >= 0.8

    def test_combined_flow_news_with_operators(self):
        """Test news query with operators through full pipeline"""
        parser = get_query_parser()
        router = get_intent_router()

        # News query with operators
        query = "AI regulation site:europa.eu after:2025-01-01"

        # Step 1: Parse
        parsed = parser.parse(query)
        assert parsed.clean_query == "AI regulation"
        assert "europa.eu" in parsed.domains
        assert parsed.after_date is not None

        # Step 2: Classify (operators force news mode)
        intent_result = router.classify(query)  # Use original query
        assert intent_result.intent == "news_current_events"
        assert intent_result.confidence == 1.0  # Operators = 100% confidence

    def test_combined_flow_with_time_window(self):
        """Test query with time window extraction"""
        parser = get_query_parser()
        router = get_intent_router()

        # Query with time window keyword
        query = "Israel news today"

        # Step 1: Parse
        parsed = parser.parse(query)
        assert parsed.time_window == "24h"  # "today" → 24h
        assert "Israel news" in parsed.clean_query

        # Step 2: Classify
        intent_result = router.classify(parsed.clean_query)
        assert intent_result.intent == "news_current_events"


class TestConfigIntegration:
    """Test config integration with other components"""

    def test_config_affects_filtering_thresholds(self):
        """Test config provides correct filtering thresholds"""
        config = get_ask_config()

        # Filtering thresholds
        assert config.min_cosine_threshold == 0.28
        assert config.date_penalty_factor == 0.3
        assert config.max_per_domain == 2

        # Auto-recovery settings
        assert config.auto_expand_window is True
        assert config.max_expansion_attempts == 5

    def test_config_scoring_weights_valid(self):
        """Test config scoring weights are valid"""
        config = get_ask_config()

        # Weights should sum to 1.0
        total = (
            config.semantic_weight +
            config.fts_weight +
            config.freshness_weight +
            config.source_weight
        )

        assert abs(total - 1.0) < 0.01

        # Individual weights should be reasonable
        assert 0.3 <= config.semantic_weight <= 0.6
        assert 0.15 <= config.freshness_weight <= 0.3
        assert config.source_weight >= 0.04


class TestMetricsIntegration:
    """Test metrics integration across components"""

    def setup_method(self):
        reset_metrics()

    def test_metrics_track_full_pipeline(self):
        """Test metrics track complete pipeline execution"""
        parser = get_query_parser()
        router = get_intent_router()
        metrics = get_metrics_collector()

        # Execute multiple queries
        queries = [
            "what is AI?",
            "Israel news site:reuters.com",
            "crypto after:3d",
            "Trump latest updates",
        ]

        for query in queries:
            parsed = parser.parse(query)
            router.classify(parsed.original_query)

        # Verify comprehensive metrics
        summary = metrics.get_summary()

        # Intent routing metrics
        assert summary["intent_routing"]["general_qa_total"] >= 1
        assert summary["intent_routing"]["news_total"] >= 3

        # Query parsing metrics
        assert summary["query_parsing"]["site_operator_total"] >= 1
        assert summary["query_parsing"]["after_operator_total"] >= 1

        # Confidence tracking
        assert summary["intent_routing"]["avg_confidence"] > 0.5

    def test_metrics_reset_works(self):
        """Test metrics can be reset"""
        router = get_intent_router()
        metrics = get_metrics_collector()

        # Record some metrics
        router.classify("what is AI?")
        summary1 = metrics.get_summary()
        assert summary1["intent_routing"]["general_qa_total"] == 1

        # Reset
        reset_metrics()
        summary2 = metrics.get_summary()
        assert summary2["intent_routing"]["general_qa_total"] == 0


class TestErrorHandling:
    """Test error handling across components"""

    def test_router_handles_empty_query(self):
        """Test router handles empty query gracefully"""
        router = get_intent_router()

        # Empty query should default to general_qa
        result = router.classify("")
        assert result.intent in ["general_qa", "news_current_events"]
        assert result.confidence > 0

    def test_parser_handles_malformed_dates(self):
        """Test parser handles malformed dates"""
        parser = get_query_parser()

        # Invalid date format
        result = parser.parse("test after:invalid-date")

        # Should not crash, returns None for invalid date
        assert result.after_date is None
        assert result.clean_query == "test"

    def test_parser_handles_malformed_operators(self):
        """Test parser handles malformed operators"""
        parser = get_query_parser()

        # Malformed site: operator
        result = parser.parse("test site:")

        # Should handle gracefully
        assert len(result.domains) == 0
        assert "test" in result.clean_query


class TestSingletonPatterns:
    """Test singleton patterns work correctly"""

    def test_router_singleton(self):
        """Test IntentRouter is singleton"""
        router1 = get_intent_router()
        router2 = get_intent_router()

        assert router1 is router2

    def test_parser_singleton(self):
        """Test QueryParser is singleton"""
        parser1 = get_query_parser()
        parser2 = get_query_parser()

        assert parser1 is parser2

    def test_config_singleton(self):
        """Test Config is singleton"""
        config1 = get_ask_config()
        config2 = get_ask_config()

        assert config1 is config2

    def test_metrics_singleton(self):
        """Test MetricsCollector is singleton"""
        metrics1 = get_metrics_collector()
        metrics2 = get_metrics_collector()

        assert metrics1 is metrics2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
