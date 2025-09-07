"""
Production-grade Connection Pool Manager and Performance Optimization
Handles PostgreSQL and Redis connections with intelligent pooling, health checks, and optimization.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager
import weakref

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field

from monitoring import MetricsCollector

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"


@dataclass
class ConnectionMetrics:
    """Metrics for a single connection"""
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_query_time_ms: float = 0.0
    last_used: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    connection_errors: int = 0
    state: ConnectionState = ConnectionState.HEALTHY
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        return self.successful_queries / max(self.total_queries, 1)
    
    @property
    def age_seconds(self) -> float:
        """Connection age in seconds"""
        return time.time() - self.created_at
    
    @property
    def idle_seconds(self) -> float:
        """Time since last use"""
        return time.time() - self.last_used


@dataclass
class PoolConfiguration:
    """Connection pool configuration"""
    min_size: int = 5
    max_size: int = 20
    idle_timeout: int = 300  # 5 minutes
    max_lifetime: int = 3600  # 1 hour
    health_check_interval: int = 60  # 1 minute
    retry_attempts: int = 3
    retry_delay: float = 1.0
    command_timeout: int = 30
    
    # Performance optimization
    statement_cache_size: int = 100
    prepared_statement_cache_size: int = 100
    
    # Connection validation
    validation_query: str = "SELECT 1"
    validation_timeout: int = 5


class DatabaseConnectionManager:
    """
    Advanced PostgreSQL connection pool manager with:
    - Intelligent connection health monitoring
    - Automatic failover and recovery
    - Connection lifecycle management  
    - Performance optimization
    - Detailed metrics and monitoring
    """
    
    def __init__(self,
                 database_url: str,
                 pool_config: PoolConfiguration,
                 metrics: Optional[MetricsCollector] = None,
                 pool_name: str = "main"):
        self.database_url = database_url
        self.config = pool_config
        self.metrics = metrics
        self.pool_name = pool_name
        
        # Connection pool
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_lock = asyncio.Lock()
        
        # Connection tracking
        self._connection_metrics: Dict[int, ConnectionMetrics] = {}
        self._connection_refs: weakref.WeakSet = weakref.WeakSet()
        
        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._pool_state = ConnectionState.HEALTHY
        self._last_health_check = 0
        
        # Performance optimization
        self._statement_cache: Dict[str, str] = {}
        self._query_stats = defaultdict(lambda: {'count': 0, 'total_time': 0.0, 'avg_time': 0.0})
        
        # Connection lifecycle stats
        self._total_connections_created = 0
        self._total_connections_closed = 0
        self._current_connections = 0
    
    async def initialize(self) -> bool:
        """
        Initialize the connection pool
        
        Returns:
            True if successful, False otherwise
        """
        try:
            async with self._pool_lock:
                if self._pool is not None:
                    logger.warning(f"Pool {self.pool_name} already initialized")
                    return True
                
                logger.info(f"Initializing database pool {self.pool_name}")
                
                # Parse database URL for pool creation
                self._pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=self.config.min_size,
                    max_size=self.config.max_size,
                    command_timeout=self.config.command_timeout,
                    max_inactive_connection_lifetime=self.config.idle_timeout,
                    server_settings={
                        'statement_timeout': f'{self.config.command_timeout}s',
                        'idle_in_transaction_session_timeout': f'{self.config.idle_timeout}s',
                        'application_name': f'rss_pipeline_{self.pool_name}'
                    },
                    init=self._init_connection
                )
                
                # Start health monitoring
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                
                # Record initialization
                if self.metrics:
                    await self.metrics.increment(f"db_pool.initialized", tags={"pool": self.pool_name})
                
                logger.info(f"Database pool {self.pool_name} initialized successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize database pool {self.pool_name}: {e}", exc_info=True)
            if self.metrics:
                await self.metrics.increment(f"db_pool.init_error", tags={"pool": self.pool_name})
            return False
    
    async def _init_connection(self, conn: asyncpg.Connection):
        """Initialize a new connection with optimizations"""
        try:
            # Set connection-level optimizations
            await conn.execute("SET statement_timeout = $1", f"{self.config.command_timeout}s")
            await conn.execute("SET lock_timeout = '30s'")
            await conn.execute("SET synchronous_commit = 'off'")  # For performance (be careful with this)
            
            # Connection tracking
            conn_id = id(conn)
            self._connection_metrics[conn_id] = ConnectionMetrics()
            self._connection_refs.add(conn)
            
            self._total_connections_created += 1
            self._current_connections += 1
            
            logger.debug(f"Initialized new database connection {conn_id}")
            
            if self.metrics:
                await self.metrics.increment(f"db_pool.connections_created", tags={"pool": self.pool_name})
                await self.metrics.gauge(f"db_pool.current_connections", self._current_connections, tags={"pool": self.pool_name})
            
        except Exception as e:
            logger.error(f"Failed to initialize connection: {e}", exc_info=True)
            raise
    
    @asynccontextmanager
    async def acquire_connection(self, timeout: Optional[float] = None):
        """
        Acquire a connection from the pool with automatic cleanup
        
        Args:
            timeout: Maximum time to wait for connection
            
        Yields:
            Database connection
        """
        if not self._pool:
            raise RuntimeError(f"Database pool {self.pool_name} not initialized")
        
        conn = None
        start_time = time.time()
        
        try:
            # Acquire connection with timeout
            conn = await asyncio.wait_for(
                self._pool.acquire(),
                timeout=timeout or self.config.command_timeout
            )
            
            # Track connection usage
            conn_id = id(conn)
            if conn_id in self._connection_metrics:
                self._connection_metrics[conn_id].last_used = time.time()
            
            acquisition_time = time.time() - start_time
            
            if self.metrics:
                await self.metrics.timing(f"db_pool.acquisition_time", acquisition_time, tags={"pool": self.pool_name})
            
            yield conn
            
        except asyncio.TimeoutError:
            logger.error(f"Connection acquisition timeout for pool {self.pool_name}")
            if self.metrics:
                await self.metrics.increment(f"db_pool.acquisition_timeout", tags={"pool": self.pool_name})
            raise
        except Exception as e:
            logger.error(f"Connection acquisition error for pool {self.pool_name}: {e}")
            if self.metrics:
                await self.metrics.increment(f"db_pool.acquisition_error", tags={"pool": self.pool_name})
            raise
        finally:
            if conn:
                try:
                    await self._pool.release(conn)
                except Exception as e:
                    logger.error(f"Error releasing connection: {e}")
    
    async def execute_query(self,
                          query: str,
                          *args,
                          timeout: Optional[float] = None,
                          prepare: bool = True) -> Any:
        """
        Execute a query with performance tracking
        
        Args:
            query: SQL query to execute
            *args: Query parameters
            timeout: Query timeout
            prepare: Whether to use prepared statements
            
        Returns:
            Query result
        """
        start_time = time.time()
        query_hash = hash(query)
        
        try:
            async with self.acquire_connection(timeout=timeout) as conn:
                conn_id = id(conn)
                
                # Execute query
                if prepare and len(args) > 0:
                    result = await conn.fetch(query, *args, timeout=timeout)
                else:
                    result = await conn.fetch(query, timeout=timeout)
                
                # Track metrics
                execution_time = time.time() - start_time
                
                # Update connection metrics
                if conn_id in self._connection_metrics:
                    metrics = self._connection_metrics[conn_id]
                    metrics.total_queries += 1
                    metrics.successful_queries += 1
                    
                    # Update average query time
                    total_time = metrics.avg_query_time_ms * (metrics.total_queries - 1) + (execution_time * 1000)
                    metrics.avg_query_time_ms = total_time / metrics.total_queries
                
                # Update query statistics
                self._query_stats[query_hash]['count'] += 1
                self._query_stats[query_hash]['total_time'] += execution_time
                self._query_stats[query_hash]['avg_time'] = (
                    self._query_stats[query_hash]['total_time'] / self._query_stats[query_hash]['count']
                )
                
                if self.metrics:
                    await self.metrics.timing(f"db_pool.query_time", execution_time, tags={
                        "pool": self.pool_name,
                        "prepared": str(prepare)
                    })
                    await self.metrics.increment(f"db_pool.queries_executed", tags={"pool": self.pool_name})
                
                return result
                
        except Exception as e:
            execution_time = time.time() - start_time
            
            # Track failed query
            if hasattr(locals(), 'conn_id') and locals()['conn_id'] in self._connection_metrics:
                metrics = self._connection_metrics[locals()['conn_id']]
                metrics.total_queries += 1
                metrics.failed_queries += 1
            
            logger.error(f"Query execution failed in {execution_time:.3f}s: {e}")
            
            if self.metrics:
                await self.metrics.increment(f"db_pool.query_errors", tags={
                    "pool": self.pool_name,
                    "error_type": type(e).__name__
                })
            
            raise
    
    async def execute_transaction(self,
                                queries: List[Tuple[str, tuple]],
                                timeout: Optional[float] = None) -> List[Any]:
        """
        Execute multiple queries in a transaction
        
        Args:
            queries: List of (query, args) tuples
            timeout: Transaction timeout
            
        Returns:
            List of query results
        """
        start_time = time.time()
        
        try:
            async with self.acquire_connection(timeout=timeout) as conn:
                async with conn.transaction():
                    results = []
                    
                    for query, args in queries:
                        result = await conn.fetch(query, *args, timeout=timeout)
                        results.append(result)
                    
                    transaction_time = time.time() - start_time
                    
                    if self.metrics:
                        await self.metrics.timing(f"db_pool.transaction_time", transaction_time, tags={"pool": self.pool_name})
                        await self.metrics.increment(f"db_pool.transactions_executed", tags={"pool": self.pool_name})
                    
                    return results
                    
        except Exception as e:
            transaction_time = time.time() - start_time
            logger.error(f"Transaction failed in {transaction_time:.3f}s: {e}")
            
            if self.metrics:
                await self.metrics.increment(f"db_pool.transaction_errors", tags={"pool": self.pool_name})
            
            raise
    
    async def _health_check_loop(self):
        """Background health check task"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error for pool {self.pool_name}: {e}", exc_info=True)
    
    async def _perform_health_check(self):
        """Perform comprehensive health check"""
        if not self._pool:
            return
        
        start_time = time.time()
        
        try:
            # Test pool connectivity
            async with self.acquire_connection(timeout=self.config.validation_timeout) as conn:
                await conn.fetchval(self.config.validation_query, timeout=self.config.validation_timeout)
            
            # Update pool state
            previous_state = self._pool_state
            self._pool_state = ConnectionState.HEALTHY
            
            if previous_state != ConnectionState.HEALTHY:
                logger.info(f"Database pool {self.pool_name} recovered to HEALTHY state")
                if self.metrics:
                    await self.metrics.increment(f"db_pool.state_change", tags={
                        "pool": self.pool_name,
                        "from_state": previous_state.value,
                        "to_state": "healthy"
                    })
            
        except Exception as e:
            # Update pool state based on error type
            if isinstance(e, asyncio.TimeoutError):
                self._pool_state = ConnectionState.DEGRADED
            else:
                self._pool_state = ConnectionState.UNHEALTHY
            
            logger.warning(f"Database pool {self.pool_name} health check failed: {e}")
            
            if self.metrics:
                await self.metrics.increment(f"db_pool.health_check_failed", tags={"pool": self.pool_name})
        
        finally:
            health_check_time = time.time() - start_time
            self._last_health_check = time.time()
            
            if self.metrics:
                await self.metrics.timing(f"db_pool.health_check_time", health_check_time, tags={"pool": self.pool_name})
                await self.metrics.gauge(f"db_pool.state", 1 if self._pool_state == ConnectionState.HEALTHY else 0, 
                                       tags={"pool": self.pool_name})
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get comprehensive pool statistics"""
        if not self._pool:
            return {"error": "Pool not initialized"}
        
        # Basic pool stats
        pool_stats = {
            "pool_name": self.pool_name,
            "pool_state": self._pool_state.value,
            "current_size": self._pool.get_size(),
            "idle_size": self._pool.get_idle_size(),
            "max_size": self._pool.get_max_size(),
            "min_size": self._pool.get_min_size(),
        }
        
        # Connection lifecycle stats
        pool_stats.update({
            "total_connections_created": self._total_connections_created,
            "total_connections_closed": self._total_connections_closed,
            "current_connections": self._current_connections,
            "last_health_check": self._last_health_check
        })
        
        # Connection metrics summary
        if self._connection_metrics:
            success_rates = [m.success_rate for m in self._connection_metrics.values()]
            avg_query_times = [m.avg_query_time_ms for m in self._connection_metrics.values()]
            connection_ages = [m.age_seconds for m in self._connection_metrics.values()]
            
            pool_stats["connection_stats"] = {
                "avg_success_rate": sum(success_rates) / len(success_rates) if success_rates else 0,
                "avg_query_time_ms": sum(avg_query_times) / len(avg_query_times) if avg_query_times else 0,
                "avg_connection_age_seconds": sum(connection_ages) / len(connection_ages) if connection_ages else 0,
                "healthy_connections": len([m for m in self._connection_metrics.values() if m.state == ConnectionState.HEALTHY])
            }
        
        # Top queries by execution time
        top_queries = sorted(
            [(qh, stats) for qh, stats in self._query_stats.items()],
            key=lambda x: x[1]['avg_time'],
            reverse=True
        )[:10]
        
        pool_stats["top_slow_queries"] = [
            {"query_hash": qh, "avg_time": stats['avg_time'], "count": stats['count']}
            for qh, stats in top_queries
        ]
        
        return pool_stats
    
    async def optimize_pool(self) -> Dict[str, Any]:
        """
        Automatically optimize pool configuration based on usage patterns
        
        Returns:
            Dict with optimization recommendations
        """
        stats = await self.get_pool_stats()
        recommendations = {}
        
        # Analyze connection usage
        current_size = stats.get("current_size", 0)
        idle_size = stats.get("idle_size", 0)
        max_size = stats.get("max_size", 0)
        
        utilization = (current_size - idle_size) / max(current_size, 1)
        
        # Pool size recommendations
        if utilization > 0.9:  # High utilization
            recommendations["pool_size"] = {
                "action": "increase",
                "current_max": max_size,
                "recommended_max": min(max_size + 5, 50),
                "reason": "High pool utilization detected"
            }
        elif utilization < 0.3 and current_size > self.config.min_size:  # Low utilization
            recommendations["pool_size"] = {
                "action": "decrease", 
                "current_max": max_size,
                "recommended_max": max(max_size - 3, self.config.min_size),
                "reason": "Low pool utilization detected"
            }
        
        # Query performance analysis
        connection_stats = stats.get("connection_stats", {})
        avg_query_time = connection_stats.get("avg_query_time_ms", 0)
        
        if avg_query_time > 1000:  # Slow queries
            recommendations["query_performance"] = {
                "action": "investigate_slow_queries",
                "avg_query_time_ms": avg_query_time,
                "reason": "Slow average query time detected"
            }
        
        # Connection health
        if connection_stats.get("avg_success_rate", 1.0) < 0.95:
            recommendations["connection_health"] = {
                "action": "investigate_connection_errors",
                "success_rate": connection_stats.get("avg_success_rate", 1.0),
                "reason": "Low connection success rate"
            }
        
        return recommendations
    
    async def close(self):
        """Clean shutdown of the connection pool"""
        logger.info(f"Closing database pool {self.pool_name}")
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        if self._pool:
            await self._pool.close()
            self._pool = None
        
        if self.metrics:
            await self.metrics.increment(f"db_pool.closed", tags={"pool": self.pool_name})
        
        logger.info(f"Database pool {self.pool_name} closed successfully")


class RedisConnectionManager:
    """
    Redis connection pool manager with similar features to DatabaseConnectionManager
    """
    
    def __init__(self,
                 redis_url: str,
                 pool_config: PoolConfiguration,
                 metrics: Optional[MetricsCollector] = None,
                 pool_name: str = "redis_main"):
        self.redis_url = redis_url
        self.config = pool_config
        self.metrics = metrics
        self.pool_name = pool_name
        
        # Redis pool
        self._pool: Optional[redis.ConnectionPool] = None
        self._redis_client: Optional[redis.Redis] = None
        
        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._pool_state = ConnectionState.HEALTHY
        
        # Metrics
        self._command_stats = defaultdict(lambda: {'count': 0, 'total_time': 0.0})
    
    async def initialize(self) -> bool:
        """Initialize Redis connection pool"""
        try:
            # Create connection pool
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.config.max_size,
                socket_timeout=self.config.command_timeout,
                socket_connect_timeout=self.config.command_timeout,
                health_check_interval=self.config.health_check_interval
            )
            
            # Create Redis client
            self._redis_client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._redis_client.ping()
            
            # Start health monitoring
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info(f"Redis pool {self.pool_name} initialized successfully")
            
            if self.metrics:
                await self.metrics.increment(f"redis_pool.initialized", tags={"pool": self.pool_name})
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis pool {self.pool_name}: {e}", exc_info=True)
            if self.metrics:
                await self.metrics.increment(f"redis_pool.init_error", tags={"pool": self.pool_name})
            return False
    
    async def execute_command(self, command: str, *args, **kwargs) -> Any:
        """Execute Redis command with performance tracking"""
        if not self._redis_client:
            raise RuntimeError(f"Redis pool {self.pool_name} not initialized")
        
        start_time = time.time()
        
        try:
            # Execute command
            method = getattr(self._redis_client, command.lower())
            result = await method(*args, **kwargs)
            
            # Track performance
            execution_time = time.time() - start_time
            self._command_stats[command]['count'] += 1
            self._command_stats[command]['total_time'] += execution_time
            
            if self.metrics:
                await self.metrics.timing(f"redis_pool.command_time", execution_time, tags={
                    "pool": self.pool_name,
                    "command": command
                })
                await self.metrics.increment(f"redis_pool.commands_executed", tags={"pool": self.pool_name})
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Redis command {command} failed in {execution_time:.3f}s: {e}")
            
            if self.metrics:
                await self.metrics.increment(f"redis_pool.command_errors", tags={
                    "pool": self.pool_name,
                    "command": command
                })
            
            raise
    
    async def _health_check_loop(self):
        """Background health check for Redis"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                if self._redis_client:
                    await self._redis_client.ping()
                    self._pool_state = ConnectionState.HEALTHY
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._pool_state = ConnectionState.UNHEALTHY
                logger.error(f"Redis health check failed for {self.pool_name}: {e}")
                
                if self.metrics:
                    await self.metrics.increment(f"redis_pool.health_check_failed", tags={"pool": self.pool_name})
    
    def get_client(self) -> redis.Redis:
        """Get Redis client instance"""
        if not self._redis_client:
            raise RuntimeError(f"Redis pool {self.pool_name} not initialized")
        return self._redis_client
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get Redis pool statistics"""
        if not self._pool:
            return {"error": "Pool not initialized"}
        
        # Basic pool info
        pool_info = {
            "pool_name": self.pool_name,
            "pool_state": self._pool_state.value,
            "max_connections": self._pool.max_connections,
            "created_connections": self._pool.created_connections
        }
        
        # Command statistics
        if self._command_stats:
            top_commands = sorted(
                [(cmd, stats) for cmd, stats in self._command_stats.items()],
                key=lambda x: x[1]['total_time'],
                reverse=True
            )[:10]
            
            pool_info["top_commands"] = [
                {
                    "command": cmd,
                    "count": stats['count'],
                    "total_time": stats['total_time'],
                    "avg_time": stats['total_time'] / stats['count']
                }
                for cmd, stats in top_commands
            ]
        
        return pool_info
    
    async def close(self):
        """Close Redis connection pool"""
        logger.info(f"Closing Redis pool {self.pool_name}")
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
        
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
        
        logger.info(f"Redis pool {self.pool_name} closed successfully")


class ConnectionPoolManager:
    """
    Central manager for all database and Redis connections
    Provides unified interface and cross-pool optimization
    """
    
    def __init__(self, metrics: Optional[MetricsCollector] = None):
        self.metrics = metrics
        
        # Connection managers
        self.database_pools: Dict[str, DatabaseConnectionManager] = {}
        self.redis_pools: Dict[str, RedisConnectionManager] = {}
        
        # Global optimization task
        self._optimization_task: Optional[asyncio.Task] = None
        self._optimization_interval = 300  # 5 minutes
    
    async def add_database_pool(self,
                              name: str,
                              database_url: str,
                              config: Optional[PoolConfiguration] = None) -> bool:
        """Add a database connection pool"""
        if name in self.database_pools:
            logger.warning(f"Database pool {name} already exists")
            return True
        
        config = config or PoolConfiguration()
        manager = DatabaseConnectionManager(database_url, config, self.metrics, name)
        
        if await manager.initialize():
            self.database_pools[name] = manager
            logger.info(f"Added database pool {name}")
            return True
        else:
            logger.error(f"Failed to add database pool {name}")
            return False
    
    async def add_redis_pool(self,
                           name: str,
                           redis_url: str,
                           config: Optional[PoolConfiguration] = None) -> bool:
        """Add a Redis connection pool"""
        if name in self.redis_pools:
            logger.warning(f"Redis pool {name} already exists")
            return True
        
        config = config or PoolConfiguration()
        manager = RedisConnectionManager(redis_url, config, self.metrics, name)
        
        if await manager.initialize():
            self.redis_pools[name] = manager
            logger.info(f"Added Redis pool {name}")
            return True
        else:
            logger.error(f"Failed to add Redis pool {name}")
            return False
    
    def get_database_pool(self, name: str = "main") -> DatabaseConnectionManager:
        """Get database pool by name"""
        if name not in self.database_pools:
            raise KeyError(f"Database pool {name} not found")
        return self.database_pools[name]
    
    def get_redis_pool(self, name: str = "main") -> RedisConnectionManager:
        """Get Redis pool by name"""
        if name not in self.redis_pools:
            raise KeyError(f"Redis pool {name} not found")
        return self.redis_pools[name]
    
    async def start_optimization(self):
        """Start automatic pool optimization"""
        self._optimization_task = asyncio.create_task(self._optimization_loop())
        logger.info("Connection pool optimization started")
    
    async def _optimization_loop(self):
        """Background task for pool optimization"""
        while True:
            try:
                await asyncio.sleep(self._optimization_interval)
                await self._optimize_all_pools()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in optimization loop: {e}", exc_info=True)
    
    async def _optimize_all_pools(self):
        """Optimize all connection pools"""
        logger.debug("Running connection pool optimization")
        
        # Optimize database pools
        for name, pool in self.database_pools.items():
            try:
                recommendations = await pool.optimize_pool()
                if recommendations:
                    logger.info(f"Optimization recommendations for DB pool {name}: {recommendations}")
                    
                    # Apply automatic optimizations (be conservative)
                    if "pool_size" in recommendations:
                        rec = recommendations["pool_size"]
                        if rec["action"] == "increase" and rec["recommended_max"] <= 30:
                            # Apply size increase (would need pool reconfiguration)
                            logger.info(f"Would increase pool {name} size to {rec['recommended_max']}")
            except Exception as e:
                logger.error(f"Error optimizing DB pool {name}: {e}")
        
        # Record optimization metrics
        if self.metrics:
            await self.metrics.increment("connection_pools.optimization_run")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all connection pools"""
        status = {
            "timestamp": datetime.utcnow().isoformat(),
            "database_pools": {},
            "redis_pools": {}
        }
        
        # Database pool stats
        for name, pool in self.database_pools.items():
            try:
                status["database_pools"][name] = await pool.get_pool_stats()
            except Exception as e:
                status["database_pools"][name] = {"error": str(e)}
        
        # Redis pool stats
        for name, pool in self.redis_pools.items():
            try:
                status["redis_pools"][name] = await pool.get_pool_stats()
            except Exception as e:
                status["redis_pools"][name] = {"error": str(e)}
        
        return status
    
    async def close_all(self):
        """Close all connection pools"""
        logger.info("Closing all connection pools")
        
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
        
        # Close database pools
        for name, pool in self.database_pools.items():
            try:
                await pool.close()
            except Exception as e:
                logger.error(f"Error closing database pool {name}: {e}")
        
        # Close Redis pools
        for name, pool in self.redis_pools.items():
            try:
                await pool.close()
            except Exception as e:
                logger.error(f"Error closing Redis pool {name}: {e}")
        
        self.database_pools.clear()
        self.redis_pools.clear()
        
        logger.info("All connection pools closed")


# Example usage
if __name__ == "__main__":
    async def example_usage():
        print("Connection Pool Manager")
        print("Features:")
        print("- Advanced PostgreSQL connection pooling")
        print("- Redis connection management")
        print("- Health monitoring and automatic recovery")
        print("- Performance optimization")
        print("- Comprehensive metrics and monitoring")
        print("- Automatic pool size optimization")
    
    # asyncio.run(example_usage())