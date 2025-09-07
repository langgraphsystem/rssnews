"""
Distributed tracing support for Stage 6 pipeline using OpenTelemetry.
"""

import asyncio
import functools
from contextlib import asynccontextmanager
from typing import Dict, Optional, Any, Callable
import time

import structlog
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

logger = structlog.get_logger(__name__)


class TracingManager:
    """Manages distributed tracing setup and configuration."""
    
    def __init__(self, 
                 service_name: str = "stage6-hybrid-chunking",
                 jaeger_endpoint: Optional[str] = None,
                 sample_rate: float = 0.1):
        
        self.service_name = service_name
        self.jaeger_endpoint = jaeger_endpoint
        self.sample_rate = sample_rate
        self._tracer_provider: Optional[TracerProvider] = None
        self._tracer: Optional[trace.Tracer] = None
        self._initialized = False
        
        logger.info("TracingManager created", 
                   service_name=service_name,
                   jaeger_endpoint=jaeger_endpoint,
                   sample_rate=sample_rate)
    
    def initialize(self) -> None:
        """Initialize OpenTelemetry tracing."""
        
        if self._initialized:
            logger.warning("TracingManager already initialized")
            return
        
        try:
            # Configure resource
            resource = Resource.create({
                ResourceAttributes.SERVICE_NAME: self.service_name,
                ResourceAttributes.SERVICE_VERSION: "1.0.0",
            })
            
            # Setup tracer provider
            self._tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(self._tracer_provider)
            
            # Setup Jaeger exporter if endpoint provided
            if self.jaeger_endpoint:
                jaeger_exporter = JaegerExporter(
                    endpoint=self.jaeger_endpoint,
                )
                span_processor = BatchSpanProcessor(jaeger_exporter)
                self._tracer_provider.add_span_processor(span_processor)
                logger.info("Jaeger exporter configured", endpoint=self.jaeger_endpoint)
            else:
                logger.info("No Jaeger endpoint provided, traces will not be exported")
            
            # Get tracer
            self._tracer = trace.get_tracer(__name__)
            
            # Instrument libraries
            self._instrument_libraries()
            
            self._initialized = True
            logger.info("Tracing initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize tracing", error=str(e))
            raise
    
    def _instrument_libraries(self) -> None:
        """Instrument common libraries for automatic tracing."""
        
        try:
            # Instrument SQLAlchemy
            SQLAlchemyInstrumentor().instrument()
            logger.debug("SQLAlchemy instrumented for tracing")
        except Exception as e:
            logger.warning("Failed to instrument SQLAlchemy", error=str(e))
        
        try:
            # Instrument HTTPX (for Gemini API calls)
            HTTPXClientInstrumentor().instrument()
            logger.debug("HTTPX instrumented for tracing")
        except Exception as e:
            logger.warning("Failed to instrument HTTPX", error=str(e))
    
    def get_tracer(self) -> Optional[trace.Tracer]:
        """Get the configured tracer."""
        if not self._initialized:
            logger.warning("TracingManager not initialized")
            return None
        return self._tracer
    
    @asynccontextmanager
    async def trace_operation(self, 
                            operation_name: str,
                            attributes: Optional[Dict[str, Any]] = None,
                            record_exception: bool = True):
        """Context manager for tracing an operation."""
        
        if not self._tracer:
            # No-op if tracing not initialized
            yield None
            return
        
        with self._tracer.start_as_current_span(operation_name) as span:
            try:
                # Set attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))
                
                start_time = time.time()
                yield span
                
                # Record success
                span.set_status(trace.Status(trace.StatusCode.OK))
                
            except Exception as e:
                # Record exception
                if record_exception:
                    span.record_exception(e)
                    span.set_status(trace.Status(
                        trace.StatusCode.ERROR,
                        description=str(e)
                    ))
                raise
            finally:
                # Record duration
                duration = time.time() - start_time
                span.set_attribute("duration_seconds", duration)
    
    def add_event(self, 
                  event_name: str, 
                  attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the current span."""
        
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.add_event(event_name, attributes or {})
    
    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the current span."""
        
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.set_attribute(key, str(value))
    
    def shutdown(self) -> None:
        """Shutdown tracing and flush pending spans."""
        
        if self._tracer_provider:
            self._tracer_provider.shutdown()
            logger.info("Tracing shutdown completed")


# Global tracing manager instance
_tracing_manager: Optional[TracingManager] = None


def initialize_tracing(service_name: str = "stage6-hybrid-chunking",
                      jaeger_endpoint: Optional[str] = None,
                      sample_rate: float = 0.1) -> TracingManager:
    """Initialize global tracing manager."""
    
    global _tracing_manager
    
    if _tracing_manager is not None:
        logger.warning("Tracing already initialized")
        return _tracing_manager
    
    _tracing_manager = TracingManager(
        service_name=service_name,
        jaeger_endpoint=jaeger_endpoint,
        sample_rate=sample_rate
    )
    _tracing_manager.initialize()
    
    return _tracing_manager


def get_tracing_manager() -> Optional[TracingManager]:
    """Get the global tracing manager."""
    return _tracing_manager


def trace_async_method(operation_name: Optional[str] = None,
                      record_args: bool = False,
                      record_result: bool = False):
    """Decorator for tracing async methods."""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            
            # Get operation name
            op_name = operation_name or f"{func.__module__}.{func.__qualname__}"
            
            # Get tracing manager
            tracing_manager = get_tracing_manager()
            if not tracing_manager:
                # No tracing configured, execute normally
                return await func(*args, **kwargs)
            
            # Prepare attributes
            attributes = {
                "function.name": func.__name__,
                "function.module": func.__module__,
            }
            
            if record_args and args:
                attributes["function.args_count"] = len(args)
            
            if record_args and kwargs:
                # Only record safe kwargs (avoid sensitive data)
                safe_kwargs = {
                    k: str(v) for k, v in kwargs.items()
                    if not any(sensitive in k.lower() 
                              for sensitive in ['password', 'token', 'key', 'secret'])
                }
                attributes.update({f"function.kwarg.{k}": v for k, v in safe_kwargs.items()})
            
            async with tracing_manager.trace_operation(op_name, attributes) as span:
                try:
                    result = await func(*args, **kwargs)
                    
                    if record_result and span:
                        # Record result metadata (not the actual result for privacy)
                        if hasattr(result, '__len__'):
                            span.set_attribute("result.length", len(result))
                        span.set_attribute("result.type", type(result).__name__)
                    
                    return result
                    
                except Exception as e:
                    if span:
                        span.set_attribute("error.type", type(e).__name__)
                    raise
        
        return wrapper
    return decorator


def trace_sync_method(operation_name: Optional[str] = None,
                     record_args: bool = False,
                     record_result: bool = False):
    """Decorator for tracing synchronous methods."""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            
            # Get operation name
            op_name = operation_name or f"{func.__module__}.{func.__qualname__}"
            
            # Get tracer
            tracing_manager = get_tracing_manager()
            if not tracing_manager or not tracing_manager.get_tracer():
                # No tracing configured, execute normally
                return func(*args, **kwargs)
            
            tracer = tracing_manager.get_tracer()
            
            # Prepare attributes
            attributes = {
                "function.name": func.__name__,
                "function.module": func.__module__,
            }
            
            if record_args and args:
                attributes["function.args_count"] = len(args)
            
            if record_args and kwargs:
                # Only record safe kwargs
                safe_kwargs = {
                    k: str(v) for k, v in kwargs.items()
                    if not any(sensitive in k.lower() 
                              for sensitive in ['password', 'token', 'key', 'secret'])
                }
                attributes.update({f"function.kwarg.{k}": v for k, v in safe_kwargs.items()})
            
            with tracer.start_as_current_span(op_name) as span:
                try:
                    # Set attributes
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))
                    
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    
                    # Record success and duration
                    duration = time.time() - start_time
                    span.set_attribute("duration_seconds", duration)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    
                    if record_result:
                        # Record result metadata
                        if hasattr(result, '__len__'):
                            span.set_attribute("result.length", len(result))
                        span.set_attribute("result.type", type(result).__name__)
                    
                    return result
                    
                except Exception as e:
                    # Record exception
                    span.record_exception(e)
                    span.set_status(trace.Status(
                        trace.StatusCode.ERROR,
                        description=str(e)
                    ))
                    span.set_attribute("error.type", type(e).__name__)
                    raise
        
        return wrapper
    return decorator


# Utility functions

def add_trace_event(event_name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add an event to the current trace span."""
    tracing_manager = get_tracing_manager()
    if tracing_manager:
        tracing_manager.add_event(event_name, attributes)


def set_trace_attribute(key: str, value: Any) -> None:
    """Set an attribute on the current trace span."""
    tracing_manager = get_tracing_manager()
    if tracing_manager:
        tracing_manager.set_attribute(key, value)


def get_trace_id() -> Optional[str]:
    """Get the current trace ID."""
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        trace_id = current_span.get_span_context().trace_id
        return format(trace_id, '032x')  # 32-character hex string
    return None


def get_span_id() -> Optional[str]:
    """Get the current span ID."""
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_id = current_span.get_span_context().span_id  
        return format(span_id, '016x')  # 16-character hex string
    return None


@asynccontextmanager
async def traced_operation(operation_name: str,
                          attributes: Optional[Dict[str, Any]] = None):
    """Async context manager for tracing operations."""
    
    tracing_manager = get_tracing_manager()
    if not tracing_manager:
        yield None
        return
    
    async with tracing_manager.trace_operation(operation_name, attributes) as span:
        yield span


def shutdown_tracing() -> None:
    """Shutdown global tracing."""
    global _tracing_manager
    
    if _tracing_manager:
        _tracing_manager.shutdown()
        _tracing_manager = None