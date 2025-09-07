"""
Metrics collection and monitoring for Stage 6 pipeline.
"""

import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
from collections import defaultdict, deque
from datetime import datetime, timedelta
import asyncio

import structlog
from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry, push_to_gateway
from prometheus_client.core import CollectorRegistry

logger = structlog.get_logger(__name__)


@dataclass
class MetricValue:
    """Represents a metric value with timestamp."""
    value: Union[int, float]
    timestamp: datetime
    labels: Dict[str, str]


class MetricsCollector(ABC):
    """Abstract base class for metrics collection."""
    
    @abstractmethod
    def counter(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> 'MetricCounter':
        """Create or get a counter metric."""
        pass
    
    @abstractmethod
    def histogram(self, name: str, help_text: str = "", buckets: List[float] = None, labels: Dict[str, str] = None) -> 'MetricHistogram':
        """Create or get a histogram metric."""
        pass
    
    @abstractmethod
    def gauge(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> 'MetricGauge':
        """Create or get a gauge metric."""
        pass
    
    @abstractmethod
    async def push_metrics(self, gateway_url: str = None) -> None:
        """Push metrics to monitoring system."""
        pass
    
    @abstractmethod
    def get_metric_summary(self) -> Dict:
        """Get summary of all metrics."""
        pass


class MetricCounter(ABC):
    """Abstract counter metric."""
    
    @abstractmethod
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Increment counter."""
        pass


class MetricHistogram(ABC):
    """Abstract histogram metric."""
    
    @abstractmethod
    def observe(self, value: float, labels: Dict[str, str] = None) -> None:
        """Observe a value."""
        pass
    
    @abstractmethod
    @asynccontextmanager
    async def time(self, labels: Dict[str, str] = None):
        """Time a block of code."""
        pass


class MetricGauge(ABC):
    """Abstract gauge metric."""
    
    @abstractmethod
    def set(self, value: float, labels: Dict[str, str] = None) -> None:
        """Set gauge value."""
        pass
    
    @abstractmethod
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Increment gauge."""
        pass
    
    @abstractmethod
    def dec(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Decrement gauge."""
        pass


class PrometheusCounter(MetricCounter):
    """Prometheus counter implementation."""
    
    def __init__(self, counter: Counter):
        self._counter = counter
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        if labels:
            self._counter.labels(**labels).inc(amount)
        else:
            self._counter.inc(amount)


class PrometheusHistogram(MetricHistogram):
    """Prometheus histogram implementation."""
    
    def __init__(self, histogram: Histogram):
        self._histogram = histogram
    
    def observe(self, value: float, labels: Dict[str, str] = None) -> None:
        if labels:
            self._histogram.labels(**labels).observe(value)
        else:
            self._histogram.observe(value)
    
    @asynccontextmanager
    async def time(self, labels: Dict[str, str] = None):
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.observe(duration, labels)


class PrometheusGauge(MetricGauge):
    """Prometheus gauge implementation."""
    
    def __init__(self, gauge: Gauge):
        self._gauge = gauge
    
    def set(self, value: float, labels: Dict[str, str] = None) -> None:
        if labels:
            self._gauge.labels(**labels).set(value)
        else:
            self._gauge.set(value)
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        if labels:
            self._gauge.labels(**labels).inc(amount)
        else:
            self._gauge.inc(amount)
    
    def dec(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        if labels:
            self._gauge.labels(**labels).dec(amount)
        else:
            self._gauge.dec(amount)


class PrometheusMetrics(MetricsCollector):
    """Prometheus-based metrics collector."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None, namespace: str = "stage6"):
        self.registry = registry or CollectorRegistry()
        self.namespace = namespace
        self._counters: Dict[str, Counter] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._gauges: Dict[str, Gauge] = {}
        
        logger.info("PrometheusMetrics initialized", namespace=namespace)
    
    def counter(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> MetricCounter:
        full_name = f"{self.namespace}_{name}"
        
        if full_name not in self._counters:
            label_names = list(labels.keys()) if labels else []
            self._counters[full_name] = Counter(
                name=full_name,
                documentation=help_text or f"Counter for {name}",
                labelnames=label_names,
                registry=self.registry
            )
        
        return PrometheusCounter(self._counters[full_name])
    
    def histogram(self, name: str, help_text: str = "", buckets: List[float] = None, labels: Dict[str, str] = None) -> MetricHistogram:
        full_name = f"{self.namespace}_{name}"
        
        if full_name not in self._histograms:
            label_names = list(labels.keys()) if labels else []
            self._histograms[full_name] = Histogram(
                name=full_name,
                documentation=help_text or f"Histogram for {name}",
                labelnames=label_names,
                buckets=buckets,
                registry=self.registry
            )
        
        return PrometheusHistogram(self._histograms[full_name])
    
    def gauge(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> MetricGauge:
        full_name = f"{self.namespace}_{name}"
        
        if full_name not in self._gauges:
            label_names = list(labels.keys()) if labels else []
            self._gauges[full_name] = Gauge(
                name=full_name,
                documentation=help_text or f"Gauge for {name}",
                labelnames=label_names,
                registry=self.registry
            )
        
        return PrometheusGauge(self._gauges[full_name])
    
    async def push_metrics(self, gateway_url: str = None) -> None:
        """Push metrics to Prometheus pushgateway."""
        if not gateway_url:
            logger.debug("No push gateway URL provided, skipping push")
            return
        
        try:
            push_to_gateway(gateway_url, job=f"{self.namespace}_stage6", registry=self.registry)
            logger.debug("Metrics pushed to gateway", url=gateway_url)
        except Exception as e:
            logger.error("Failed to push metrics", error=str(e), gateway_url=gateway_url)
    
    def get_metric_summary(self) -> Dict:
        """Get summary of all registered metrics."""
        return {
            'counters': list(self._counters.keys()),
            'histograms': list(self._histograms.keys()),
            'gauges': list(self._gauges.keys()),
            'total_metrics': len(self._counters) + len(self._histograms) + len(self._gauges)
        }


class InMemoryMetrics(MetricsCollector):
    """In-memory metrics collector for testing and development."""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._counters: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._gauges: Dict[str, float] = {}
        self._metric_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        
        logger.info("InMemoryMetrics initialized", max_history=max_history)
    
    def counter(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> MetricCounter:
        return InMemoryCounter(name, self, labels)
    
    def histogram(self, name: str, help_text: str = "", buckets: List[float] = None, labels: Dict[str, str] = None) -> MetricHistogram:
        return InMemoryHistogram(name, self, labels)
    
    def gauge(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> MetricGauge:
        return InMemoryGauge(name, self, labels)
    
    async def push_metrics(self, gateway_url: str = None) -> None:
        """No-op for in-memory metrics."""
        logger.debug("InMemoryMetrics push_metrics called (no-op)")
    
    def get_metric_summary(self) -> Dict:
        """Get summary of all metrics."""
        histogram_stats = {}
        for name, values in self._histograms.items():
            if values:
                histogram_stats[name] = {
                    'count': len(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values)
                }
        
        return {
            'counters': dict(self._counters),
            'histograms': histogram_stats,
            'gauges': dict(self._gauges),
            'total_metrics': len(self._counters) + len(self._histograms) + len(self._gauges)
        }


class InMemoryCounter(MetricCounter):
    """In-memory counter implementation."""
    
    def __init__(self, name: str, collector: InMemoryMetrics, labels: Dict[str, str] = None):
        self.name = name
        self.collector = collector
        self.labels = labels or {}
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        full_labels = {**self.labels, **(labels or {})}
        key = f"{self.name}_{hash(str(sorted(full_labels.items())))}"
        
        self.collector._counters[key] += amount
        self.collector._metric_history[key].append(
            MetricValue(amount, datetime.utcnow(), full_labels)
        )


class InMemoryHistogram(MetricHistogram):
    """In-memory histogram implementation."""
    
    def __init__(self, name: str, collector: InMemoryMetrics, labels: Dict[str, str] = None):
        self.name = name
        self.collector = collector
        self.labels = labels or {}
    
    def observe(self, value: float, labels: Dict[str, str] = None) -> None:
        full_labels = {**self.labels, **(labels or {})}
        key = f"{self.name}_{hash(str(sorted(full_labels.items())))}"
        
        self.collector._histograms[key].append(value)
        self.collector._metric_history[key].append(
            MetricValue(value, datetime.utcnow(), full_labels)
        )
    
    @asynccontextmanager
    async def time(self, labels: Dict[str, str] = None):
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.observe(duration, labels)


class InMemoryGauge(MetricGauge):
    """In-memory gauge implementation."""
    
    def __init__(self, name: str, collector: InMemoryMetrics, labels: Dict[str, str] = None):
        self.name = name
        self.collector = collector
        self.labels = labels or {}
    
    def set(self, value: float, labels: Dict[str, str] = None) -> None:
        full_labels = {**self.labels, **(labels or {})}
        key = f"{self.name}_{hash(str(sorted(full_labels.items())))}"
        
        self.collector._gauges[key] = value
        self.collector._metric_history[key].append(
            MetricValue(value, datetime.utcnow(), full_labels)
        )
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        full_labels = {**self.labels, **(labels or {})}
        key = f"{self.name}_{hash(str(sorted(full_labels.items())))}"
        
        current = self.collector._gauges.get(key, 0.0)
        new_value = current + amount
        self.set(new_value, labels)
    
    def dec(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        self.inc(-amount, labels)


class Stage6Metrics:
    """Pre-configured metrics for Stage 6 pipeline."""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        
        # Pipeline metrics
        self.articles_processed = collector.counter(
            "articles_processed_total",
            "Total number of articles processed"
        )
        
        self.chunks_created = collector.counter(
            "chunks_created_total", 
            "Total number of chunks created"
        )
        
        self.llm_requests = collector.counter(
            "llm_requests_total",
            "Total number of LLM API requests"
        )
        
        self.llm_success = collector.counter(
            "llm_success_total",
            "Total number of successful LLM requests" 
        )
        
        self.processing_errors = collector.counter(
            "processing_errors_total",
            "Total number of processing errors"
        )
        
        # Performance metrics
        self.batch_processing_time = collector.histogram(
            "batch_processing_duration_seconds",
            "Time taken to process batches",
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
        )
        
        self.article_processing_time = collector.histogram(
            "article_processing_duration_seconds", 
            "Time taken to process individual articles",
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
        )
        
        self.llm_response_time = collector.histogram(
            "llm_response_duration_seconds",
            "LLM API response time",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )
        
        self.chunk_size_distribution = collector.histogram(
            "chunk_size_words",
            "Distribution of chunk sizes in words",
            buckets=[50, 100, 200, 300, 400, 500, 600, 800, 1000]
        )
        
        # Resource metrics
        self.active_jobs = collector.gauge(
            "active_jobs",
            "Number of currently active processing jobs"
        )
        
        self.queue_size = collector.gauge(
            "job_queue_size", 
            "Number of jobs in queue"
        )
        
        self.llm_circuit_breaker_state = collector.gauge(
            "llm_circuit_breaker_open",
            "LLM circuit breaker state (1 = open, 0 = closed)"
        )
        
        self.database_connections = collector.gauge(
            "database_connections_active",
            "Number of active database connections"
        )
        
        logger.info("Stage6Metrics initialized")


# Utility functions

async def create_metrics_collector(metrics_type: str = "prometheus", **kwargs) -> MetricsCollector:
    """Create a metrics collector based on configuration."""
    
    if metrics_type == "prometheus":
        return PrometheusMetrics(**kwargs)
    elif metrics_type == "memory":
        return InMemoryMetrics(**kwargs)
    else:
        raise ValueError(f"Unknown metrics type: {metrics_type}")


@asynccontextmanager
async def track_processing_time(histogram: MetricHistogram, labels: Dict[str, str] = None):
    """Context manager to track processing time."""
    async with histogram.time(labels):
        yield