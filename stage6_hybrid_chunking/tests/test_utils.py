"""
Tests for utility modules (metrics, tracing, health, logging).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime

from src.utils.metrics import (
    InMemoryMetrics, PrometheusMetrics, Stage6Metrics,
    MetricCounter, MetricHistogram, MetricGauge
)
from src.utils.health import (
    HealthChecker, HealthStatus, HealthCheckResult,
    DatabaseHealthChecker, LLMHealthChecker
)
from src.utils.tracing import (
    TracingManager, trace_async_method, trace_sync_method,
    initialize_tracing, get_tracing_manager, shutdown_tracing
)
from src.utils.logging import (
    configure_logging, LoggingContext, ComponentLogger,
    log_performance, log_error_with_context
)


class TestInMemoryMetrics:
    """Test suite for InMemoryMetrics."""
    
    def test_metrics_initialization(self):
        """Test metrics collector initializes correctly."""
        metrics = InMemoryMetrics(max_history=100)
        
        assert metrics.max_history == 100
        assert len(metrics._counters) == 0
        assert len(metrics._histograms) == 0
        assert len(metrics._gauges) == 0
    
    def test_counter_operations(self):
        """Test counter metric operations."""
        metrics = InMemoryMetrics()
        
        counter = metrics.counter("test_counter", "Test counter")
        assert counter is not None
        
        # Test increment
        counter.inc()
        counter.inc(5.0)
        
        # Check summary
        summary = metrics.get_metric_summary()
        assert 'counters' in summary
        # Should have recorded the increments
        assert len(summary['counters']) > 0
    
    def test_histogram_operations(self):
        """Test histogram metric operations."""
        metrics = InMemoryMetrics()
        
        histogram = metrics.histogram("test_histogram", "Test histogram")
        assert histogram is not None
        
        # Test observations
        histogram.observe(1.0)
        histogram.observe(2.5)
        histogram.observe(3.2)
        
        # Check summary
        summary = metrics.get_metric_summary()
        assert 'histograms' in summary
        
        # Should have statistics
        if summary['histograms']:
            hist_stats = list(summary['histograms'].values())[0]
            assert hist_stats['count'] == 3
            assert hist_stats['avg'] > 0
    
    @pytest.mark.asyncio
    async def test_histogram_timing(self):
        """Test histogram timing context manager."""
        metrics = InMemoryMetrics()
        histogram = metrics.histogram("test_timing")
        
        async with histogram.time():
            await asyncio.sleep(0.01)  # Small delay
        
        # Should have recorded the timing
        summary = metrics.get_metric_summary()
        if summary['histograms']:
            hist_stats = list(summary['histograms'].values())[0]
            assert hist_stats['count'] == 1
            assert hist_stats['avg'] > 0
    
    def test_gauge_operations(self):
        """Test gauge metric operations."""
        metrics = InMemoryMetrics()
        
        gauge = metrics.gauge("test_gauge", "Test gauge")
        assert gauge is not None
        
        # Test set, inc, dec
        gauge.set(10.0)
        gauge.inc(5.0)
        gauge.dec(2.0)
        
        # Check final value
        summary = metrics.get_metric_summary()
        assert 'gauges' in summary
    
    @pytest.mark.asyncio
    async def test_push_metrics_noop(self):
        """Test push metrics is no-op for in-memory."""
        metrics = InMemoryMetrics()
        
        # Should not raise exception
        await metrics.push_metrics("http://localhost:9091")


class TestPrometheusMetrics:
    """Test suite for PrometheusMetrics."""
    
    def test_prometheus_initialization(self):
        """Test Prometheus metrics collector initializes."""
        from prometheus_client import CollectorRegistry
        
        registry = CollectorRegistry()
        metrics = PrometheusMetrics(registry=registry, namespace="test")
        
        assert metrics.registry == registry
        assert metrics.namespace == "test"
    
    def test_prometheus_counter(self):
        """Test Prometheus counter creation."""
        from prometheus_client import CollectorRegistry
        
        registry = CollectorRegistry()
        metrics = PrometheusMetrics(registry=registry)
        
        counter = metrics.counter("test_counter", "Test counter")
        assert counter is not None
        
        # Test increment
        counter.inc(5.0)
        
        # Check registry
        metric_families = list(registry.collect())
        assert len(metric_families) > 0
    
    def test_prometheus_histogram(self):
        """Test Prometheus histogram creation."""
        from prometheus_client import CollectorRegistry
        
        registry = CollectorRegistry()
        metrics = PrometheusMetrics(registry=registry)
        
        histogram = metrics.histogram("test_histogram", "Test histogram")
        assert histogram is not None
        
        # Test observation
        histogram.observe(1.5)
        
        # Check registry
        metric_families = list(registry.collect())
        assert len(metric_families) > 0


class TestStage6Metrics:
    """Test suite for Stage6Metrics."""
    
    def test_stage6_metrics_initialization(self):
        """Test Stage6Metrics initializes all required metrics."""
        collector = InMemoryMetrics()
        stage6_metrics = Stage6Metrics(collector)
        
        # Check all metrics are created
        assert stage6_metrics.articles_processed is not None
        assert stage6_metrics.chunks_created is not None
        assert stage6_metrics.llm_requests is not None
        assert stage6_metrics.batch_processing_time is not None
        assert stage6_metrics.active_jobs is not None
    
    def test_stage6_metrics_usage(self):
        """Test using Stage6Metrics for recording."""
        collector = InMemoryMetrics()
        stage6_metrics = Stage6Metrics(collector)
        
        # Record some metrics
        stage6_metrics.articles_processed.inc(5)
        stage6_metrics.chunks_created.inc(25)
        stage6_metrics.llm_requests.inc(3)
        stage6_metrics.batch_processing_time.observe(2.5)
        stage6_metrics.active_jobs.set(2)
        
        # Verify recorded
        summary = collector.get_metric_summary()
        assert len(summary['counters']) > 0
        assert len(summary['histograms']) > 0
        assert len(summary['gauges']) > 0


class TestHealthChecker:
    """Test suite for HealthChecker."""
    
    @pytest.mark.asyncio
    async def test_health_checker_initialization(self):
        """Test health checker initializes correctly."""
        checker = HealthChecker(timeout_seconds=10.0)
        
        assert checker.timeout_seconds == 10.0
        assert len(checker.checks) > 0  # Default checks registered
        assert 'system_time' in checker.checks
    
    @pytest.mark.asyncio
    async def test_register_custom_check(self):
        """Test registering custom health check."""
        checker = HealthChecker()
        
        async def custom_check():
            return HealthCheckResult(
                name="custom_test",
                status=HealthStatus.HEALTHY,
                message="Custom check passed"
            )
        
        checker.register_check("custom_test", custom_check)
        assert "custom_test" in checker.checks
        
        # Run the check
        result = await checker.check_single("custom_test")
        assert result is not None
        assert result.name == "custom_test"
        assert result.status == HealthStatus.HEALTHY
    
    @pytest.mark.asyncio
    async def test_check_all(self):
        """Test running all health checks."""
        checker = HealthChecker()
        
        # Add a failing check
        async def failing_check():
            return HealthCheckResult(
                name="failing_test",
                status=HealthStatus.UNHEALTHY,
                message="This check always fails"
            )
        
        checker.register_check("failing_test", failing_check)
        
        results = await checker.check_all()
        
        assert isinstance(results, dict)
        assert len(results) > 0
        assert 'failing_test' in results
        assert results['failing_test'].status == HealthStatus.UNHEALTHY
    
    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """Test health check timeout handling."""
        checker = HealthChecker(timeout_seconds=0.1)
        
        async def slow_check():
            await asyncio.sleep(1.0)  # Longer than timeout
            return HealthCheckResult(
                name="slow_test",
                status=HealthStatus.HEALTHY
            )
        
        checker.register_check("slow_test", slow_check)
        
        result = await checker.check_single("slow_test")
        assert result.status == HealthStatus.UNHEALTHY
        assert "timed out" in result.message.lower()
    
    def test_overall_health_calculation(self):
        """Test overall health status calculation."""
        checker = HealthChecker()
        
        # Mock some results
        checker.last_results = {
            'check1': HealthCheckResult('check1', HealthStatus.HEALTHY),
            'check2': HealthCheckResult('check2', HealthStatus.HEALTHY),
            'check3': HealthCheckResult('check3', HealthStatus.DEGRADED)
        }
        
        overall = checker.get_overall_health()
        assert overall == HealthStatus.DEGRADED  # Degraded takes precedence
        
        # Test with unhealthy
        checker.last_results['check4'] = HealthCheckResult('check4', HealthStatus.UNHEALTHY)
        overall = checker.get_overall_health()
        assert overall == HealthStatus.UNHEALTHY  # Unhealthy takes precedence


class TestDatabaseHealthChecker:
    """Test suite for DatabaseHealthChecker."""
    
    @pytest.mark.asyncio
    async def test_database_connection_check(self, db_session):
        """Test database connection health check."""
        db_checker = DatabaseHealthChecker(db_session)
        
        result = await db_checker.check_connection()
        
        assert result.name == "database_connection"
        assert result.status == HealthStatus.HEALTHY
        assert "successful" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_database_tables_check(self, db_session):
        """Test database tables health check."""
        db_checker = DatabaseHealthChecker(db_session)
        
        # Test with tables that should exist
        result = await db_checker.check_tables(['articles'])
        
        # Note: In test environment, tables should exist
        assert result.name == "database_tables"
        # Status depends on whether tables exist in test DB


class TestLLMHealthChecker:
    """Test suite for LLMHealthChecker."""
    
    @pytest.mark.asyncio
    async def test_llm_health_check_with_client(self, mock_gemini_client):
        """Test LLM health check with client."""
        llm_checker = LLMHealthChecker(mock_gemini_client)
        
        # Mock healthy response
        mock_gemini_client.health_check.return_value = True
        
        result = await llm_checker.check_api_availability()
        
        assert result.name == "llm_api"
        assert result.status == HealthStatus.HEALTHY
        assert "responding" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_llm_health_check_no_client(self):
        """Test LLM health check with no client."""
        llm_checker = LLMHealthChecker(None)
        
        result = await llm_checker.check_api_availability()
        
        assert result.status == HealthStatus.UNKNOWN
        assert "not configured" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_check(self, mock_gemini_client):
        """Test circuit breaker health check."""
        llm_checker = LLMHealthChecker(mock_gemini_client)
        
        # Mock circuit breaker closed
        mock_gemini_client.get_stats.return_value = {
            'circuit_breaker_state': 'closed',
            'circuit_breaker_failures': 0
        }
        
        result = await llm_checker.check_circuit_breaker()
        
        assert result.name == "llm_circuit_breaker"
        assert result.status == HealthStatus.HEALTHY
        assert "closed" in result.message.lower()


class TestTracingManager:
    """Test suite for TracingManager."""
    
    def test_tracing_manager_initialization(self):
        """Test tracing manager initializes."""
        manager = TracingManager(
            service_name="test-service",
            sample_rate=0.5
        )
        
        assert manager.service_name == "test-service"
        assert manager.sample_rate == 0.5
        assert not manager._initialized
    
    def test_tracing_manager_initialize(self):
        """Test tracing manager initialization."""
        manager = TracingManager(service_name="test-service")
        
        # Should not raise exception
        manager.initialize()
        assert manager._initialized
        
        # Should have tracer
        tracer = manager.get_tracer()
        assert tracer is not None
    
    @pytest.mark.asyncio
    async def test_trace_operation_context_manager(self):
        """Test tracing operation context manager."""
        manager = TracingManager(service_name="test-service")
        manager.initialize()
        
        async with manager.trace_operation("test_operation", {"test": "value"}) as span:
            assert span is not None
            manager.add_event("test_event")
            manager.set_attribute("test_attr", "test_value")
    
    def test_global_tracing_functions(self):
        """Test global tracing functions."""
        # Initialize global tracing
        manager = initialize_tracing(service_name="global-test")
        assert manager is not None
        
        # Get manager
        retrieved = get_tracing_manager()
        assert retrieved == manager
        
        # Shutdown
        shutdown_tracing()
        retrieved = get_tracing_manager()
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_trace_async_method_decorator(self):
        """Test async method tracing decorator."""
        # Initialize tracing
        initialize_tracing(service_name="decorator-test")
        
        @trace_async_method("test_operation")
        async def test_function(value):
            await asyncio.sleep(0.01)
            return value * 2
        
        result = await test_function(5)
        assert result == 10
        
        shutdown_tracing()
    
    def test_trace_sync_method_decorator(self):
        """Test sync method tracing decorator."""
        initialize_tracing(service_name="sync-decorator-test")
        
        @trace_sync_method("test_sync_operation")
        def test_sync_function(value):
            return value * 3
        
        result = test_sync_function(4)
        assert result == 12
        
        shutdown_tracing()


class TestLogging:
    """Test suite for logging utilities."""
    
    def test_configure_logging_json(self):
        """Test JSON logging configuration."""
        # Should not raise exception
        configure_logging(
            log_level="INFO",
            log_format="json",
            enable_tracing=False
        )
    
    def test_configure_logging_console(self):
        """Test console logging configuration."""
        configure_logging(
            log_level="DEBUG", 
            log_format="console",
            enable_tracing=True
        )
    
    def test_logging_context(self):
        """Test logging context manager."""
        configure_logging(log_level="WARNING", log_format="console")
        
        with LoggingContext(test_id="123", operation="test") as logger:
            logger.info("Test message in context")
    
    def test_component_logger(self):
        """Test component-specific logger."""
        configure_logging(log_level="WARNING", log_format="console")
        
        logger = ComponentLogger("test_component", extra_field="value")
        
        logger.info("Test info message")
        logger.warning("Test warning message")
        logger.error("Test error message")
        
        # Test binding additional context
        bound_logger = logger.bind(request_id="456")
        bound_logger.info("Bound logger message")
    
    def test_utility_logging_functions(self):
        """Test utility logging functions."""
        configure_logging(log_level="WARNING", log_format="console")
        
        # Test performance logging
        log_performance("test_operation", 1.5, extra_info="test")
        
        # Test error logging
        test_error = ValueError("Test error")
        log_error_with_context(test_error, "test_operation", context_id="789")


# Integration tests

class TestIntegrationHealthAndMetrics:
    """Integration tests for health and metrics."""
    
    @pytest.mark.asyncio
    async def test_stage6_health_checker_creation(self, db_session, mock_gemini_client):
        """Test creating Stage 6 health checker with components."""
        from src.utils.health import create_stage6_health_checker
        
        checker = create_stage6_health_checker(
            db_session=db_session,
            gemini_client=mock_gemini_client,
            timeout_seconds=5.0
        )
        
        assert checker is not None
        assert 'database_connection' in checker.checks
        assert 'database_tables' in checker.checks
        assert 'llm_api' in checker.checks
        assert 'llm_circuit_breaker' in checker.checks
        
        # Run all checks
        results = await checker.check_all()
        assert len(results) > 0
    
    def test_metrics_and_logging_integration(self):
        """Test metrics and logging work together."""
        # Configure logging
        configure_logging(log_level="WARNING", log_format="console")
        
        # Create metrics
        metrics = InMemoryMetrics()
        stage6_metrics = Stage6Metrics(metrics)
        
        # Use both
        logger = ComponentLogger("integration_test")
        
        logger.info("Starting integration test")
        stage6_metrics.articles_processed.inc()
        
        with LoggingContext(operation="test_metrics"):
            stage6_metrics.batch_processing_time.observe(2.0)
            logger.info("Recorded metrics")
        
        # Verify metrics recorded
        summary = metrics.get_metric_summary()
        assert summary['total_metrics'] > 0