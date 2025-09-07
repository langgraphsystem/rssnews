"""
Production-grade Monitoring, Metrics, and Alerting System
Comprehensive observability with Prometheus, Grafana integration, and intelligent alerting.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMING = "timing"
    RATE = "rate"


class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(Enum):
    """Alert status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class Metric:
    """Individual metric data point"""
    name: str
    value: Union[int, float]
    metric_type: MetricType
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_prometheus_format(self) -> str:
        """Convert to Prometheus format"""
        tag_str = ""
        if self.tags:
            tag_pairs = [f'{k}="{v}"' for k, v in self.tags.items()]
            tag_str = f"{{{','.join(tag_pairs)}}}"
        
        return f"{self.name}{tag_str} {self.value} {int(self.timestamp.timestamp() * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'value': self.value,
            'type': self.metric_type.value,
            'tags': self.tags,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class Alert:
    """Alert definition and state"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    metric_name: str
    condition: str  # e.g., "> 100", "< 0.95"
    threshold_value: float
    duration_minutes: int = 5  # Alert after condition persists for this long
    
    # State tracking
    first_triggered: Optional[datetime] = None
    last_triggered: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    trigger_count: int = 0
    
    # Configuration
    enabled: bool = True
    tags: Dict[str, str] = field(default_factory=dict)
    notification_channels: List[str] = field(default_factory=list)
    
    def should_trigger(self, current_value: float) -> bool:
        """Check if alert should trigger based on current value"""
        if not self.enabled or self.status == AlertStatus.SUPPRESSED:
            return False
        
        # Parse condition
        if self.condition.startswith('>'):
            threshold = float(self.condition[1:].strip())
            return current_value > threshold
        elif self.condition.startswith('<'):
            threshold = float(self.condition[1:].strip())
            return current_value < threshold
        elif self.condition.startswith('>='):
            threshold = float(self.condition[2:].strip())
            return current_value >= threshold
        elif self.condition.startswith('<='):
            threshold = float(self.condition[2:].strip())
            return current_value <= threshold
        elif self.condition.startswith('=='):
            threshold = float(self.condition[2:].strip())
            return abs(current_value - threshold) < 0.0001
        else:
            return False
    
    def trigger(self):
        """Trigger the alert"""
        now = datetime.utcnow()
        if not self.first_triggered:
            self.first_triggered = now
        
        self.last_triggered = now
        self.trigger_count += 1
        self.status = AlertStatus.ACTIVE
        self.resolved_at = None
    
    def resolve(self):
        """Resolve the alert"""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.utcnow()
    
    def suppress(self):
        """Suppress the alert"""
        self.status = AlertStatus.SUPPRESSED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'severity': self.severity.value,
            'status': self.status.value,
            'metric_name': self.metric_name,
            'condition': self.condition,
            'threshold_value': self.threshold_value,
            'duration_minutes': self.duration_minutes,
            'first_triggered': self.first_triggered.isoformat() if self.first_triggered else None,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'trigger_count': self.trigger_count,
            'enabled': self.enabled,
            'tags': self.tags,
            'notification_channels': self.notification_channels
        }


class Timer:
    """Context manager for timing operations"""
    
    def __init__(self, metrics_collector: 'MetricsCollector', metric_name: str, tags: Dict[str, str] = None):
        self.metrics = metrics_collector
        self.metric_name = metric_name
        self.tags = tags or {}
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_async()
    
    def stop(self):
        """Stop the timer and record metric synchronously"""
        if self.start_time:
            self.end_time = time.time()
            duration = self.end_time - self.start_time
            # For sync usage, we can't await, so we'll store it for later processing
            self.metrics._pending_timings.append((self.metric_name, duration, self.tags))
    
    async def stop_async(self):
        """Stop the timer and record metric asynchronously"""
        if self.start_time:
            self.end_time = time.time()
            duration = self.end_time - self.start_time
            await self.metrics.timing(self.metric_name, duration, self.tags)
    
    @property
    def elapsed(self) -> Optional[float]:
        """Get elapsed time"""
        if self.start_time:
            end = self.end_time or time.time()
            return end - self.start_time
        return None


class MetricsCollector:
    """
    High-performance metrics collection system with multiple backends:
    - In-memory for real-time dashboards
    - Redis for distributed collection
    - PostgreSQL for long-term storage
    - Prometheus exposition endpoint
    """
    
    def __init__(self,
                 redis_client: Optional[redis.Redis] = None,
                 db_pool: Optional[asyncpg.Pool] = None,
                 buffer_size: int = 1000,
                 flush_interval_seconds: int = 30):
        self.redis = redis_client
        self.db_pool = db_pool
        self.buffer_size = buffer_size
        self.flush_interval_seconds = flush_interval_seconds
        
        # In-memory metric storage
        self._metrics_buffer: List[Metric] = []
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._rates: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # For sync timing operations
        self._pending_timings: List[tuple] = []
        
        # Background tasks
        self._flush_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Performance tracking
        self._last_flush = time.time()
        self._metrics_collected = 0
        self._flush_errors = 0
    
    async def initialize(self):
        """Initialize the metrics collector"""
        # Start background tasks
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Metrics collector initialized")
    
    async def shutdown(self):
        """Shutdown the metrics collector"""
        # Cancel background tasks
        if self._flush_task:
            self._flush_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Final flush
        await self._flush_metrics()
        
        logger.info("Metrics collector shutdown")
    
    async def increment(self, name: str, value: float = 1.0, tags: Dict[str, str] = None):
        """Increment a counter metric"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            tags=tags or {}
        )
        
        # Update in-memory counter
        key = self._make_metric_key(name, tags)
        self._counters[key] += value
        
        await self._record_metric(metric)
    
    async def gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Set a gauge metric"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            tags=tags or {}
        )
        
        # Update in-memory gauge
        key = self._make_metric_key(name, tags)
        self._gauges[key] = value
        
        await self._record_metric(metric)
    
    async def histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record a histogram metric"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            tags=tags or {}
        )
        
        # Update in-memory histogram
        key = self._make_metric_key(name, tags)
        self._histograms[key].append((time.time(), value))
        
        await self._record_metric(metric)
    
    async def timing(self, name: str, duration_seconds: float, tags: Dict[str, str] = None):
        """Record a timing metric"""
        metric = Metric(
            name=name,
            value=duration_seconds,
            metric_type=MetricType.TIMING,
            tags=tags or {}
        )
        
        await self._record_metric(metric)
        await self.histogram(f"{name}.duration", duration_seconds, tags)
    
    async def rate(self, name: str, value: float = 1.0, tags: Dict[str, str] = None):
        """Record a rate metric"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.RATE,
            tags=tags or {}
        )
        
        # Update in-memory rate tracking
        key = self._make_metric_key(name, tags)
        self._rates[key].append((time.time(), value))
        
        await self._record_metric(metric)
    
    def timer(self, name: str, tags: Dict[str, str] = None) -> Timer:
        """Create a timer context manager"""
        return Timer(self, name, tags)
    
    async def _record_metric(self, metric: Metric):
        """Record a metric in the buffer"""
        self._metrics_buffer.append(metric)
        self._metrics_collected += 1
        
        # Flush if buffer is full
        if len(self._metrics_buffer) >= self.buffer_size:
            await self._flush_metrics()
    
    async def _flush_metrics(self):
        """Flush metrics to storage backends"""
        if not self._metrics_buffer and not self._pending_timings:
            return
        
        start_time = time.time()
        
        try:
            # Process pending timings from sync operations
            for metric_name, duration, tags in self._pending_timings:
                await self.timing(metric_name, duration, tags)
            self._pending_timings.clear()
            
            # Get current buffer
            metrics_to_flush = self._metrics_buffer.copy()
            self._metrics_buffer.clear()
            
            # Flush to Redis if available
            if self.redis:
                await self._flush_to_redis(metrics_to_flush)
            
            # Flush to PostgreSQL if available
            if self.db_pool:
                await self._flush_to_postgres(metrics_to_flush)
            
            self._last_flush = time.time()
            
        except Exception as e:
            logger.error(f"Failed to flush metrics: {e}", exc_info=True)
            self._flush_errors += 1
            
            # Put metrics back in buffer if flush failed
            self._metrics_buffer = metrics_to_flush + self._metrics_buffer
        
        flush_duration = time.time() - start_time
        logger.debug(f"Flushed {len(metrics_to_flush)} metrics in {flush_duration:.3f}s")
    
    async def _flush_to_redis(self, metrics: List[Metric]):
        """Flush metrics to Redis"""
        if not metrics:
            return
        
        try:
            pipe = self.redis.pipeline()
            
            for metric in metrics:
                # Store in time-series format
                key = f"metrics:{metric.name}"
                timestamp = int(metric.timestamp.timestamp())
                
                # Store the metric value with timestamp
                pipe.zadd(
                    key,
                    {json.dumps(metric.to_dict()): timestamp}
                )
                
                # Set expiration (keep metrics for 24 hours in Redis)
                pipe.expire(key, 86400)
                
                # Store latest value for quick access
                latest_key = f"metrics:latest:{metric.name}"
                pipe.hset(latest_key, mapping={
                    'value': metric.value,
                    'timestamp': timestamp,
                    'tags': json.dumps(metric.tags)
                })
                pipe.expire(latest_key, 3600)  # Keep latest values for 1 hour
            
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to flush metrics to Redis: {e}")
            raise
    
    async def _flush_to_postgres(self, metrics: List[Metric]):
        """Flush metrics to PostgreSQL"""
        if not metrics or not self.db_pool:
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                # Batch insert metrics
                values = [
                    (
                        m.name,
                        m.metric_type.value,
                        m.value,
                        'seconds' if m.metric_type == MetricType.TIMING else None,
                        m.tags,
                        'production',  # environment
                        'rss_processor',  # service
                        '1.0',  # version
                        None,  # correlation_id
                        None,  # trace_id
                        m.timestamp,
                        {'source': 'metrics_collector'}  # metadata
                    )
                    for m in metrics
                ]
                
                await conn.executemany("""
                    INSERT INTO performance_metrics (
                        metric_name, metric_type, metric_value, metric_unit,
                        tags, environment, service, version,
                        correlation_id, trace_id, recorded_at, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """, values)
                
        except Exception as e:
            logger.error(f"Failed to flush metrics to PostgreSQL: {e}")
            raise
    
    async def _flush_loop(self):
        """Background task to periodically flush metrics"""
        while True:
            try:
                await asyncio.sleep(self.flush_interval_seconds)
                await self._flush_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush loop: {e}", exc_info=True)
    
    async def _cleanup_loop(self):
        """Background task to clean up old metrics"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self._cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)
    
    async def _cleanup_old_data(self):
        """Clean up old metric data"""
        try:
            # Clean up old histogram data (keep only last hour)
            cutoff_time = time.time() - 3600
            
            for key, deque_obj in self._histograms.items():
                # Remove old entries
                while deque_obj and deque_obj[0][0] < cutoff_time:
                    deque_obj.popleft()
            
            # Clean up old rate data
            for key, deque_obj in self._rates.items():
                while deque_obj and deque_obj[0][0] < cutoff_time:
                    deque_obj.popleft()
            
            # Clean up Redis data older than 24 hours
            if self.redis:
                cutoff_timestamp = int((datetime.utcnow() - timedelta(hours=24)).timestamp())
                
                async for key in self.redis.scan_iter(match="metrics:*"):
                    await self.redis.zremrangebyscore(key, 0, cutoff_timestamp)
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
    
    def _make_metric_key(self, name: str, tags: Dict[str, str] = None) -> str:
        """Create a unique key for a metric with tags"""
        if not tags:
            return name
        
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"
    
    # Query methods for dashboards and alerts
    
    async def get_counter_value(self, name: str, tags: Dict[str, str] = None) -> float:
        """Get current counter value"""
        key = self._make_metric_key(name, tags)
        return self._counters.get(key, 0.0)
    
    async def get_gauge_value(self, name: str, tags: Dict[str, str] = None) -> Optional[float]:
        """Get current gauge value"""
        key = self._make_metric_key(name, tags)
        return self._gauges.get(key)
    
    async def get_histogram_stats(self, name: str, tags: Dict[str, str] = None) -> Dict[str, float]:
        """Get histogram statistics"""
        key = self._make_metric_key(name, tags)
        values = [v for t, v in self._histograms[key]]
        
        if not values:
            return {}
        
        values.sort()
        n = len(values)
        
        return {
            'count': n,
            'min': values[0],
            'max': values[-1],
            'mean': sum(values) / n,
            'p50': values[int(n * 0.5)] if n > 0 else 0,
            'p95': values[int(n * 0.95)] if n > 0 else 0,
            'p99': values[int(n * 0.99)] if n > 0 else 0,
        }
    
    async def get_rate_per_second(self, name: str, tags: Dict[str, str] = None, window_seconds: int = 60) -> float:
        """Get rate per second for a metric"""
        key = self._make_metric_key(name, tags)
        now = time.time()
        cutoff = now - window_seconds
        
        # Count events in the time window
        count = sum(1 for t, v in self._rates[key] if t >= cutoff)
        return count / window_seconds
    
    def get_prometheus_metrics(self) -> str:
        """Generate Prometheus format metrics"""
        lines = []
        
        # Add counters
        for key, value in self._counters.items():
            name, tags = self._parse_metric_key(key)
            metric = Metric(name, value, MetricType.COUNTER, tags)
            lines.append(metric.to_prometheus_format())
        
        # Add gauges
        for key, value in self._gauges.items():
            name, tags = self._parse_metric_key(key)
            metric = Metric(name, value, MetricType.GAUGE, tags)
            lines.append(metric.to_prometheus_format())
        
        return '\n'.join(lines)
    
    def _parse_metric_key(self, key: str) -> tuple[str, Dict[str, str]]:
        """Parse metric key back to name and tags"""
        if '[' not in key:
            return key, {}
        
        name, tag_part = key.split('[', 1)
        tag_part = tag_part.rstrip(']')
        
        tags = {}
        if tag_part:
            for tag_pair in tag_part.split(','):
                k, v = tag_pair.split('=', 1)
                tags[k] = v
        
        return name, tags
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collector statistics"""
        return {
            'metrics_collected': self._metrics_collected,
            'buffer_size': len(self._metrics_buffer),
            'pending_timings': len(self._pending_timings),
            'counters_count': len(self._counters),
            'gauges_count': len(self._gauges),
            'histograms_count': len(self._histograms),
            'rates_count': len(self._rates),
            'last_flush': self._last_flush,
            'flush_errors': self._flush_errors
        }


class AlertManager:
    """
    Intelligent alert management system with:
    - Configurable thresholds and conditions
    - Alert suppression and routing
    - Notification channels (email, Slack, webhook)
    - Alert correlation and grouping
    """
    
    def __init__(self,
                 metrics_collector: MetricsCollector,
                 redis_client: Optional[redis.Redis] = None,
                 db_pool: Optional[asyncpg.Pool] = None):
        self.metrics = metrics_collector
        self.redis = redis_client
        self.db_pool = db_pool
        
        # Alert definitions
        self._alerts: Dict[str, Alert] = {}
        self._alert_history: Dict[str, List[Dict]] = defaultdict(list)
        
        # Alert evaluation
        self._evaluation_task: Optional[asyncio.Task] = None
        self._evaluation_interval = 30  # seconds
        
        # Notification handlers
        self._notification_handlers: Dict[str, Callable] = {}
        
        # Load default alerts
        self._load_default_alerts()
    
    async def initialize(self):
        """Initialize the alert manager"""
        # Load alerts from database if available
        if self.db_pool:
            await self._load_alerts_from_db()
        
        # Start evaluation loop
        self._evaluation_task = asyncio.create_task(self._evaluation_loop())
        
        logger.info("Alert manager initialized")
    
    async def shutdown(self):
        """Shutdown the alert manager"""
        if self._evaluation_task:
            self._evaluation_task.cancel()
        
        logger.info("Alert manager shutdown")
    
    def _load_default_alerts(self):
        """Load default production alerts"""
        
        # System health alerts
        self.add_alert(Alert(
            id="high_error_rate",
            name="High Error Rate",
            description="Error rate is above acceptable threshold",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            metric_name="pipeline.batch.error_rate",
            condition="> 0.05",  # 5% error rate
            threshold_value=0.05,
            duration_minutes=5,
            notification_channels=["email", "slack"]
        ))
        
        self.add_alert(Alert(
            id="low_throughput",
            name="Low Processing Throughput",
            description="Processing throughput is below expected levels",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.RESOLVED,
            metric_name="pipeline.batch.throughput",
            condition="< 100",  # Less than 100 articles/minute
            threshold_value=100,
            duration_minutes=10,
            notification_channels=["slack"]
        ))
        
        self.add_alert(Alert(
            id="high_latency",
            name="High Processing Latency",
            description="Pipeline processing latency is too high",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.RESOLVED,
            metric_name="pipeline.batch.duration",
            condition="> 300",  # More than 5 minutes per batch
            threshold_value=300,
            duration_minutes=3,
            notification_channels=["email"]
        ))
        
        self.add_alert(Alert(
            id="queue_backlog",
            name="Large Queue Backlog",
            description="Too many articles waiting for processing",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.RESOLVED,
            metric_name="queue.pending_articles",
            condition="> 10000",
            threshold_value=10000,
            duration_minutes=15,
            notification_channels=["slack"]
        ))
        
        self.add_alert(Alert(
            id="db_connection_pool_exhausted",
            name="Database Connection Pool Exhausted",
            description="Database connection pool is running out of connections",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            metric_name="db.connection_pool.available",
            condition="< 5",
            threshold_value=5,
            duration_minutes=1,
            notification_channels=["email", "slack"]
        ))
        
        self.add_alert(Alert(
            id="memory_usage_high",
            name="High Memory Usage",
            description="System memory usage is critically high",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            metric_name="system.memory.usage_percent",
            condition="> 90",
            threshold_value=90,
            duration_minutes=5,
            notification_channels=["email"]
        ))
        
        self.add_alert(Alert(
            id="disk_space_low",
            name="Low Disk Space",
            description="Available disk space is running low",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.RESOLVED,
            metric_name="system.disk.available_percent",
            condition="< 20",
            threshold_value=20,
            duration_minutes=10,
            notification_channels=["email", "slack"]
        ))
    
    def add_alert(self, alert: Alert):
        """Add an alert definition"""
        self._alerts[alert.id] = alert
    
    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert definition"""
        if alert_id in self._alerts:
            del self._alerts[alert_id]
            return True
        return False
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get an alert definition"""
        return self._alerts.get(alert_id)
    
    def list_alerts(self, status: Optional[AlertStatus] = None) -> List[Alert]:
        """List all alerts or alerts with specific status"""
        alerts = list(self._alerts.values())
        
        if status:
            alerts = [a for a in alerts if a.status == status]
        
        return alerts
    
    async def _evaluation_loop(self):
        """Background task to evaluate alerts"""
        while True:
            try:
                await asyncio.sleep(self._evaluation_interval)
                await self._evaluate_alerts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert evaluation loop: {e}", exc_info=True)
    
    async def _evaluate_alerts(self):
        """Evaluate all alerts against current metrics"""
        for alert in self._alerts.values():
            if not alert.enabled:
                continue
            
            try:
                await self._evaluate_single_alert(alert)
            except Exception as e:
                logger.error(f"Failed to evaluate alert {alert.id}: {e}")
    
    async def _evaluate_single_alert(self, alert: Alert):
        """Evaluate a single alert"""
        # Get current metric value
        current_value = await self._get_metric_value(alert.metric_name)
        if current_value is None:
            return
        
        # Check if alert condition is met
        should_trigger = alert.should_trigger(current_value)
        
        if should_trigger:
            if alert.status != AlertStatus.ACTIVE:
                # Check if condition has persisted for required duration
                if await self._check_alert_duration(alert, current_value):
                    alert.trigger()
                    await self._send_alert_notification(alert, current_value)
                    await self._record_alert_event(alert, "triggered", current_value)
                    
                    logger.warning(f"Alert triggered: {alert.name} (value: {current_value})")
        else:
            if alert.status == AlertStatus.ACTIVE:
                alert.resolve()
                await self._send_alert_notification(alert, current_value, resolved=True)
                await self._record_alert_event(alert, "resolved", current_value)
                
                logger.info(f"Alert resolved: {alert.name} (value: {current_value})")
    
    async def _get_metric_value(self, metric_name: str) -> Optional[float]:
        """Get current value of a metric"""
        # Try different metric types
        gauge_value = await self.metrics.get_gauge_value(metric_name)
        if gauge_value is not None:
            return gauge_value
        
        counter_value = await self.metrics.get_counter_value(metric_name)
        if counter_value != 0:
            return counter_value
        
        # For rates, calculate per-second rate
        rate_value = await self.metrics.get_rate_per_second(metric_name)
        if rate_value > 0:
            return rate_value
        
        # For histograms, use mean value
        histogram_stats = await self.metrics.get_histogram_stats(metric_name)
        if histogram_stats:
            return histogram_stats.get('mean', 0)
        
        return None
    
    async def _check_alert_duration(self, alert: Alert, current_value: float) -> bool:
        """Check if alert condition has persisted for required duration"""
        if alert.duration_minutes <= 0:
            return True  # No duration requirement
        
        # Store condition state in Redis for duration tracking
        if not self.redis:
            return True  # Can't track duration without Redis
        
        key = f"alert_condition:{alert.id}"
        now = time.time()
        
        # Get stored condition timestamps
        stored_data = await self.redis.get(key)
        if stored_data:
            data = json.loads(stored_data)
            first_seen = data.get('first_seen', now)
            
            # Check if condition has persisted long enough
            if now - first_seen >= (alert.duration_minutes * 60):
                # Clean up the stored state
                await self.redis.delete(key)
                return True
        else:
            # First time seeing this condition
            await self.redis.setex(
                key,
                alert.duration_minutes * 60 + 60,  # Add buffer
                json.dumps({
                    'first_seen': now,
                    'value': current_value,
                    'threshold': alert.threshold_value
                })
            )
        
        return False
    
    async def _send_alert_notification(self, alert: Alert, current_value: float, resolved: bool = False):
        """Send alert notification through configured channels"""
        for channel in alert.notification_channels:
            handler = self._notification_handlers.get(channel)
            if handler:
                try:
                    await handler(alert, current_value, resolved)
                except Exception as e:
                    logger.error(f"Failed to send alert notification via {channel}: {e}")
            else:
                logger.warning(f"No notification handler configured for channel: {channel}")
    
    async def _record_alert_event(self, alert: Alert, event_type: str, current_value: float):
        """Record alert event in history"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'current_value': current_value,
            'threshold': alert.threshold_value,
            'severity': alert.severity.value
        }
        
        self._alert_history[alert.id].append(event)
        
        # Keep only last 100 events per alert
        if len(self._alert_history[alert.id]) > 100:
            self._alert_history[alert.id] = self._alert_history[alert.id][-100:]
        
        # Store in database if available
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO alert_events (
                            alert_id, alert_name, event_type, current_value,
                            threshold_value, severity, recorded_at, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    alert.id, alert.name, event_type, current_value,
                    alert.threshold_value, alert.severity.value,
                    datetime.utcnow(), json.dumps({'tags': alert.tags}))
            except Exception as e:
                logger.error(f"Failed to record alert event in database: {e}")
    
    def register_notification_handler(self, channel: str, handler: Callable):
        """Register a notification handler for a channel"""
        self._notification_handlers[channel] = handler
    
    async def _load_alerts_from_db(self):
        """Load alert definitions from database"""
        # This would load custom alerts from database
        # For now, we'll just use the default alerts
        pass
    
    def get_alert_history(self, alert_id: str) -> List[Dict]:
        """Get alert history for a specific alert"""
        return self._alert_history.get(alert_id, [])


class DashboardMetrics:
    """
    Provides aggregated metrics for dashboards and monitoring displays
    """
    
    def __init__(self, metrics_collector: MetricsCollector, alert_manager: AlertManager):
        self.metrics = metrics_collector
        self.alerts = alert_manager
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """Get high-level system overview metrics"""
        return {
            'throughput': {
                'articles_per_minute': await self.metrics.get_rate_per_second('pipeline.articles.processed') * 60,
                'batches_per_hour': await self.metrics.get_rate_per_second('pipeline.batch.completed') * 3600,
                'avg_batch_size': await self._get_avg_batch_size()
            },
            'quality': {
                'success_rate': await self._get_success_rate(),
                'duplicate_rate': await self._get_duplicate_rate(),
                'avg_quality_score': await self._get_avg_quality_score()
            },
            'performance': {
                'avg_processing_time': await self._get_avg_processing_time(),
                'p95_processing_time': await self._get_p95_processing_time(),
                'queue_depth': await self.metrics.get_gauge_value('queue.pending_articles') or 0
            },
            'health': {
                'active_workers': await self.metrics.get_gauge_value('system.active_workers') or 0,
                'error_rate': await self._get_error_rate(),
                'active_alerts': len([a for a in self.alerts.list_alerts() if a.status == AlertStatus.ACTIVE])
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def get_pipeline_metrics(self) -> Dict[str, Any]:
        """Get detailed pipeline metrics"""
        stages = [
            'validation', 'feed_health', 'deduplication', 'normalization',
            'text_cleaning', 'indexing', 'chunking', 'search_indexing'
        ]
        
        stage_metrics = {}
        
        for stage in stages:
            stage_metrics[stage] = {
                'avg_duration': await self._get_stage_avg_duration(stage),
                'success_rate': await self._get_stage_success_rate(stage),
                'throughput': await self.metrics.get_rate_per_second(f'pipeline.stage.{stage}.completed')
            }
        
        return {
            'stages': stage_metrics,
            'overall': {
                'total_duration': sum([m['avg_duration'] for m in stage_metrics.values()]),
                'bottleneck_stage': max(stage_metrics.keys(), 
                                      key=lambda s: stage_metrics[s]['avg_duration']),
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def get_feed_metrics(self) -> Dict[str, Any]:
        """Get feed-related metrics"""
        return {
            'active_feeds': await self.metrics.get_gauge_value('feeds.active_count') or 0,
            'healthy_feeds': await self.metrics.get_gauge_value('feeds.healthy_count') or 0,
            'avg_health_score': await self.metrics.get_gauge_value('feeds.avg_health_score') or 0,
            'fetch_success_rate': await self._get_feed_fetch_success_rate(),
            'avg_fetch_time': await self._get_avg_feed_fetch_time(),
            'top_domains': await self._get_top_domains(),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    # Helper methods for calculating derived metrics
    
    async def _get_avg_batch_size(self) -> float:
        """Calculate average batch size"""
        stats = await self.metrics.get_histogram_stats('pipeline.batch.size')
        return stats.get('mean', 0) if stats else 0
    
    async def _get_success_rate(self) -> float:
        """Calculate overall success rate"""
        successful = await self.metrics.get_counter_value('pipeline.articles.processed')
        total = await self.metrics.get_counter_value('pipeline.articles.total')
        
        return (successful / total) if total > 0 else 0
    
    async def _get_duplicate_rate(self) -> float:
        """Calculate duplicate detection rate"""
        duplicates = await self.metrics.get_counter_value('pipeline.articles.duplicates')
        total = await self.metrics.get_counter_value('pipeline.articles.total')
        
        return (duplicates / total) if total > 0 else 0
    
    async def _get_avg_quality_score(self) -> float:
        """Calculate average quality score"""
        stats = await self.metrics.get_histogram_stats('pipeline.articles.quality_score')
        return stats.get('mean', 0) if stats else 0
    
    async def _get_avg_processing_time(self) -> float:
        """Calculate average processing time"""
        stats = await self.metrics.get_histogram_stats('pipeline.batch.duration')
        return stats.get('mean', 0) if stats else 0
    
    async def _get_p95_processing_time(self) -> float:
        """Calculate 95th percentile processing time"""
        stats = await self.metrics.get_histogram_stats('pipeline.batch.duration')
        return stats.get('p95', 0) if stats else 0
    
    async def _get_error_rate(self) -> float:
        """Calculate current error rate"""
        errors = await self.metrics.get_rate_per_second('pipeline.errors', window_seconds=300)  # 5 min window
        total = await self.metrics.get_rate_per_second('pipeline.articles.processed', window_seconds=300)
        
        return (errors / total) if total > 0 else 0
    
    async def _get_stage_avg_duration(self, stage: str) -> float:
        """Get average duration for a pipeline stage"""
        stats = await self.metrics.get_histogram_stats(f'pipeline.stage.{stage}.duration')
        return stats.get('mean', 0) if stats else 0
    
    async def _get_stage_success_rate(self, stage: str) -> float:
        """Get success rate for a pipeline stage"""
        successful = await self.metrics.get_counter_value(f'pipeline.stage.{stage}.success')
        total = await self.metrics.get_counter_value(f'pipeline.stage.{stage}.total')
        
        return (successful / total) if total > 0 else 0
    
    async def _get_feed_fetch_success_rate(self) -> float:
        """Calculate feed fetch success rate"""
        success = await self.metrics.get_counter_value('feeds.fetch.success')
        total = await self.metrics.get_counter_value('feeds.fetch.total')
        
        return (success / total) if total > 0 else 0
    
    async def _get_avg_feed_fetch_time(self) -> float:
        """Calculate average feed fetch time"""
        stats = await self.metrics.get_histogram_stats('feeds.fetch.duration')
        return stats.get('mean', 0) if stats else 0
    
    async def _get_top_domains(self) -> List[Dict[str, Any]]:
        """Get top domains by article count"""
        # This would require aggregating by domain tags
        # For now, return empty list
        return []


# Example notification handlers
async def email_notification_handler(alert: Alert, current_value: float, resolved: bool = False):
    """Send email notification for alerts"""
    # Implementation would use email service
    status = "RESOLVED" if resolved else "TRIGGERED"
    logger.info(f"EMAIL ALERT {status}: {alert.name} - Current value: {current_value}")


async def slack_notification_handler(alert: Alert, current_value: float, resolved: bool = False):
    """Send Slack notification for alerts"""
    # Implementation would use Slack API
    status = "✅ RESOLVED" if resolved else "🚨 TRIGGERED"
    logger.info(f"SLACK ALERT {status}: {alert.name} - Current value: {current_value}")


# Example usage
if __name__ == "__main__":
    async def test_monitoring_system():
        # Initialize components
        metrics = MetricsCollector()
        await metrics.initialize()
        
        alerts = AlertManager(metrics)
        alerts.register_notification_handler("email", email_notification_handler)
        alerts.register_notification_handler("slack", slack_notification_handler)
        await alerts.initialize()
        
        dashboard = DashboardMetrics(metrics, alerts)
        
        # Record some test metrics
        await metrics.increment("test.counter", 5)
        await metrics.gauge("test.gauge", 42.5)
        await metrics.histogram("test.histogram", 123.45)
        
        # Get system overview
        overview = await dashboard.get_system_overview()
        print("System Overview:", json.dumps(overview, indent=2))
        
        # Cleanup
        await metrics.shutdown()
        await alerts.shutdown()
        
        print("Monitoring system test completed")
    
    # asyncio.run(test_monitoring_system())