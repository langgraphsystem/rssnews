"""
Service manager for coordinating RSS News services
"""

import os
import sys
import asyncio
import logging
import signal
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pg_client_new import PgClient
from config import load_config
from services.chunking_service import ChunkingService
from services.fts_service import FTSService
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages and coordinates all RSS News services"""

    def __init__(self, db_client: Optional[PgClient] = None):
        self.db = db_client or PgClient()
        self.services = {}
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        # Default batch sizes (overridable from CLI)
        # Chunking: 100 articles per pass; Embeddings: 200 chunks per pass
        self.chunking_batch_size: int = 100
        self.embedding_batch_size: int = 200

        # Initialize services
        self.chunking_service = ChunkingService(self.db)
        self.fts_service = FTSService(self.db)
        self.embedding_service = EmbeddingService(self.db)

        # Service configurations
        self.service_configs = {
            'chunking': {
                'service': self.chunking_service,
                'interval': 30,
                'enabled': os.getenv("ENABLE_LOCAL_CHUNKING", "true").lower() == "true"
            },
            'fts': {
                'service': self.fts_service,
                'interval': 60,
                'enabled': True
            },
            'embedding': {
                'service': self.embedding_service,
                'interval': 45,
                'enabled': os.getenv("ENABLE_LOCAL_EMBEDDINGS", "true").lower() == "true"
            }
        }

    async def start_all_services(self):
        """Start all enabled services"""
        logger.info("Starting RSS News service manager")
        self.running = True

        # Start each enabled service in its own task
        tasks = []

        for service_name, config in self.service_configs.items():
            if config['enabled']:
                logger.info(f"Starting {service_name} service")
                task = asyncio.create_task(
                    self._run_service(service_name, config['service'], config['interval'])
                )
                tasks.append(task)
            else:
                logger.info(f"Service {service_name} is disabled")

        if not tasks:
            logger.warning("No services enabled")
            return

        # Wait for all tasks
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Service manager stopped by user")
        finally:
            self.running = False

    async def _run_service(self, service_name: str, service, interval: int):
        """Run a single service in a loop"""
        logger.info(f"Service {service_name} started with {interval}s interval")

        while self.running:
            try:
                if service_name == 'chunking':
                    await service.process_pending_chunks(batch_size=self.chunking_batch_size)
                elif service_name == 'fts':
                    await service.update_fts_index()
                elif service_name == 'embedding':
                    await service.process_pending_embeddings(batch_size=self.embedding_batch_size)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in {service_name} service: {e}")
                await asyncio.sleep(interval)

        logger.info(f"Service {service_name} stopped")

    async def run_single_pass(self, services: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run a single pass of specified services"""
        if services is None:
            services = ['chunking', 'fts', 'embedding']

        results = {}

        for service_name in services:
            if service_name not in self.service_configs:
                logger.warning(f"Unknown service: {service_name}")
                continue

            config = self.service_configs[service_name]
            if not config['enabled']:
                logger.info(f"Service {service_name} is disabled")
                results[service_name] = {'status': 'disabled'}
                continue

            try:
                logger.info(f"Running {service_name} service once")

                if service_name == 'chunking':
                    result = await config['service'].process_pending_chunks(batch_size=self.chunking_batch_size)
                elif service_name == 'fts':
                    result = await config['service'].update_fts_index()
                elif service_name == 'embedding':
                    result = await config['service'].process_pending_embeddings(batch_size=self.embedding_batch_size)

                results[service_name] = result

            except Exception as e:
                logger.error(f"Error running {service_name} service: {e}")
                results[service_name] = {'status': 'error', 'error': str(e)}

        return results

    async def get_service_status(self) -> Dict[str, Any]:
        """Get status of all services"""
        status = {
            'service_manager_running': self.running,
            'services': {}
        }

        for service_name, config in self.service_configs.items():
            service_status = {
                'enabled': config['enabled'],
                'interval': config['interval']
            }

            # Test service connectivity if enabled
            if config['enabled']:
                try:
                    if service_name == 'embedding':
                        service_status['connectivity'] = await config['service'].test_embedding_service()
                    else:
                        service_status['connectivity'] = True
                except Exception as e:
                    service_status['connectivity'] = False
                    service_status['error'] = str(e)

            status['services'][service_name] = service_status

        return status

    def stop_all_services(self):
        """Stop all running services"""
        logger.info("Stopping all services")
        self.running = False


async def main():
    """CLI entry point for service manager"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News Service Manager')
    parser.add_argument('command', choices=['start', 'run-once', 'status'],
                       help='Command to run')
    parser.add_argument('--services', nargs='*',
                       choices=['chunking', 'fts', 'embedding'],
                       help='Specific services to run (for run-once)')
    parser.add_argument('--chunking-interval', type=int, default=30,
                       help='Chunking service interval in seconds')
    parser.add_argument('--fts-interval', type=int, default=60,
                       help='FTS service interval in seconds')
    parser.add_argument('--embedding-interval', type=int, default=45,
                       help='Embedding service interval in seconds')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load configuration
    config = load_config()

    # Initialize database
    db = PgClient()

    # Create service manager
    manager = ServiceManager(db)

    # Update intervals if provided
    if args.chunking_interval:
        manager.service_configs['chunking']['interval'] = args.chunking_interval
    if args.fts_interval:
        manager.service_configs['fts']['interval'] = args.fts_interval
    if args.embedding_interval:
        manager.service_configs['embedding']['interval'] = args.embedding_interval

    if args.command == 'start':
        # Start all services continuously
        try:
            await manager.start_all_services()
        except KeyboardInterrupt:
            logger.info("Service manager stopped by user")
        finally:
            manager.stop_all_services()

    elif args.command == 'run-once':
        # Run services once
        results = await manager.run_single_pass(args.services)
        print("Service execution results:")
        for service_name, result in results.items():
            print(f"  {service_name}: {result}")

    elif args.command == 'status':
        # Get service status
        status = await manager.get_service_status()
        print("Service status:")
        print(f"  Manager running: {status['service_manager_running']}")
        for service_name, service_status in status['services'].items():
            print(f"  {service_name}:")
            for key, value in service_status.items():
                print(f"    {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
