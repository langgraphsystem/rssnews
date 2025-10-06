"""
Metrics Module for /ask Command
Tracks intent routing, retrieval quality, and performance
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter
import threading

logger = logging.getLogger(__name__)


@dataclass
class MetricCounter:
    """Simple counter metric"""
    name: str
    value: int = 0
    labels: Dict[str, str] = field(default_factory=dict)

    def increment(self, amount: int = 1):
        """Increment counter"""
        self.value += amount

    def reset(self):
        """Reset counter to 0"""
        self.value = 0


@dataclass
class MetricHistogram:
    """Histogram metric for tracking distributions"""
    name: str
    values: List[float] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    def observe(self, value: float):
        """Record a value"""
        self.values.append(value)

    def get_percentile(self, percentile: float) -> Optional[float]:
        """Get percentile value (0-100)"""
        if not self.values:
            return None
        sorted_values = sorted(self.values)
        index = int(len(sorted_values) * (percentile / 100.0))
        return sorted_values[min(index, len(sorted_values) - 1)]

    def get_mean(self) -> Optional[float]:
        """Get mean value"""
        if not self.values:
            return None
        return sum(self.values) / len(self.values)

    def get_count(self) -> int:
        """Get count of observations"""
        return len(self.values)

    def reset(self):
        """Reset histogram"""
        self.values = []


class AskMetricsCollector:
    """Centralized metrics collector for /ask command"""

    def __init__(self):
        self._lock = threading.Lock()

        # Intent routing metrics
        self.intent_general_qa_total = MetricCounter("ask_intent_general_qa_total")
        self.intent_news_total = MetricCounter("ask_intent_news_total")
        self.intent_confidence_histogram = MetricHistogram("ask_intent_confidence")

        # Retrieval metrics
        self.retrieval_bypassed_total = MetricCounter("ask_retrieval_bypassed_total")
        self.retrieval_executed_total = MetricCounter("ask_retrieval_executed_total")
        self.retrieval_empty_results_total = MetricCounter("ask_retrieval_empty_results_total")
        self.retrieval_window_expansion_total = MetricCounter("ask_retrieval_window_expansion_total")

        # Retrieval results distribution
        self.retrieval_results_count_histogram = MetricHistogram("ask_retrieval_results_count")
        self.retrieval_window_histogram = MetricHistogram("ask_retrieval_window_days")

        # Filtering metrics
        self.filter_offtopic_dropped_total = MetricCounter("ask_filter_offtopic_dropped_total")
        self.filter_category_penalty_applied_total = MetricCounter("ask_filter_category_penalty_total")
        self.filter_date_penalty_applied_total = MetricCounter("ask_filter_date_penalty_total")
        self.filter_domain_diversity_dropped_total = MetricCounter("ask_filter_domain_diversity_dropped_total")

        # Deduplication metrics
        self.dedup_duplicates_found_total = MetricCounter("ask_dedup_duplicates_found_total")
        self.dedup_canonical_selected_total = MetricCounter("ask_dedup_canonical_selected_total")
        self.dedup_url_normalized_total = MetricCounter("ask_dedup_url_normalized_total")

        # Query parsing metrics
        self.query_parser_site_operator_total = MetricCounter("ask_query_site_operator_total")
        self.query_parser_after_operator_total = MetricCounter("ask_query_after_operator_total")
        self.query_parser_before_operator_total = MetricCounter("ask_query_before_operator_total")
        self.query_parser_time_window_extracted_total = MetricCounter("ask_query_time_window_extracted_total")

        # Performance metrics
        self.response_time_histogram = MetricHistogram("ask_response_time_seconds")
        self.llm_calls_total = MetricCounter("ask_llm_calls_total")
        self.llm_tokens_histogram = MetricHistogram("ask_llm_tokens")

        # Quality metrics
        self.top10_unique_domains_histogram = MetricHistogram("ask_top10_unique_domains")
        self.top10_dated_articles_percentage_histogram = MetricHistogram("ask_top10_dated_articles_percentage")

        # Error tracking
        self.errors_total = MetricCounter("ask_errors_total")
        self.errors_by_type: Dict[str, MetricCounter] = defaultdict(
            lambda: MetricCounter("ask_errors_by_type")
        )

        # Session tracking
        self.session_start_time = datetime.utcnow()
        self.total_queries = 0

    # ==========================================================================
    # INTENT ROUTING METRICS
    # ==========================================================================

    def record_intent_classification(self, intent: str, confidence: float):
        """Record intent classification result"""
        with self._lock:
            if intent == "general_qa":
                self.intent_general_qa_total.increment()
            elif intent == "news_current_events":
                self.intent_news_total.increment()

            self.intent_confidence_histogram.observe(confidence)
            logger.debug(f"Metrics: Intent={intent}, confidence={confidence:.2f}")

    # ==========================================================================
    # RETRIEVAL METRICS
    # ==========================================================================

    def record_retrieval_bypassed(self):
        """Record that retrieval was bypassed (general-QA mode)"""
        with self._lock:
            self.retrieval_bypassed_total.increment()
            logger.debug("Metrics: Retrieval bypassed (general-QA)")

    def record_retrieval_executed(self, window: str, results_count: int):
        """Record retrieval execution"""
        with self._lock:
            self.retrieval_executed_total.increment()
            self.retrieval_results_count_histogram.observe(results_count)

            # Convert window to days for histogram
            window_days = self._window_to_days(window)
            if window_days:
                self.retrieval_window_histogram.observe(window_days)

            if results_count == 0:
                self.retrieval_empty_results_total.increment()

            logger.debug(f"Metrics: Retrieval executed window={window}, results={results_count}")

    def record_window_expansion(self, original_window: str, expanded_window: str):
        """Record window expansion event"""
        with self._lock:
            self.retrieval_window_expansion_total.increment()
            logger.info(f"Metrics: Window expansion {original_window} → {expanded_window}")

    # ==========================================================================
    # FILTERING METRICS
    # ==========================================================================

    def record_offtopic_filtering(self, dropped_count: int):
        """Record off-topic articles dropped"""
        with self._lock:
            self.filter_offtopic_dropped_total.increment(dropped_count)
            logger.debug(f"Metrics: Off-topic filtering dropped {dropped_count} articles")

    def record_category_penalty(self, category: str):
        """Record category penalty application"""
        with self._lock:
            self.filter_category_penalty_applied_total.increment()
            logger.debug(f"Metrics: Category penalty applied: {category}")

    def record_date_penalty(self):
        """Record date penalty application"""
        with self._lock:
            self.filter_date_penalty_applied_total.increment()

    def record_domain_diversity_filtering(self, dropped_count: int):
        """Record domain diversity filtering"""
        with self._lock:
            self.filter_domain_diversity_dropped_total.increment(dropped_count)
            logger.debug(f"Metrics: Domain diversity dropped {dropped_count} articles")

    # ==========================================================================
    # DEDUPLICATION METRICS
    # ==========================================================================

    def record_deduplication(self, original_count: int, deduplicated_count: int):
        """Record deduplication results"""
        with self._lock:
            duplicates_found = original_count - deduplicated_count
            self.dedup_duplicates_found_total.increment(duplicates_found)
            self.dedup_canonical_selected_total.increment(deduplicated_count)
            logger.debug(f"Metrics: Dedup {original_count} → {deduplicated_count} "
                        f"(removed {duplicates_found})")

    def record_url_normalization(self):
        """Record URL normalization event"""
        with self._lock:
            self.dedup_url_normalized_total.increment()

    # ==========================================================================
    # QUERY PARSING METRICS
    # ==========================================================================

    def record_search_operator(self, operator: str):
        """Record search operator usage"""
        with self._lock:
            if operator == "site":
                self.query_parser_site_operator_total.increment()
            elif operator == "after":
                self.query_parser_after_operator_total.increment()
            elif operator == "before":
                self.query_parser_before_operator_total.increment()

            logger.debug(f"Metrics: Search operator used: {operator}:")

    def record_time_window_extraction(self, window: str):
        """Record time window extraction from query"""
        with self._lock:
            self.query_parser_time_window_extracted_total.increment()
            logger.debug(f"Metrics: Time window extracted: {window}")

    # ==========================================================================
    # PERFORMANCE METRICS
    # ==========================================================================

    def record_response_time(self, duration_seconds: float):
        """Record response time"""
        with self._lock:
            self.response_time_histogram.observe(duration_seconds)
            logger.debug(f"Metrics: Response time {duration_seconds:.2f}s")

    def record_llm_call(self, tokens: int):
        """Record LLM call"""
        with self._lock:
            self.llm_calls_total.increment()
            self.llm_tokens_histogram.observe(tokens)
            logger.debug(f"Metrics: LLM call {tokens} tokens")

    # ==========================================================================
    # QUALITY METRICS
    # ==========================================================================

    def record_top10_diversity(self, unique_domains: int, dated_articles_count: int,
                                total_articles: int):
        """Record diversity metrics for top-10 results"""
        with self._lock:
            self.top10_unique_domains_histogram.observe(unique_domains)

            if total_articles > 0:
                dated_percentage = (dated_articles_count / total_articles) * 100
                self.top10_dated_articles_percentage_histogram.observe(dated_percentage)

            logger.debug(f"Metrics: Top-10 diversity: {unique_domains} domains, "
                        f"{dated_articles_count}/{total_articles} dated")

    # ==========================================================================
    # ERROR TRACKING
    # ==========================================================================

    def record_error(self, error_type: str, error_message: str):
        """Record error occurrence"""
        with self._lock:
            self.errors_total.increment()
            self.errors_by_type[error_type].increment()
            logger.warning(f"Metrics: Error recorded: {error_type} - {error_message}")

    # ==========================================================================
    # REPORTING
    # ==========================================================================

    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        with self._lock:
            uptime_seconds = (datetime.utcnow() - self.session_start_time).total_seconds()

            return {
                "session": {
                    "uptime_seconds": uptime_seconds,
                    "total_queries": self.total_queries,
                },
                "intent_routing": {
                    "general_qa_total": self.intent_general_qa_total.value,
                    "news_total": self.intent_news_total.value,
                    "avg_confidence": self.intent_confidence_histogram.get_mean(),
                },
                "retrieval": {
                    "bypassed_total": self.retrieval_bypassed_total.value,
                    "executed_total": self.retrieval_executed_total.value,
                    "empty_results_total": self.retrieval_empty_results_total.value,
                    "window_expansion_total": self.retrieval_window_expansion_total.value,
                    "avg_results_count": self.retrieval_results_count_histogram.get_mean(),
                    "avg_window_days": self.retrieval_window_histogram.get_mean(),
                },
                "filtering": {
                    "offtopic_dropped_total": self.filter_offtopic_dropped_total.value,
                    "category_penalty_total": self.filter_category_penalty_applied_total.value,
                    "date_penalty_total": self.filter_date_penalty_applied_total.value,
                    "domain_diversity_dropped_total": self.filter_domain_diversity_dropped_total.value,
                },
                "deduplication": {
                    "duplicates_found_total": self.dedup_duplicates_found_total.value,
                    "canonical_selected_total": self.dedup_canonical_selected_total.value,
                    "url_normalized_total": self.dedup_url_normalized_total.value,
                },
                "query_parsing": {
                    "site_operator_total": self.query_parser_site_operator_total.value,
                    "after_operator_total": self.query_parser_after_operator_total.value,
                    "before_operator_total": self.query_parser_before_operator_total.value,
                    "time_window_extracted_total": self.query_parser_time_window_extracted_total.value,
                },
                "performance": {
                    "avg_response_time_seconds": self.response_time_histogram.get_mean(),
                    "p50_response_time_seconds": self.response_time_histogram.get_percentile(50),
                    "p95_response_time_seconds": self.response_time_histogram.get_percentile(95),
                    "p99_response_time_seconds": self.response_time_histogram.get_percentile(99),
                    "llm_calls_total": self.llm_calls_total.value,
                    "avg_llm_tokens": self.llm_tokens_histogram.get_mean(),
                },
                "quality": {
                    "avg_top10_unique_domains": self.top10_unique_domains_histogram.get_mean(),
                    "avg_top10_dated_percentage": self.top10_dated_articles_percentage_histogram.get_mean(),
                },
                "errors": {
                    "total": self.errors_total.value,
                    "by_type": {k: v.value for k, v in self.errors_by_type.items()},
                },
            }

    def reset_all(self):
        """Reset all metrics"""
        with self._lock:
            # Reset all counters
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                if isinstance(attr, (MetricCounter, MetricHistogram)):
                    attr.reset()

            # Reset session
            self.session_start_time = datetime.utcnow()
            self.total_queries = 0
            self.errors_by_type.clear()

            logger.info("Metrics: All metrics reset")

    # ==========================================================================
    # HELPERS
    # ==========================================================================

    def _window_to_days(self, window: str) -> Optional[float]:
        """Convert window string to days"""
        window = window.lower().strip()

        # Hour windows
        if window.endswith('h'):
            try:
                hours = int(window[:-1])
                return hours / 24.0
            except:
                return None

        # Day windows
        if window.endswith('d'):
            try:
                return float(window[:-1])
            except:
                return None

        # Week windows
        if window.endswith('w'):
            try:
                weeks = int(window[:-1])
                return weeks * 7.0
            except:
                return None

        # Month windows (approximate)
        if window.endswith('m'):
            try:
                months = int(window[:-1])
                return months * 30.0
            except:
                return None

        # Year windows
        if window.endswith('y'):
            try:
                years = int(window[:-1])
                return years * 365.0
            except:
                return None

        return None


# Global singleton instance
_metrics_collector: Optional[AskMetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> AskMetricsCollector:
    """Get global metrics collector instance"""
    global _metrics_collector

    if _metrics_collector is None:
        with _metrics_lock:
            if _metrics_collector is None:
                _metrics_collector = AskMetricsCollector()
                logger.info("AskMetricsCollector initialized")

    return _metrics_collector


def reset_metrics():
    """Reset all metrics"""
    collector = get_metrics_collector()
    collector.reset_all()
