"""
Work Continuous Service
Continuously processes pending articles from 'raw' table with fulltext extraction
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pg_client_new import PgClient
from worker import ArticleWorker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkContinuousService:
    """Service for continuous article processing"""

    def __init__(self, db_client=None):
        self.db = db_client or PgClient()
        self.batch_size = int(os.getenv("WORK_CONTINUOUS_BATCH", "50"))
        self.max_workers = int(os.getenv("WORK_WORKERS", "10"))
        self.worker = ArticleWorker(
            db_client=self.db,
            batch_size=self.batch_size,
            max_workers=self.max_workers
        )

    def get_backlog_stats(self) -> Dict[str, Any]:
        """Get statistics about pending articles"""
        try:
            with self.db._cursor() as cur:
                # Total articles in raw
                cur.execute("SELECT COUNT(*) FROM raw")
                total = cur.fetchone()[0]

                # Pending articles (no fulltext)
                cur.execute("""
                    SELECT COUNT(*)
                    FROM raw
                    WHERE id NOT IN (
                        SELECT raw_id FROM fulltext WHERE raw_id IS NOT NULL
                    )
                """)
                pending = cur.fetchone()[0]

                # Processing articles
                cur.execute("SELECT COUNT(*) FROM raw WHERE status = 'processing'")
                processing = cur.fetchone()[0]

                # Error articles
                cur.execute("SELECT COUNT(*) FROM raw WHERE status = 'error'")
                errors = cur.fetchone()[0]

                stats = {
                    'total': total,
                    'pending': pending,
                    'processing': processing,
                    'errors': errors,
                    'completion': round(100 * (total - pending) / total, 2) if total > 0 else 0
                }

                return stats

        except Exception as e:
            logger.error(f"Failed to get backlog stats: {e}")
            return {}

    def process_batch(self) -> Dict[str, Any]:
        """Process one batch of pending articles"""
        try:
            logger.info("Processing batch of articles...")
            result = self.worker.process_pending_articles()
            return result

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            return {
                'articles_processed': 0,
                'successful': 0,
                'errors': 1,
                'error': str(e)
            }

    async def run_continuous(self, interval: int = 30):
        """
        Run continuous processing loop

        Args:
            interval: Seconds to wait between batches
        """
        logger.info(f"Starting Work Continuous Service (interval: {interval}s, batch: {self.batch_size})")

        iteration = 0
        while True:
            iteration += 1
            logger.info(f"=== Iteration {iteration} ===")

            # Get backlog stats
            stats = self.get_backlog_stats()
            pending = stats.get('pending', 0)

            logger.info(
                f"Backlog: {pending:,} pending articles "
                f"({stats.get('completion', 0)}% complete)"
            )

            if pending > 0:
                # Process batch
                result = self.process_batch()

                logger.info(
                    f"Processed {result.get('articles_processed', 0)} articles: "
                    f"{result.get('successful', 0)} successful, "
                    f"{result.get('duplicates', 0)} duplicates, "
                    f"{result.get('errors', 0)} errors"
                )

                # Log errors if any
                if result.get('error_details'):
                    for error in result['error_details'][:5]:  # Show first 5 errors
                        logger.error(f"  Error: {error.get('url')} - {error.get('error')}")
            else:
                logger.info("No pending articles, waiting...")

            # Wait before next iteration
            logger.info(f"Waiting {interval}s until next check...")
            await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='Work Continuous Service')
    parser.add_argument(
        '--interval',
        type=int,
        default=int(os.getenv("WORK_CONTINUOUS_INTERVAL", "30")),
        help='Seconds between processing batches (default: 30)'
    )
    parser.add_argument(
        '--batch',
        type=int,
        default=int(os.getenv("WORK_CONTINUOUS_BATCH", "50")),
        help='Number of articles to process per batch (default: 50)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit (for testing)'
    )

    args = parser.parse_args()

    # Update env vars if provided via CLI
    if args.batch:
        os.environ["WORK_CONTINUOUS_BATCH"] = str(args.batch)

    service = WorkContinuousService()

    if args.once:
        # Run once for testing
        logger.info("Running in single-batch mode")
        stats = service.get_backlog_stats()
        logger.info(f"Backlog: {stats}")

        if stats.get('pending', 0) > 0:
            result = service.process_batch()
            logger.info(f"Result: {result}")
        else:
            logger.info("No pending articles")
    else:
        # Run continuous
        asyncio.run(service.run_continuous(interval=args.interval))


if __name__ == "__main__":
    main()
