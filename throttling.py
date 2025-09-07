"""
Production-grade Throttling and Backpressure System
Implements circuit breakers, rate limiting, and adaptive load management for RSS processing.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field

from monitoring import MetricsCollector

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class ThrottleStrategy(Enum):
    """Throttling strategies"""
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    ADAPTIVE = "adaptive"


@dataclass
class LoadMetrics:
    """System load metrics for adaptive throttling"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    queue_depth: int = 0
    active_workers: int = 0
    avg_response_time_ms: float = 0.0
    error_rate_1min: float = 0.0
    success_rate_5min: float = 1.0
    
    def load_factor(self) -> float:
        """Calculate overall load factor (0.0-1.0)"""
        factors = [
            self.cpu_percent / 100.0,
            self.memory_percent / 100.0,
            min(self.queue_depth / 1000.0, 1.0),  # Normalize queue depth
            min(self.avg_response_time_ms / 5000.0, 1.0),  # 5s is high latency
            self.error_rate_1min * 2.0,  # Error rate has high weight
            max(0.0, 1.0 - self.success_rate_5min)  # Invert success rate
        ]
        return min(1.0, sum(factors) / len(factors))


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: int = 60
    max_requests_half_open: int = 5


@dataclass 
class RateLimitConfig:
    """Rate limiting configuration"""
    max_requests: int = 100
    window_seconds: int = 60
    strategy: ThrottleStrategy = ThrottleStrategy.SLIDING_WINDOW
    burst_allowance: int = 20


class CircuitBreaker:
    """
    Circuit breaker implementation for service protection
    Prevents cascade failures by monitoring success/failure rates
    """
    
    def __init__(self, 
                 name: str,
                 config: CircuitBreakerConfig,
                 redis_client: Optional[redis.Redis] = None,
                 metrics: Optional[MetricsCollector] = None):
        self.name = name
        self.config = config
        self.redis = redis_client
        self.metrics = metrics
        
        # Local state (for performance)
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.half_open_requests = 0
        
        # Distributed state key (Redis)
        self.redis_key = f"circuit_breaker:{name}"
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: When circuit is open
        """
        # Check if circuit should transition states
        await self._check_state_transition()
        
        if self.state == CircuitState.OPEN:
            await self._record_blocked_request()
            raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_requests >= self.config.max_requests_half_open:
                await self._record_blocked_request()
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} half-open limit exceeded")
            self.half_open_requests += 1
        
        # Execute the function
        start_time = time.time()
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Record success
            execution_time = (time.time() - start_time) * 1000
            await self._record_success(execution_time)
            
            return result
            
        except Exception as e:
            # Record failure
            execution_time = (time.time() - start_time) * 1000
            await self._record_failure(e, execution_time)
            raise
    
    async def _check_state_transition(self):
        """Check if circuit breaker should change state"""
        current_time = time.time()
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if current_time - self.last_failure_time >= self.config.timeout_seconds:
                await self._transition_to_half_open()
        
        elif self.state == CircuitState.HALF_OPEN:
            # Check if we should close or open
            if self.success_count >= self.config.success_threshold:
                await self._transition_to_closed()
            elif self.failure_count > 0:  # Any failure in half-open triggers open
                await self._transition_to_open()
    
    async def _record_success(self, execution_time_ms: float):
        """Record successful execution"""
        self.success_count += 1
        
        if self.state == CircuitState.HALF_OPEN:
            logger.debug(f"Circuit breaker {self.name}: Success in half-open state ({self.success_count}/{self.config.success_threshold})")
        
        if self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = max(0, self.failure_count - 1)
        
        # Record metrics
        if self.metrics:
            await self.metrics.increment(f"circuit_breaker.success", tags={"name": self.name, "state": self.state.value})
            await self.metrics.histogram(f"circuit_breaker.execution_time", execution_time_ms, tags={"name": self.name})
        
        # Update distributed state
        if self.redis:
            await self.redis.hset(self.redis_key, mapping={
                "success_count": self.success_count,
                "last_success": current_time := time.time(),
                "avg_execution_time": execution_time_ms
            })
    
    async def _record_failure(self, exception: Exception, execution_time_ms: float):
        """Record failed execution"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(f"Circuit breaker {self.name}: Failure recorded - {type(exception).__name__}: {exception}")
        
        # Check if we should trip to OPEN
        if self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
            await self._transition_to_open()
        elif self.state == CircuitState.HALF_OPEN:
            await self._transition_to_open()
        
        # Record metrics
        if self.metrics:
            await self.metrics.increment(f"circuit_breaker.failure", tags={
                "name": self.name, 
                "state": self.state.value,
                "exception": type(exception).__name__
            })
        
        # Update distributed state
        if self.redis:
            await self.redis.hset(self.redis_key, mapping={
                "failure_count": self.failure_count,
                "last_failure": self.last_failure_time,
                "last_exception": str(exception)
            })
    
    async def _record_blocked_request(self):
        """Record blocked request due to circuit breaker"""
        logger.debug(f"Circuit breaker {self.name}: Request blocked (state: {self.state.value})")
        
        if self.metrics:
            await self.metrics.increment(f"circuit_breaker.blocked", tags={"name": self.name, "state": self.state.value})
    
    async def _transition_to_open(self):
        """Transition circuit breaker to OPEN state"""
        self.state = CircuitState.OPEN
        self.half_open_requests = 0
        
        logger.warning(f"Circuit breaker {self.name}: OPEN (failures: {self.failure_count})")
        
        if self.metrics:
            await self.metrics.increment(f"circuit_breaker.state_change", tags={"name": self.name, "to_state": "open"})
        
        if self.redis:
            await self.redis.hset(self.redis_key, mapping={
                "state": "open",
                "opened_at": time.time()
            })
    
    async def _transition_to_half_open(self):
        """Transition circuit breaker to HALF_OPEN state"""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.failure_count = 0
        self.half_open_requests = 0
        
        logger.info(f"Circuit breaker {self.name}: HALF_OPEN (testing recovery)")
        
        if self.metrics:
            await self.metrics.increment(f"circuit_breaker.state_change", tags={"name": self.name, "to_state": "half_open"})
        
        if self.redis:
            await self.redis.hset(self.redis_key, mapping={
                "state": "half_open",
                "half_open_at": time.time()
            })
    
    async def _transition_to_closed(self):
        """Transition circuit breaker to CLOSED state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_requests = 0
        
        logger.info(f"Circuit breaker {self.name}: CLOSED (recovered)")
        
        if self.metrics:
            await self.metrics.increment(f"circuit_breaker.state_change", tags={"name": self.name, "to_state": "closed"})
        
        if self.redis:
            await self.redis.hset(self.redis_key, mapping={
                "state": "closed",
                "closed_at": time.time()
            })
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_requests": self.half_open_requests,
            "last_failure_time": self.last_failure_time,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds
            }
        }


class RateLimiter:
    """
    Advanced rate limiter with multiple strategies
    Supports fixed window, sliding window, and token bucket algorithms
    """
    
    def __init__(self,
                 name: str,
                 config: RateLimitConfig,
                 redis_client: Optional[redis.Redis] = None,
                 metrics: Optional[MetricsCollector] = None):
        self.name = name
        self.config = config
        self.redis = redis_client
        self.metrics = metrics
        
        # Local state for performance
        self._local_requests = deque(maxlen=config.max_requests * 2)
        self._local_tokens = config.burst_allowance
        self._last_token_refill = time.time()
        
        # Redis keys
        self.redis_key_requests = f"rate_limit:{name}:requests"
        self.redis_key_tokens = f"rate_limit:{name}:tokens"
    
    async def check_limit(self, key: str = "default", cost: int = 1) -> bool:
        """
        Check if request is within rate limit
        
        Args:
            key: Identifier for the entity being rate limited
            cost: Cost of this request (for weighted rate limiting)
            
        Returns:
            True if request is allowed, False if rate limited
        """
        if self.config.strategy == ThrottleStrategy.SLIDING_WINDOW:
            return await self._sliding_window_check(key, cost)
        elif self.config.strategy == ThrottleStrategy.TOKEN_BUCKET:
            return await self._token_bucket_check(key, cost)
        elif self.config.strategy == ThrottleStrategy.ADAPTIVE:
            return await self._adaptive_check(key, cost)
        else:
            return await self._fixed_window_check(key, cost)
    
    async def _sliding_window_check(self, key: str, cost: int) -> bool:
        """Sliding window rate limiting"""
        current_time = time.time()
        window_start = current_time - self.config.window_seconds
        
        if self.redis:
            # Use Redis for distributed rate limiting
            pipe = self.redis.pipeline()
            
            # Remove old requests outside the window
            pipe.zremrangebyscore(f"{self.redis_key_requests}:{key}", 0, window_start)
            
            # Count current requests in window
            pipe.zcard(f"{self.redis_key_requests}:{key}")
            
            # Add current request (tentatively)
            request_id = f"{current_time}_{uuid4().hex[:8]}"
            pipe.zadd(f"{self.redis_key_requests}:{key}", {request_id: current_time})
            
            # Set expiration
            pipe.expire(f"{self.redis_key_requests}:{key}", self.config.window_seconds + 10)
            
            results = await pipe.execute()
            current_requests = results[1]
            
            # Check if we exceeded the limit
            if current_requests + cost > self.config.max_requests:
                # Remove the tentative request
                await self.redis.zrem(f"{self.redis_key_requests}:{key}", request_id)
                await self._record_rate_limit_hit(key)
                return False
            else:
                await self._record_rate_limit_success(key)
                return True
        else:
            # Local sliding window
            # Clean old requests
            while self._local_requests and self._local_requests[0] < window_start:
                self._local_requests.popleft()
            
            if len(self._local_requests) + cost > self.config.max_requests:
                await self._record_rate_limit_hit(key)
                return False
            else:
                self._local_requests.append(current_time)
                await self._record_rate_limit_success(key)
                return True
    
    async def _token_bucket_check(self, key: str, cost: int) -> bool:
        """Token bucket rate limiting"""
        current_time = time.time()
        
        if self.redis:
            # Distributed token bucket using Lua script for atomicity
            lua_script = """
            local key = KEYS[1]
            local max_tokens = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local cost = tonumber(ARGV[3])
            local current_time = tonumber(ARGV[4])
            
            local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
            local tokens = tonumber(bucket[1]) or max_tokens
            local last_refill = tonumber(bucket[2]) or current_time
            
            -- Refill tokens
            local time_passed = current_time - last_refill
            local tokens_to_add = math.floor(time_passed * refill_rate)
            tokens = math.min(max_tokens, tokens + tokens_to_add)
            
            -- Check if we have enough tokens
            if tokens >= cost then
                tokens = tokens - cost
                redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
                redis.call('EXPIRE', key, 3600)  -- 1 hour expiration
                return 1  -- Success
            else
                redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
                redis.call('EXPIRE', key, 3600)
                return 0  -- Rate limited
            end
            """
            
            refill_rate = self.config.max_requests / self.config.window_seconds
            result = await self.redis.eval(
                lua_script,
                1,
                f"{self.redis_key_tokens}:{key}",
                str(self.config.burst_allowance),
                str(refill_rate),
                str(cost),
                str(current_time)
            )
            
            if result == 1:
                await self._record_rate_limit_success(key)
                return True
            else:
                await self._record_rate_limit_hit(key)
                return False
        else:
            # Local token bucket
            time_passed = current_time - self._last_token_refill
            refill_rate = self.config.max_requests / self.config.window_seconds
            tokens_to_add = time_passed * refill_rate
            
            self._local_tokens = min(self.config.burst_allowance, self._local_tokens + tokens_to_add)
            self._last_token_refill = current_time
            
            if self._local_tokens >= cost:
                self._local_tokens -= cost
                await self._record_rate_limit_success(key)
                return True
            else:
                await self._record_rate_limit_hit(key)
                return False
    
    async def _adaptive_check(self, key: str, cost: int) -> bool:
        """Adaptive rate limiting based on system load"""
        # Get current system load metrics
        load_metrics = await self._get_load_metrics()
        load_factor = load_metrics.load_factor()
        
        # Adjust rate limit based on load
        if load_factor > 0.9:
            # High load - reduce limit by 80%
            adjusted_limit = int(self.config.max_requests * 0.2)
        elif load_factor > 0.7:
            # Medium load - reduce limit by 50%
            adjusted_limit = int(self.config.max_requests * 0.5)
        elif load_factor > 0.5:
            # Light load - reduce limit by 20%
            adjusted_limit = int(self.config.max_requests * 0.8)
        else:
            # Low load - use full limit
            adjusted_limit = self.config.max_requests
        
        # Apply adaptive limit using sliding window
        original_max = self.config.max_requests
        self.config.max_requests = adjusted_limit
        
        try:
            result = await self._sliding_window_check(key, cost)
            
            # Record adaptive decision
            if self.metrics:
                await self.metrics.histogram(f"rate_limit.adaptive_factor", load_factor, tags={"name": self.name})
                await self.metrics.gauge(f"rate_limit.adjusted_limit", adjusted_limit, tags={"name": self.name})
            
            return result
        finally:
            # Restore original limit
            self.config.max_requests = original_max
    
    async def _fixed_window_check(self, key: str, cost: int) -> bool:
        """Fixed window rate limiting"""
        current_time = time.time()
        window_start = int(current_time // self.config.window_seconds) * self.config.window_seconds
        
        if self.redis:
            window_key = f"{self.redis_key_requests}:{key}:{window_start}"
            
            # Increment counter
            current_count = await self.redis.incr(window_key)
            
            if current_count == 1:
                # First request in this window - set expiration
                await self.redis.expire(window_key, self.config.window_seconds + 10)
            
            if current_count <= self.config.max_requests:
                await self._record_rate_limit_success(key)
                return True
            else:
                await self._record_rate_limit_hit(key)
                return False
        else:
            # Local implementation would need similar logic
            await self._record_rate_limit_success(key)
            return True  # Simplified for local mode
    
    async def _get_load_metrics(self) -> LoadMetrics:
        """Get current system load metrics"""
        # This would integrate with system monitoring
        # For now, return default values
        return LoadMetrics()
    
    async def _record_rate_limit_success(self, key: str):
        """Record successful rate limit check"""
        if self.metrics:
            await self.metrics.increment(f"rate_limit.allowed", tags={"name": self.name, "key": key})
    
    async def _record_rate_limit_hit(self, key: str):
        """Record rate limit hit"""
        logger.debug(f"Rate limit hit for {self.name}:{key}")
        
        if self.metrics:
            await self.metrics.increment(f"rate_limit.blocked", tags={"name": self.name, "key": key})
    
    def get_state(self) -> Dict[str, Any]:
        """Get current rate limiter state"""
        return {
            "name": self.name,
            "strategy": self.config.strategy.value,
            "max_requests": self.config.max_requests,
            "window_seconds": self.config.window_seconds,
            "local_tokens": getattr(self, '_local_tokens', 0),
            "local_requests_count": len(self._local_requests)
        }


class BackpressureManager:
    """
    Intelligent backpressure management system
    Monitors system health and automatically adjusts processing rates
    """
    
    def __init__(self,
                 redis_client: redis.Redis,
                 metrics: MetricsCollector,
                 db_pool: Optional[asyncpg.Pool] = None):
        self.redis = redis_client
        self.metrics = metrics
        self.db_pool = db_pool
        
        # Circuit breakers for different services
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Rate limiters for different resources
        self.rate_limiters: Dict[str, RateLimiter] = {}
        
        # Load monitoring
        self.load_history = deque(maxlen=100)  # Keep last 100 load measurements
        
        # Configuration
        self.monitoring_interval = 30  # seconds
        self.backpressure_enabled = True
        
        # Initialize default circuit breakers
        self._initialize_circuit_breakers()
        
        # Initialize default rate limiters
        self._initialize_rate_limiters()
    
    def _initialize_circuit_breakers(self):
        """Initialize circuit breakers for critical services"""
        
        # Database circuit breaker
        self.circuit_breakers['database'] = CircuitBreaker(
            name='database',
            config=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                timeout_seconds=30
            ),
            redis_client=self.redis,
            metrics=self.metrics
        )
        
        # Feed fetching circuit breaker
        self.circuit_breakers['feed_fetching'] = CircuitBreaker(
            name='feed_fetching',
            config=CircuitBreakerConfig(
                failure_threshold=10,
                success_threshold=5,
                timeout_seconds=60
            ),
            redis_client=self.redis,
            metrics=self.metrics
        )
        
        # Pipeline processing circuit breaker
        self.circuit_breakers['pipeline'] = CircuitBreaker(
            name='pipeline',
            config=CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=120
            ),
            redis_client=self.redis,
            metrics=self.metrics
        )
    
    def _initialize_rate_limiters(self):
        """Initialize rate limiters for different resources"""
        
        # Per-domain rate limiter
        self.rate_limiters['domain'] = RateLimiter(
            name='domain_requests',
            config=RateLimitConfig(
                max_requests=10,
                window_seconds=60,
                strategy=ThrottleStrategy.SLIDING_WINDOW,
                burst_allowance=3
            ),
            redis_client=self.redis,
            metrics=self.metrics
        )
        
        # Database operations rate limiter
        self.rate_limiters['database'] = RateLimiter(
            name='database_operations',
            config=RateLimitConfig(
                max_requests=1000,
                window_seconds=60,
                strategy=ThrottleStrategy.ADAPTIVE,
                burst_allowance=100
            ),
            redis_client=self.redis,
            metrics=self.metrics
        )
        
        # Batch processing rate limiter
        self.rate_limiters['batch_processing'] = RateLimiter(
            name='batch_processing',
            config=RateLimitConfig(
                max_requests=5,
                window_seconds=60,
                strategy=ThrottleStrategy.TOKEN_BUCKET,
                burst_allowance=2
            ),
            redis_client=self.redis,
            metrics=self.metrics
        )
    
    async def execute_with_protection(self,
                                    func: Callable,
                                    circuit_breaker_name: str,
                                    rate_limit_key: str = None,
                                    rate_limit_name: str = None,
                                    *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker and rate limiting protection
        
        Args:
            func: Function to execute
            circuit_breaker_name: Name of circuit breaker to use
            rate_limit_key: Key for rate limiting (e.g., domain name)
            rate_limit_name: Name of rate limiter to use
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            RateLimitExceededError: If rate limit is exceeded
        """
        # Check rate limit first (faster than circuit breaker)
        if rate_limit_name and rate_limit_key:
            rate_limiter = self.rate_limiters.get(rate_limit_name)
            if rate_limiter:
                allowed = await rate_limiter.check_limit(rate_limit_key)
                if not allowed:
                    raise RateLimitExceededError(f"Rate limit exceeded for {rate_limit_name}:{rate_limit_key}")
        
        # Execute through circuit breaker
        circuit_breaker = self.circuit_breakers.get(circuit_breaker_name)
        if circuit_breaker:
            return await circuit_breaker.call(func, *args, **kwargs)
        else:
            # No circuit breaker configured - execute directly
            return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
    
    async def monitor_system_health(self) -> LoadMetrics:
        """Monitor system health and return current load metrics"""
        try:
            # Collect various system metrics
            load_metrics = LoadMetrics()
            
            # Queue depth from database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    queue_depth = await conn.fetchval(
                        "SELECT COUNT(*) FROM raw_articles WHERE status = 'pending'"
                    )
                    load_metrics.queue_depth = queue_depth or 0
                    
                    # Active workers
                    active_workers = await conn.fetchval(
                        "SELECT COUNT(DISTINCT worker_id) FROM batches WHERE status = 'processing'"
                    )
                    load_metrics.active_workers = active_workers or 0
                    
                    # Average response time from recent metrics
                    avg_response = await conn.fetchval("""
                        SELECT AVG(metric_value)
                        FROM performance_metrics
                        WHERE metric_name = 'batch.processing_time'
                          AND recorded_at > NOW() - INTERVAL '5 minutes'
                    """)
                    load_metrics.avg_response_time_ms = (avg_response or 0) * 1000
                    
                    # Error rate
                    error_rate = await conn.fetchval("""
                        SELECT 
                            COALESCE(
                                SUM(CASE WHEN metric_name = 'batch.error_rate' THEN metric_value ELSE 0 END) / 
                                NULLIF(COUNT(*), 0),
                                0
                            )
                        FROM performance_metrics
                        WHERE metric_name IN ('batch.error_rate', 'batch.success_rate')
                          AND recorded_at > NOW() - INTERVAL '1 minute'
                    """)
                    load_metrics.error_rate_1min = error_rate or 0
            
            # System resource usage (would integrate with psutil or similar)
            # For now, use placeholders
            load_metrics.cpu_percent = 50.0  # Would get actual CPU usage
            load_metrics.memory_percent = 60.0  # Would get actual memory usage
            
            # Store in history for trend analysis
            self.load_history.append(load_metrics)
            
            # Record metrics
            await self.metrics.gauge('backpressure.load_factor', load_metrics.load_factor())
            await self.metrics.gauge('backpressure.queue_depth', load_metrics.queue_depth)
            await self.metrics.gauge('backpressure.active_workers', load_metrics.active_workers)
            
            return load_metrics
            
        except Exception as e:
            logger.error(f"Failed to monitor system health: {e}", exc_info=True)
            return LoadMetrics()  # Return defaults on error
    
    async def adjust_processing_rate(self, load_metrics: LoadMetrics) -> Dict[str, Any]:
        """
        Adjust processing rates based on system load
        
        Args:
            load_metrics: Current system load metrics
            
        Returns:
            Dict with adjustment decisions
        """
        adjustments = {}
        load_factor = load_metrics.load_factor()
        
        # Adjust batch processing rate
        if load_factor > 0.9:
            # High load - pause batch processing temporarily
            adjustments['batch_processing'] = 'pause'
            logger.warning("High system load detected - pausing batch processing")
        elif load_factor > 0.7:
            # Medium load - reduce processing rate
            adjustments['batch_processing'] = 'throttle_high'
            # Increase rate limit window to slow down processing
            batch_limiter = self.rate_limiters.get('batch_processing')
            if batch_limiter:
                batch_limiter.config.window_seconds = 120  # Slower processing
        elif load_factor > 0.5:
            # Light load - moderate throttling
            adjustments['batch_processing'] = 'throttle_medium'
            batch_limiter = self.rate_limiters.get('batch_processing')
            if batch_limiter:
                batch_limiter.config.window_seconds = 80
        else:
            # Low load - normal processing
            adjustments['batch_processing'] = 'normal'
            batch_limiter = self.rate_limiters.get('batch_processing')
            if batch_limiter:
                batch_limiter.config.window_seconds = 60  # Normal rate
        
        # Adjust database operations
        if load_metrics.avg_response_time_ms > 5000:  # 5 seconds
            adjustments['database'] = 'throttle'
            db_limiter = self.rate_limiters.get('database')
            if db_limiter:
                db_limiter.config.max_requests = int(db_limiter.config.max_requests * 0.5)
        else:
            adjustments['database'] = 'normal'
        
        # Record adjustment decisions
        await self.metrics.increment('backpressure.adjustments', tags={
            'load_factor_range': self._get_load_range(load_factor),
            'batch_action': adjustments.get('batch_processing', 'normal')
        })
        
        return adjustments
    
    def _get_load_range(self, load_factor: float) -> str:
        """Get load factor range for tagging"""
        if load_factor > 0.9:
            return 'critical'
        elif load_factor > 0.7:
            return 'high'
        elif load_factor > 0.5:
            return 'medium'
        else:
            return 'low'
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        load_metrics = await self.monitor_system_health()
        
        # Circuit breaker states
        circuit_states = {}
        for name, cb in self.circuit_breakers.items():
            circuit_states[name] = cb.get_state()
        
        # Rate limiter states
        rate_limit_states = {}
        for name, rl in self.rate_limiters.items():
            rate_limit_states[name] = rl.get_state()
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'load_metrics': {
                'load_factor': load_metrics.load_factor(),
                'cpu_percent': load_metrics.cpu_percent,
                'memory_percent': load_metrics.memory_percent,
                'queue_depth': load_metrics.queue_depth,
                'active_workers': load_metrics.active_workers,
                'avg_response_time_ms': load_metrics.avg_response_time_ms,
                'error_rate_1min': load_metrics.error_rate_1min
            },
            'circuit_breakers': circuit_states,
            'rate_limiters': rate_limit_states,
            'backpressure_enabled': self.backpressure_enabled
        }
    
    async def start_monitoring(self):
        """Start background monitoring task"""
        asyncio.create_task(self._monitoring_loop())
        logger.info("Backpressure monitoring started")
    
    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.backpressure_enabled:
            try:
                # Monitor system health
                load_metrics = await self.monitor_system_health()
                
                # Apply adjustments based on load
                adjustments = await self.adjust_processing_rate(load_metrics)
                
                # Log significant changes
                if adjustments.get('batch_processing') == 'pause':
                    logger.warning("System overloaded - batch processing paused")
                elif adjustments.get('batch_processing') in ['throttle_high', 'throttle_medium']:
                    logger.info(f"System load elevated - batch processing {adjustments['batch_processing']}")
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Longer wait on error


# Custom exceptions
class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded"""
    pass


# Example usage
if __name__ == "__main__":
    async def example_usage():
        # This would be integrated with the actual system
        print("Throttling and Backpressure System")
        print("Features:")
        print("- Circuit breakers for service protection")
        print("- Rate limiting with multiple strategies")
        print("- Adaptive backpressure based on system load")
        print("- Distributed coordination via Redis")
        print("- Comprehensive monitoring and metrics")
    
    # asyncio.run(example_usage())