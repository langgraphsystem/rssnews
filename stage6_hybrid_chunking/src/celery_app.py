"""
Celery application configuration for Stage 6 processing.
"""

from celery import Celery
from kombu import Queue
import structlog

from src.config.settings import Settings

logger = structlog.get_logger(__name__)

# Load settings
settings = Settings()

# Create Celery app
celery_app = Celery("stage6-hybrid-chunking")

# Configure Celery
celery_app.conf.update(
    # Broker settings (Redis)
    broker_url=settings.redis.url,
    result_backend=settings.redis.url,
    
    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # Task routing
    task_routes={
        'stage6.tasks.process_articles_task': {'queue': 'stage6_processing'},
        'stage6.tasks.health_check_task': {'queue': 'stage6_monitoring'},
        'stage6.tasks.cleanup_task': {'queue': 'stage6_maintenance'},
    },
    
    # Queue configuration
    task_default_queue='stage6_default',
    task_queues=(
        Queue('stage6_default', routing_key='stage6.default'),
        Queue('stage6_processing', routing_key='stage6.processing'),
        Queue('stage6_monitoring', routing_key='stage6.monitoring'),
        Queue('stage6_maintenance', routing_key='stage6.maintenance'),
    ),
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Disable prefetching for fair distribution
    task_acks_late=True,  # Acknowledge tasks after completion
    worker_disable_rate_limits=False,
    
    # Task execution
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 minute soft limit
    task_max_retries=3,
    task_default_retry_delay=300,  # 5 minutes
    
    # Results
    result_expires=86400,  # 24 hours
    result_persistent=True,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Database connections (if using database result backend)
    database_table_schemas={
        'task': 'celery_tasks',
        'group': 'celery_tasksets',
    },
    
    # Security
    worker_hijack_root_logger=False,
    worker_log_color=False,
    
    # Beat scheduler (for periodic tasks)
    beat_schedule={
        'health-check-every-5-minutes': {
            'task': 'stage6.tasks.health_check_task',
            'schedule': 300.0,  # 5 minutes
        },
        'cleanup-old-results-daily': {
            'task': 'stage6.tasks.cleanup_task',
            'schedule': 86400.0,  # 24 hours
        },
    },
    timezone='UTC',
)

# Import tasks to register them
from src.tasks import tasks  # noqa

logger.info("Celery app configured", 
           broker=settings.redis.url,
           queues=['stage6_default', 'stage6_processing', 'stage6_monitoring', 'stage6_maintenance'])


if __name__ == '__main__':
    celery_app.start()