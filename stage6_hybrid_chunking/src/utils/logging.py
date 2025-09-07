"""
Structured logging configuration for Stage 6 pipeline.
"""

import json
import logging
import sys
from typing import Dict, Any, Optional
from datetime import datetime

import structlog
from structlog.types import Processor

from src.utils.tracing import get_trace_id, get_span_id


def add_trace_context(logger, method_name, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add trace context to log events."""
    
    trace_id = get_trace_id()
    span_id = get_span_id()
    
    if trace_id:
        event_dict['trace_id'] = trace_id
    
    if span_id:
        event_dict['span_id'] = span_id
    
    return event_dict


def add_service_context(logger, method_name, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add service context to log events."""
    
    event_dict.update({
        'service': 'stage6-hybrid-chunking',
        'version': '1.0.0',
        'component': event_dict.get('component', 'unknown')
    })
    
    return event_dict


def add_timestamp(logger, method_name, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add ISO timestamp to log events."""
    
    event_dict['timestamp'] = datetime.utcnow().isoformat() + 'Z'
    return event_dict


def filter_sensitive_data(logger, method_name, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Filter out sensitive data from logs."""
    
    sensitive_keys = {
        'password', 'token', 'key', 'secret', 'api_key', 
        'auth', 'authorization', 'credential', 'private'
    }
    
    def clean_dict(d: Dict) -> Dict:
        """Recursively clean sensitive data from dictionary."""
        cleaned = {}
        for k, v in d.items():
            key_lower = k.lower()
            
            # Check if key contains sensitive words
            is_sensitive = any(sensitive_word in key_lower for sensitive_word in sensitive_keys)
            
            if is_sensitive:
                cleaned[k] = '[REDACTED]'
            elif isinstance(v, dict):
                cleaned[k] = clean_dict(v)
            elif isinstance(v, str) and len(v) > 50:
                # Truncate very long strings to avoid log bloat
                cleaned[k] = v[:47] + '...'
            else:
                cleaned[k] = v
        
        return cleaned
    
    # Clean the event dict
    return clean_dict(event_dict)


def format_json_logs(logger, method_name, event_dict: Dict[str, Any]) -> str:
    """Format logs as JSON."""
    
    # Ensure event is a string
    event = event_dict.pop('event', '')
    log_record = {
        'message': event,
        **event_dict
    }
    
    return json.dumps(log_record, default=str, separators=(',', ':'))


def format_console_logs(logger, method_name, event_dict: Dict[str, Any]) -> str:
    """Format logs for console output."""
    
    timestamp = event_dict.get('timestamp', datetime.utcnow().isoformat())
    level = event_dict.get('level', 'INFO').upper()
    component = event_dict.get('component', 'stage6')
    event = event_dict.get('event', '')
    
    # Build base message
    message_parts = [f"[{timestamp}]", f"[{level}]", f"[{component}]", event]
    
    # Add key context fields
    context_fields = ['trace_id', 'span_id', 'job_id', 'batch_id', 'article_id']
    context = []
    
    for field in context_fields:
        if field in event_dict:
            value = event_dict[field]
            context.append(f"{field}={value}")
    
    if context:
        message_parts.append(f"({', '.join(context)})")
    
    # Add additional fields (excluding already shown ones)
    excluded_fields = {
        'timestamp', 'level', 'component', 'event', 'service', 'version'
    } | set(context_fields)
    
    extra_fields = []
    for k, v in event_dict.items():
        if k not in excluded_fields and not k.startswith('_'):
            extra_fields.append(f"{k}={v}")
    
    if extra_fields:
        message_parts.append(' '.join(extra_fields))
    
    return ' '.join(message_parts)


def configure_logging(log_level: str = "INFO",
                     log_format: str = "json", 
                     enable_tracing: bool = True) -> None:
    """
    Configure structured logging for Stage 6 pipeline.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ("json" or "console")
        enable_tracing: Whether to include trace context
    """
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    
    # Configure structlog processors
    processors = [
        structlog.stdlib.filter_by_level,
        add_service_context,
        add_timestamp,
    ]
    
    # Add trace context if enabled
    if enable_tracing:
        processors.append(add_trace_context)
    
    # Add sensitive data filtering
    processors.append(filter_sensitive_data)
    
    # Add appropriate formatter
    if log_format.lower() == "json":
        processors.append(format_json_logs)
    else:
        processors.append(format_console_logs)
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set up root logger for third-party libraries
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Adjust specific logger levels
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    # Create a test log to verify configuration
    logger = structlog.get_logger(__name__)
    logger.info("Logging configured successfully", 
               log_level=log_level, 
               log_format=log_format,
               enable_tracing=enable_tracing)


class LoggingContext:
    """Context manager for adding context to logs within a block."""
    
    def __init__(self, **context):
        self.context = context
        self.logger = structlog.get_logger()
    
    def __enter__(self):
        self.bound_logger = self.logger.bind(**self.context)
        return self.bound_logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.bound_logger.error("Exception occurred in logging context",
                                  exc_type=exc_type.__name__,
                                  exc_message=str(exc_val))


class ComponentLogger:
    """Component-specific logger with bound context."""
    
    def __init__(self, component: str, **extra_context):
        self.component = component
        self.extra_context = extra_context
        self.logger = structlog.get_logger().bind(
            component=component,
            **extra_context
        )
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.logger.critical(message, **kwargs)
    
    def bind(self, **kwargs):
        """Create a new logger with additional context."""
        return ComponentLogger(
            self.component,
            **self.extra_context,
            **kwargs
        )


# Pre-configured component loggers

def get_pipeline_logger() -> ComponentLogger:
    """Get logger for pipeline operations."""
    return ComponentLogger("pipeline")


def get_chunker_logger() -> ComponentLogger:
    """Get logger for chunking operations."""
    return ComponentLogger("chunker")


def get_llm_logger() -> ComponentLogger:
    """Get logger for LLM operations."""
    return ComponentLogger("llm")


def get_database_logger() -> ComponentLogger:
    """Get logger for database operations."""
    return ComponentLogger("database")


def get_metrics_logger() -> ComponentLogger:
    """Get logger for metrics operations."""
    return ComponentLogger("metrics")


# Utility functions

def log_performance(operation_name: str, duration_seconds: float, **extra_context):
    """Log performance metrics."""
    logger = structlog.get_logger("performance")
    
    level = "info"
    if duration_seconds > 30:
        level = "warning"
    elif duration_seconds > 60:
        level = "error"
    
    getattr(logger, level)(
        f"{operation_name} completed",
        operation=operation_name,
        duration_seconds=duration_seconds,
        **extra_context
    )


def log_error_with_context(error: Exception, 
                          operation: str,
                          **context):
    """Log error with full context."""
    logger = structlog.get_logger("error")
    
    logger.error(
        f"Error in {operation}",
        operation=operation,
        error_type=type(error).__name__,
        error_message=str(error),
        **context
    )


def log_batch_summary(batch_id: str,
                     articles_processed: int,
                     chunks_created: int,
                     processing_time_seconds: float,
                     errors: int = 0,
                     **extra_context):
    """Log batch processing summary."""
    logger = ComponentLogger("batch_processor")
    
    logger.info("Batch processing completed",
               batch_id=batch_id,
               articles_processed=articles_processed,
               chunks_created=chunks_created,
               processing_time_seconds=processing_time_seconds,
               errors=errors,
               articles_per_second=articles_processed / max(1, processing_time_seconds),
               chunks_per_article=chunks_created / max(1, articles_processed),
               **extra_context)