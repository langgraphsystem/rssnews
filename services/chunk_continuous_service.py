"""
Chunk Continuous Service
Continuously processes articles that need chunking
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
from services.chunking_service import ChunkingService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChunkContinuousService:
    """Service for continuous article chunking"""

    def __init__(self, db_client=None):
        self.db = db_client or PgClient()
        self.batch_size = int(os.getenv("CHUNK_CONTINUOUS_BATCH", "100"))
        self.chunker = ChunkingService(db_client=self.db)

    def get_backlog_stats(self) -> Dict[str, Any]:
        """Get statistics about articles needing chunking"""
        try:
            with self.db._cursor() as cur:
                # Total articles in fulltext
                cur.execute("SELECT COUNT(*) FROM fulltext")
                total = cur.fetchone()[0]

                # Articles without chunks (not in article_chunks)
                cur.execute("""
                    SELECT COUNT(DISTINCT f.article_id)
                    FROM fulltext f
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM article_chunks ac
                        WHERE ac.article_id = f.article_id
                    )
                    AND f.clean_text IS NOT NULL
                    AND LENGTH(f.clean_text) > 50
                """)
                pending = cur.fetchone()[0]

                # Total chunks created
                cur.execute("SELECT COUNT(*) FROM article_chunks")
                total_chunks = cur.fetchone()[0]

                # Articles with chunks
                cur.execute("SELECT COUNT(DISTINCT article_id) FROM article_chunks")
                chunked_articles = cur.fetchone()[0]

                stats = {
                    'total_articles': total,
                    'pending_chunking': pending,
                    'chunked_articles': chunked_articles,
                    'total_chunks': total_chunks,
                    'completion': round(100 * chunked_articles / total, 2) if total > 0 else 0
                }

                return stats

        except Exception as e:
            logger.error(f"Failed to get backlog stats: {e}")
            return {}

    async def process_batch(self) -> Dict[str, Any]:
        """Process one batch of articles needing chunking"""
        try:
            logger.info(f"Processing batch of {self.batch_size} articles...")
            result = await self.chunker.process_pending_chunks(batch_size=self.batch_size)
            return result

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            return {
                'processed': 0,
                'successful': 0,
                'errors': 1,
                'error': str(e)
            }

    async def run_continuous(self, interval: int = 30):
        """
        Run continuous chunking loop

        Args:
            interval: Seconds to wait between batches
        """
        logger.info(f"Starting Chunk Continuous Service (interval: {interval}s, batch: {self.batch_size})")

        iteration = 0
        while True:
            iteration += 1
            logger.info(f"=== Iteration {iteration} ===")

            # Get backlog stats
            stats = self.get_backlog_stats()
            pending = stats.get('pending_chunking', 0)

            logger.info(
                f"Backlog: {pending:,} articles need chunking "
                f"({stats.get('completion', 0)}% complete, "
                f"{stats.get('total_chunks', 0):,} total chunks)"
            )

            if pending > 0:
                # Process batch
                result = await self.process_batch()

                logger.info(
                    f"Processed {result.get('processed', 0)} articles: "
                    f"{result.get('successful', 0)} successful, "
                    f"{result.get('total_chunks', 0)} chunks created, "
                    f"{result.get('errors', 0)} errors"
                )

                # Log errors if any
                if result.get('error_details'):
                    for error in result['error_details'][:5]:  # Show first 5 errors
                        logger.error(f"  Error: article {error.get('article_id')} - {error.get('error')}")
            else:
                logger.info("No articles need chunking, waiting...")

            # Wait before next iteration
            logger.info(f"Waiting {interval}s until next check...")
            await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='Chunk Continuous Service')
    parser.add_argument(
        '--interval',
        type=int,
        default=int(os.getenv("CHUNK_CONTINUOUS_INTERVAL", "30")),
        help='Seconds between processing batches (default: 30)'
    )
    parser.add_argument(
        '--batch',
        type=int,
        default=int(os.getenv("CHUNK_CONTINUOUS_BATCH", "100")),
        help='Number of articles to process per batch (default: 100)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit (for testing)'
    )

    args = parser.parse_args()

    # Update env vars if provided via CLI
    if args.batch:
        os.environ["CHUNK_CONTINUOUS_BATCH"] = str(args.batch)

    service = ChunkContinuousService()

    if args.once:
        # Run once for testing
        logger.info("Running in single-batch mode")
        stats = service.get_backlog_stats()
        logger.info(f"Backlog: {stats}")

        if stats.get('pending_chunking', 0) > 0:
            result = asyncio.run(service.process_batch())
            logger.info(f"Result: {result}")
        else:
            logger.info("No articles need chunking")
    else:
        # Run continuous
        asyncio.run(service.run_continuous(interval=args.interval))


if __name__ == "__main__":
    main()
