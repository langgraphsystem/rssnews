"""
Health checking system for Stage 6 pipeline components.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import time

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"  
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'status': self.status.value,
            'message': self.message,
            'details': self.details,
            'duration_ms': self.duration_ms,
            'timestamp': self.timestamp.isoformat()
        }


class HealthChecker:
    """
    Comprehensive health checking system for Stage 6 pipeline.
    
    Features:
    - Database connectivity checks
    - LLM API availability checks
    - Resource utilization monitoring
    - Component-specific health checks
    - Configurable thresholds and timeouts
    """
    
    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds
        self.checks: Dict[str, Callable] = {}
        self.last_results: Dict[str, HealthCheckResult] = {}
        
        # Register default health checks
        self._register_default_checks()
        
        logger.info("HealthChecker initialized", timeout_seconds=timeout_seconds)
    
    def _register_default_checks(self) -> None:
        """Register default health checks."""
        self.register_check("system_time", self._check_system_time)
        self.register_check("memory_usage", self._check_memory_usage)
    
    def register_check(self, name: str, check_func: Callable) -> None:
        """Register a health check function."""
        self.checks[name] = check_func
        logger.debug("Health check registered", name=name)
    
    async def check_all(self) -> Dict[str, HealthCheckResult]:
        """Run all registered health checks."""
        results = {}
        
        # Run checks concurrently
        tasks = []
        for name, check_func in self.checks.items():
            task = asyncio.create_task(self._run_check(name, check_func))
            tasks.append(task)
        
        # Wait for all checks to complete
        completed_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(completed_results):
            name = list(self.checks.keys())[i]
            
            if isinstance(result, Exception):
                results[name] = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(result)}"
                )
            else:
                results[name] = result
                self.last_results[name] = result
        
        return results
    
    async def check_single(self, check_name: str) -> Optional[HealthCheckResult]:
        """Run a single health check."""
        if check_name not in self.checks:
            logger.warning("Health check not found", name=check_name)
            return None
        
        try:
            result = await self._run_check(check_name, self.checks[check_name])
            self.last_results[check_name] = result
            return result
        except Exception as e:
            logger.error("Health check failed", name=check_name, error=str(e))
            result = HealthCheckResult(
                name=check_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}"
            )
            self.last_results[check_name] = result
            return result
    
    async def _run_check(self, name: str, check_func: Callable) -> HealthCheckResult:
        """Run a single health check with timeout."""
        start_time = time.time()
        
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                self._execute_check(check_func),
                timeout=self.timeout_seconds
            )
            
            duration_ms = (time.time() - start_time) * 1000
            result.duration_ms = duration_ms
            
            return result
            
        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check timed out after {self.timeout_seconds}s",
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                duration_ms=duration_ms
            )
    
    async def _execute_check(self, check_func: Callable) -> HealthCheckResult:
        """Execute a health check function."""
        if asyncio.iscoroutinefunction(check_func):
            return await check_func()
        else:
            return check_func()
    
    async def _check_system_time(self) -> HealthCheckResult:
        """Basic system time health check."""
        current_time = datetime.utcnow()
        
        return HealthCheckResult(
            name="system_time",
            status=HealthStatus.HEALTHY,
            message="System time is available",
            details={'current_time': current_time.isoformat()}
        )
    
    async def _check_memory_usage(self) -> HealthCheckResult:
        """Basic memory usage check."""
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            if memory_percent > 90:
                status = HealthStatus.UNHEALTHY
                message = f"High memory usage: {memory_percent:.1f}%"
            elif memory_percent > 80:
                status = HealthStatus.DEGRADED
                message = f"Elevated memory usage: {memory_percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory_percent:.1f}%"
            
            return HealthCheckResult(
                name="memory_usage",
                status=status,
                message=message,
                details={
                    'memory_percent': memory_percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'memory_total_gb': memory.total / (1024**3)
                }
            )
            
        except ImportError:
            return HealthCheckResult(
                name="memory_usage",
                status=HealthStatus.UNKNOWN,
                message="psutil not available for memory monitoring"
            )
    
    def get_overall_health(self) -> HealthStatus:
        """Get overall health status from all checks."""
        if not self.last_results:
            return HealthStatus.UNKNOWN
        
        statuses = [result.status for result in self.last_results.values()]
        
        # If any check is unhealthy, overall is unhealthy
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        
        # If any check is degraded, overall is degraded
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        
        # If all checks are healthy, overall is healthy
        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        
        # Mixed or unknown states
        return HealthStatus.UNKNOWN
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary."""
        overall_status = self.get_overall_health()
        
        summary = {
            'overall_status': overall_status.value,
            'total_checks': len(self.checks),
            'last_check_time': None,
            'checks': {}
        }
        
        if self.last_results:
            # Find most recent check time
            latest_time = max(result.timestamp for result in self.last_results.values())
            summary['last_check_time'] = latest_time.isoformat()
            
            # Add individual check results
            for name, result in self.last_results.items():
                summary['checks'][name] = result.to_dict()
        
        return summary


class DatabaseHealthChecker:
    """Database-specific health checks."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
    
    async def check_connection(self) -> HealthCheckResult:
        """Check database connectivity."""
        try:
            # Simple connectivity test
            result = await self.db_session.execute(text("SELECT 1"))
            row = result.fetchone()
            
            if row and row[0] == 1:
                return HealthCheckResult(
                    name="database_connection",
                    status=HealthStatus.HEALTHY,
                    message="Database connection successful"
                )
            else:
                return HealthCheckResult(
                    name="database_connection",
                    status=HealthStatus.UNHEALTHY,
                    message="Database query returned unexpected result"
                )
                
        except Exception as e:
            return HealthCheckResult(
                name="database_connection",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}"
            )
    
    async def check_tables(self, required_tables: List[str] = None) -> HealthCheckResult:
        """Check if required tables exist."""
        required_tables = required_tables or ['articles', 'article_chunks']
        
        try:
            missing_tables = []
            
            for table_name in required_tables:
                result = await self.db_session.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table)")
                )
                exists = result.scalar()
                
                if not exists:
                    missing_tables.append(table_name)
            
            if missing_tables:
                return HealthCheckResult(
                    name="database_tables",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Missing tables: {', '.join(missing_tables)}",
                    details={'missing_tables': missing_tables}
                )
            else:
                return HealthCheckResult(
                    name="database_tables",
                    status=HealthStatus.HEALTHY,
                    message=f"All {len(required_tables)} required tables exist",
                    details={'checked_tables': required_tables}
                )
                
        except Exception as e:
            return HealthCheckResult(
                name="database_tables", 
                status=HealthStatus.UNHEALTHY,
                message=f"Table check failed: {str(e)}"
            )


class LLMHealthChecker:
    """LLM API specific health checks."""
    
    def __init__(self, gemini_client):
        self.gemini_client = gemini_client
    
    async def check_api_availability(self) -> HealthCheckResult:
        """Check if LLM API is available."""
        if not self.gemini_client:
            return HealthCheckResult(
                name="llm_api",
                status=HealthStatus.UNKNOWN,
                message="LLM client not configured"
            )
        
        try:
            # Use the client's built-in health check
            is_healthy = await self.gemini_client.health_check()
            
            if is_healthy:
                stats = self.gemini_client.get_stats()
                return HealthCheckResult(
                    name="llm_api",
                    status=HealthStatus.HEALTHY,
                    message="LLM API is responding",
                    details={
                        'total_requests': stats.get('total_requests', 0),
                        'circuit_breaker_state': stats.get('circuit_breaker_state', 'unknown')
                    }
                )
            else:
                return HealthCheckResult(
                    name="llm_api",
                    status=HealthStatus.UNHEALTHY,
                    message="LLM API health check failed"
                )
                
        except Exception as e:
            return HealthCheckResult(
                name="llm_api",
                status=HealthStatus.UNHEALTHY,
                message=f"LLM API check failed: {str(e)}"
            )
    
    async def check_circuit_breaker(self) -> HealthCheckResult:
        """Check LLM circuit breaker status."""
        if not self.gemini_client:
            return HealthCheckResult(
                name="llm_circuit_breaker",
                status=HealthStatus.UNKNOWN,
                message="LLM client not configured"
            )
        
        try:
            stats = self.gemini_client.get_stats()
            cb_state = stats.get('circuit_breaker_state', 'unknown')
            failure_count = stats.get('circuit_breaker_failures', 0)
            
            if cb_state == 'closed':
                status = HealthStatus.HEALTHY
                message = "Circuit breaker closed (normal operation)"
            elif cb_state == 'half_open':
                status = HealthStatus.DEGRADED
                message = "Circuit breaker half-open (testing recovery)"
            elif cb_state == 'open':
                status = HealthStatus.UNHEALTHY
                message = f"Circuit breaker open ({failure_count} failures)"
            else:
                status = HealthStatus.UNKNOWN
                message = f"Circuit breaker state unknown: {cb_state}"
            
            return HealthCheckResult(
                name="llm_circuit_breaker",
                status=status,
                message=message,
                details={
                    'state': cb_state,
                    'failure_count': failure_count
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="llm_circuit_breaker",
                status=HealthStatus.UNHEALTHY,
                message=f"Circuit breaker check failed: {str(e)}"
            )


# Utility functions

def create_stage6_health_checker(db_session: Optional[AsyncSession] = None,
                                gemini_client = None,
                                timeout_seconds: float = 5.0) -> HealthChecker:
    """Create a health checker with Stage 6 specific checks."""
    
    health_checker = HealthChecker(timeout_seconds=timeout_seconds)
    
    # Add database checks if session provided
    if db_session:
        db_checker = DatabaseHealthChecker(db_session)
        health_checker.register_check("database_connection", db_checker.check_connection)
        health_checker.register_check("database_tables", db_checker.check_tables)
    
    # Add LLM checks if client provided
    if gemini_client:
        llm_checker = LLMHealthChecker(gemini_client)
        health_checker.register_check("llm_api", llm_checker.check_api_availability)
        health_checker.register_check("llm_circuit_breaker", llm_checker.check_circuit_breaker)
    
    return health_checker