"""
Production RSS Processing System - Main Entry Point
Complete integration of all components with production-ready initialization, monitoring, and management.
"""

import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse

# Import all system components
from batch_planner import BatchPlanner, BatchConfiguration, BatchPriority
from pipeline_processor import PipelineProcessor
from monitoring import MetricsCollector, AlertManager, DashboardMetrics
from task_queue import TaskScheduler, celery_app
from throttling import BackpressureManager, CircuitBreaker, RateLimiter
from connection_manager import ConnectionPoolManager, PoolConfiguration
from configuration import ConfigurationManager, SystemConfig, DEFAULT_CONFIG_TEMPLATE

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/rss_pipeline.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


class ProductionRSSSystem:
    """
    Main production RSS processing system
    Orchestrates all components and provides unified management interface
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Core components
        self.config_manager: Optional[ConfigurationManager] = None
        self.connection_manager: Optional[ConnectionPoolManager] = None
        self.metrics: Optional[MetricsCollector] = None
        self.alert_manager: Optional[AlertManager] = None
        self.backpressure_manager: Optional[BackpressureManager] = None
        self.batch_planner: Optional[BatchPlanner] = None
        self.pipeline_processor: Optional[PipelineProcessor] = None
        self.task_scheduler: Optional[TaskScheduler] = None
        self.dashboard: Optional[DashboardMetrics] = None
        
        # System state
        self.system_id = f"rss_system_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.startup_time: Optional[datetime] = None
        
    async def initialize(self) -> bool:
        """
        Initialize all system components
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"🚀 Initializing Production RSS Processing System ({self.system_id})")
            
            # 1. Initialize configuration management
            if not await self._initialize_configuration():
                return False
            
            # 2. Initialize connection pools
            if not await self._initialize_connections():
                return False
            
            # 3. Initialize monitoring and metrics
            if not await self._initialize_monitoring():
                return False
            
            # 4. Initialize throttling and backpressure
            if not await self._initialize_throttling():
                return False
            
            # 5. Initialize batch planning
            if not await self._initialize_batch_planning():
                return False
            
            # 6. Initialize pipeline processing
            if not await self._initialize_pipeline():
                return False
            
            # 7. Initialize task scheduling
            if not await self._initialize_task_scheduling():
                return False
            
            # 8. Initialize dashboard
            if not await self._initialize_dashboard():
                return False
            
            # 9. Setup signal handlers
            self._setup_signal_handlers()
            
            # 10. Perform initial health checks
            if not await self._perform_health_checks():
                logger.error("Initial health checks failed")
                return False
            
            self.startup_time = datetime.utcnow()
            logger.info("✅ Production RSS Processing System initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize system: {e}", exc_info=True)
            return False
    
    async def _initialize_configuration(self) -> bool:
        """Initialize configuration management"""
        try:
            logger.info("📋 Initializing configuration management...")
            
            self.config_manager = ConfigurationManager()
            
            if self.config_path and Path(self.config_path).exists():
                # Load from specified file
                success = await self.config_manager.load_config_from_file(self.config_path)
                if not success:
                    logger.warning(f"Failed to load config from {self.config_path}, using defaults")
                    return await self._create_default_config()
            else:
                # Try to load from database first, then create default
                success = await self.config_manager.load_config_from_database()
                if not success:
                    logger.info("No existing configuration found, creating default")
                    return await self._create_default_config()
            
            # Register configuration change callback
            self.config_manager.register_change_callback(self._on_config_changed)
            
            logger.info("✅ Configuration management initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Configuration initialization failed: {e}", exc_info=True)
            return False
    
    async def _create_default_config(self) -> bool:
        """Create default configuration"""
        try:
            # Create default config from template
            from configuration import SystemConfig
            
            default_config = SystemConfig(**DEFAULT_CONFIG_TEMPLATE)
            
            # Save to temporary file and load
            config_file = Path("config_default.json")
            with open(config_file, 'w') as f:
                import json
                json.dump(default_config.dict(), f, indent=2, default=str)
            
            return await self.config_manager.load_config_from_file(config_file)
            
        except Exception as e:
            logger.error(f"Failed to create default config: {e}", exc_info=True)
            return False
    
    async def _initialize_connections(self) -> bool:
        """Initialize database and Redis connections"""
        try:
            logger.info("🔌 Initializing connection pools...")
            
            config = self.config_manager.get_config()
            if not config:
                logger.error("Configuration not loaded")
                return False
            
            self.connection_manager = ConnectionPoolManager()
            
            # Initialize database pool
            db_config = PoolConfiguration(
                min_size=config.database.pool_min_size,
                max_size=config.database.pool_max_size,
                idle_timeout=config.database.pool_timeout,
                command_timeout=config.database.command_timeout
            )
            
            db_success = await self.connection_manager.add_database_pool(
                "main",
                config.database.get_connection_url(),
                db_config
            )
            
            if not db_success:
                logger.error("Failed to initialize database pool")
                return False
            
            # Initialize Redis pool
            redis_config = PoolConfiguration(
                max_size=config.redis.max_connections,
                command_timeout=config.redis.socket_timeout
            )
            
            redis_success = await self.connection_manager.add_redis_pool(
                "main",
                config.redis.get_connection_url(),
                redis_config
            )
            
            if not redis_success:
                logger.error("Failed to initialize Redis pool")
                return False
            
            # Start connection optimization
            await self.connection_manager.start_optimization()
            
            logger.info("✅ Connection pools initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Connection initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_monitoring(self) -> bool:
        """Initialize monitoring, metrics, and alerting"""
        try:
            logger.info("📊 Initializing monitoring system...")
            
            config = self.config_manager.get_config()
            
            # Get Redis client for metrics
            redis_client = self.connection_manager.get_redis_pool("main").get_client()
            
            # Get database pool for metrics storage
            db_pool = self.connection_manager.get_database_pool("main")._pool
            
            # Initialize metrics collector
            self.metrics = MetricsCollector(
                redis_client=redis_client,
                db_pool=db_pool,
                buffer_size=config.monitoring.metrics_buffer_size,
                flush_interval_seconds=config.monitoring.metrics_flush_interval
            )
            
            await self.metrics.initialize()
            
            # Initialize alert manager
            self.alert_manager = AlertManager(
                metrics_collector=self.metrics,
                redis_client=redis_client,
                db_pool=db_pool
            )
            
            await self.alert_manager.initialize()
            
            # Setup alert notification handlers
            from monitoring import email_notification_handler, slack_notification_handler
            self.alert_manager.register_notification_handler("email", email_notification_handler)
            self.alert_manager.register_notification_handler("slack", slack_notification_handler)
            
            logger.info("✅ Monitoring system initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Monitoring initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_throttling(self) -> bool:
        """Initialize throttling and backpressure management"""
        try:
            logger.info("🚦 Initializing throttling and backpressure...")
            
            # Get required components
            redis_client = self.connection_manager.get_redis_pool("main").get_client()
            db_pool = self.connection_manager.get_database_pool("main")._pool
            
            # Initialize backpressure manager
            self.backpressure_manager = BackpressureManager(
                redis_client=redis_client,
                metrics=self.metrics,
                db_pool=db_pool
            )
            
            # Start monitoring
            await self.backpressure_manager.start_monitoring()
            
            logger.info("✅ Throttling and backpressure initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Throttling initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_batch_planning(self) -> bool:
        """Initialize batch planning system"""
        try:
            logger.info("📦 Initializing batch planning...")
            
            # Get required components
            db_pool = self.connection_manager.get_database_pool("main")._pool
            redis_client = self.connection_manager.get_redis_pool("main").get_client()
            config = self.config_manager.get_config()
            
            # Initialize batch planner
            self.batch_planner = BatchPlanner(
                db_pool=db_pool,
                redis_client=redis_client,
                metrics=self.metrics,
                config=self.config_manager
            )
            
            logger.info("✅ Batch planning initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Batch planning initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_pipeline(self) -> bool:
        """Initialize pipeline processing"""
        try:
            logger.info("⚙️ Initializing pipeline processor...")
            
            # Get required components
            db_pool = self.connection_manager.get_database_pool("main")._pool
            redis_client = self.connection_manager.get_redis_pool("main").get_client()
            
            # Initialize pipeline processor
            self.pipeline_processor = PipelineProcessor(
                db_pool=db_pool,
                redis_client=redis_client,
                metrics=self.metrics,
                config=self.config_manager
            )
            
            logger.info("✅ Pipeline processor initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Pipeline initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_task_scheduling(self) -> bool:
        """Initialize task scheduling"""
        try:
            logger.info("⏰ Initializing task scheduler...")
            
            # Get required components
            redis_client = self.connection_manager.get_redis_pool("main").get_client()
            
            # Initialize task scheduler
            self.task_scheduler = TaskScheduler(
                redis_client=redis_client,
                metrics=self.metrics,
                config=self.config_manager
            )
            
            # Start scheduler
            await self.task_scheduler.start()
            
            logger.info("✅ Task scheduler initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Task scheduling initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_dashboard(self) -> bool:
        """Initialize dashboard metrics"""
        try:
            logger.info("📈 Initializing dashboard...")
            
            # Initialize dashboard metrics
            self.dashboard = DashboardMetrics(
                metrics_collector=self.metrics,
                alert_manager=self.alert_manager
            )
            
            logger.info("✅ Dashboard initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Dashboard initialization failed: {e}", exc_info=True)
            return False
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"🛑 Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)
    
    async def _perform_health_checks(self) -> bool:
        """Perform initial health checks"""
        try:
            logger.info("🏥 Performing health checks...")
            
            # Check database connectivity
            db_pool = self.connection_manager.get_database_pool("main")
            async with db_pool.acquire_connection() as conn:
                await conn.fetchval("SELECT 1")
            
            # Check Redis connectivity
            redis_client = self.connection_manager.get_redis_pool("main").get_client()
            await redis_client.ping()
            
            # Check pipeline components
            config = self.config_manager.get_config()
            if not config:
                raise ValueError("Configuration not loaded")
            
            logger.info("✅ Health checks passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}", exc_info=True)
            return False
    
    async def _on_config_changed(self, old_config: SystemConfig, new_config: SystemConfig):
        """Handle configuration changes"""
        try:
            logger.info("🔄 Configuration changed, applying updates...")
            
            # Update log level if changed
            if old_config and old_config.log_level != new_config.log_level:
                logging.getLogger().setLevel(getattr(logging, new_config.log_level))
                logger.info(f"Log level updated to {new_config.log_level}")
            
            # Record configuration change
            if self.metrics:
                await self.metrics.increment("system.config_changed")
            
            logger.info("✅ Configuration changes applied")
            
        except Exception as e:
            logger.error(f"❌ Failed to apply configuration changes: {e}", exc_info=True)
    
    async def run(self):
        """Main system run loop"""
        try:
            self.running = True
            logger.info(f"🏃 Production RSS System running (ID: {self.system_id})")
            
            # Record system startup
            if self.metrics:
                await self.metrics.increment("system.startup")
                await self.metrics.gauge("system.running", 1)
            
            # Main run loop
            while self.running and not self.shutdown_event.is_set():
                try:
                    # Periodic system health monitoring
                    await self._monitor_system_health()
                    
                    # Wait for shutdown signal or timeout
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=60)
                    
                except asyncio.TimeoutError:
                    # Normal timeout - continue monitoring
                    continue
                except Exception as e:
                    logger.error(f"Error in main run loop: {e}", exc_info=True)
                    await asyncio.sleep(10)  # Brief pause before retrying
            
            logger.info("🛑 Main run loop exiting")
            
        except Exception as e:
            logger.error(f"❌ Critical error in run loop: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def _monitor_system_health(self):
        """Monitor overall system health"""
        try:
            # Get system status
            connection_status = await self.connection_manager.get_system_status()
            backpressure_status = await self.backpressure_manager.get_system_status()
            config_status = self.config_manager.get_status()
            
            # Record key health metrics
            if self.metrics:
                await self.metrics.gauge("system.health.connections_healthy", 
                                       1 if all(pool.get("pool_state") == "healthy" 
                                              for pool in connection_status.get("database_pools", {}).values()) else 0)
                
                await self.metrics.gauge("system.health.config_loaded", 
                                       1 if config_status["config_loaded"] else 0)
                
                await self.metrics.gauge("system.uptime_seconds", 
                                       (datetime.utcnow() - self.startup_time).total_seconds() if self.startup_time else 0)
            
        except Exception as e:
            logger.error(f"Error monitoring system health: {e}", exc_info=True)
    
    async def get_system_status(self) -> dict:
        """Get comprehensive system status"""
        try:
            status = {
                "system_id": self.system_id,
                "running": self.running,
                "startup_time": self.startup_time.isoformat() if self.startup_time else None,
                "uptime_seconds": (datetime.utcnow() - self.startup_time).total_seconds() if self.startup_time else 0
            }
            
            # Component statuses
            if self.config_manager:
                status["configuration"] = self.config_manager.get_status()
            
            if self.connection_manager:
                status["connections"] = await self.connection_manager.get_system_status()
            
            if self.metrics:
                status["metrics"] = self.metrics.get_stats()
            
            if self.backpressure_manager:
                status["backpressure"] = await self.backpressure_manager.get_system_status()
            
            if self.dashboard:
                status["dashboard"] = {
                    "system_overview": await self.dashboard.get_system_overview(),
                    "pipeline_metrics": await self.dashboard.get_pipeline_metrics(),
                    "feed_metrics": await self.dashboard.get_feed_metrics()
                }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def create_emergency_batch(self, max_size: int = 50) -> Optional[str]:
        """Create emergency batch for urgent processing"""
        try:
            if not self.batch_planner:
                logger.error("Batch planner not initialized")
                return None
            
            from batch_planner import create_emergency_batch
            batch_id = await create_emergency_batch(
                self.batch_planner,
                f"emergency_{self.system_id}",
                max_size
            )
            
            if batch_id:
                logger.warning(f"Emergency batch created: {batch_id}")
                if self.metrics:
                    await self.metrics.increment("system.emergency_batch_created")
            
            return batch_id
            
        except Exception as e:
            logger.error(f"Failed to create emergency batch: {e}", exc_info=True)
            return None
    
    async def shutdown(self):
        """Graceful system shutdown"""
        try:
            logger.info("🛑 Initiating graceful shutdown...")
            self.running = False
            
            shutdown_start = datetime.utcnow()
            
            # Record shutdown start
            if self.metrics:
                await self.metrics.increment("system.shutdown_initiated")
                await self.metrics.gauge("system.running", 0)
            
            # Shutdown components in reverse order of initialization
            if self.task_scheduler:
                logger.info("Stopping task scheduler...")
                await self.task_scheduler.stop()
            
            if self.backpressure_manager:
                logger.info("Stopping backpressure monitoring...")
                self.backpressure_manager.backpressure_enabled = False
            
            if self.alert_manager:
                logger.info("Shutting down alert manager...")
                await self.alert_manager.shutdown()
            
            if self.metrics:
                logger.info("Shutting down metrics collector...")
                await self.metrics.shutdown()
            
            if self.connection_manager:
                logger.info("Closing connection pools...")
                await self.connection_manager.close_all()
            
            if self.config_manager:
                logger.info("Closing configuration manager...")
                await self.config_manager.close()
            
            shutdown_time = (datetime.utcnow() - shutdown_start).total_seconds()
            logger.info(f"✅ Graceful shutdown completed in {shutdown_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}", exc_info=True)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Production RSS Processing System")
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument("--mode", "-m", choices=["worker", "scheduler", "full"], 
                       default="full", help="Run mode")
    parser.add_argument("--log-level", "-l", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       default="INFO", help="Log level")
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)
    
    # Initialize and run system
    system = ProductionRSSSystem(config_path=args.config)
    
    try:
        # Initialize system
        if not await system.initialize():
            logger.error("❌ System initialization failed")
            sys.exit(1)
        
        # Run based on mode
        if args.mode == "full":
            # Run complete system
            await system.run()
        elif args.mode == "worker":
            # Run only as Celery worker
            logger.info("🔧 Running in worker mode - start Celery separately")
            await system.run()
        elif args.mode == "scheduler":
            # Run only task scheduler
            logger.info("⏰ Running in scheduler mode")
            await system.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.error(f"❌ System error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("👋 System shutdown complete")


if __name__ == "__main__":
    # Ensure proper event loop policy on Windows
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())