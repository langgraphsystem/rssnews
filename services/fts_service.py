"""
Separate Full-Text Search (FTS) service for RSS News System
"""

import os
import sys
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pg_client_new import PgClient
from config import load_config

logger = logging.getLogger(__name__)


class FTSService:
    """Dedicated service for Full-Text Search indexing"""

    def __init__(self, db_client: Optional[PgClient] = None):
        self.db = db_client or PgClient()

    async def update_fts_index(self, batch_size: int = 100000) -> Dict[str, Any]:
        """Update FTS vectors for chunks that need indexing"""
        logger.info("Starting FTS indexing service")

        # Get chunks that need FTS indexing (those without fts_vector)
        chunk_ids = self.db.get_chunks_needing_fts_update(batch_size)

        if not chunk_ids:
            logger.info("No chunks need FTS indexing")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info(f"Updating FTS index for {len(chunk_ids)} chunks")

        stats = {
            'processed': len(chunk_ids),
            'successful': 0,
            'errors': 0,
            'error_details': []
        }

        try:
            # Update FTS vectors in batch
            updated_count = self.db.update_chunks_fts(chunk_ids)
            stats['successful'] = updated_count

            if updated_count != len(chunk_ids):
                stats['errors'] = len(chunk_ids) - updated_count
                logger.warning(f"Expected to update {len(chunk_ids)} chunks, but updated {updated_count}")

            logger.info(f"FTS indexing complete: {updated_count} chunks indexed")

        except Exception as e:
            stats['errors'] = len(chunk_ids)
            error_msg = f"Error updating FTS index: {e}"
            logger.error(error_msg)
            stats['error_details'].append(error_msg)

        return stats

    async def search_chunks(self, query: str, limit: int = 10,
                           sources: Optional[List[str]] = None,
                           since_days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search chunks using FTS"""
        try:
            if sources or since_days:
                # Use advanced search with filters
                results = self.db.search_chunks_fts_ts(
                    tsquery=None,
                    plainto=query,
                    sources=sources or [],
                    since_days=since_days,
                    limit=limit
                )
            else:
                # Use simple FTS search
                results = self.db.search_chunks_fts(query, limit)

            logger.info(f"FTS search for '{query}' returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"FTS search failed for query '{query}': {e}")
            return []

    async def rebuild_fts_index(self) -> Dict[str, Any]:
        """Rebuild entire FTS index"""
        logger.info("Starting FTS index rebuild")

        try:
            # Get all chunk IDs
            all_chunk_ids = self.db.get_all_chunk_ids()

            if not all_chunk_ids:
                logger.info("No chunks found for FTS rebuild")
                return {'processed': 0, 'successful': 0, 'errors': 0}

            logger.info(f"Rebuilding FTS index for {len(all_chunk_ids)} chunks")

            # Process in batches to avoid memory issues
            batch_size = 1000
            total_updated = 0
            total_errors = 0

            for i in range(0, len(all_chunk_ids), batch_size):
                batch_ids = all_chunk_ids[i:i + batch_size]

                try:
                    updated_count = self.db.update_chunks_fts(batch_ids)
                    total_updated += updated_count
                    logger.info(f"FTS rebuild progress: {total_updated}/{len(all_chunk_ids)} chunks")

                except Exception as e:
                    total_errors += len(batch_ids)
                    logger.error(f"Error rebuilding FTS batch {i}-{i+len(batch_ids)}: {e}")

            logger.info(f"FTS index rebuild complete: {total_updated} successful, {total_errors} errors")

            return {
                'processed': len(all_chunk_ids),
                'successful': total_updated,
                'errors': total_errors
            }

        except Exception as e:
            logger.error(f"Error during FTS index rebuild: {e}")
            return {'processed': 0, 'successful': 0, 'errors': 1}

    def run_service(self, interval_seconds: int = 60):
        """Run FTS service in a loop"""
        logger.info(f"Starting FTS service with {interval_seconds}s interval")

        async def service_loop():
            while True:
                try:
                    await self.update_fts_index()
                    await asyncio.sleep(interval_seconds)
                except KeyboardInterrupt:
                    logger.info("FTS service stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in FTS service: {e}")
                    await asyncio.sleep(interval_seconds)

        asyncio.run(service_loop())


async def main():
    """CLI entry point for FTS service"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News FTS Service')
    parser.add_argument('command', choices=['index', 'search', 'rebuild', 'service'],
                       help='Command to run')
    parser.add_argument('--query', type=str, help='Search query')
    parser.add_argument('--limit', type=int, default=10, help='Search result limit')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for indexing')
    parser.add_argument('--interval', type=int, default=60, help='Service loop interval in seconds')
    parser.add_argument('--sources', nargs='*', help='Filter by source domains')
    parser.add_argument('--since-days', type=int, help='Filter by days since publication')

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

    # Create FTS service
    service = FTSService(db)

    if args.command == 'index':
        # Update FTS index once
        result = await service.update_fts_index(args.batch_size)
        print(f"FTS indexing complete: {result}")

    elif args.command == 'search':
        if not args.query:
            print("Error: --query is required for search command")
            return

        # Search chunks
        results = await service.search_chunks(
            query=args.query,
            limit=args.limit,
            sources=args.sources,
            since_days=args.since_days
        )

        print(f"Found {len(results)} results for '{args.query}':")
        for i, result in enumerate(results, 1):
            score = result.get('score', 0)
            title = result.get('title_norm', 'No title')[:50]
            source = result.get('source_domain', 'Unknown')
            text_preview = result.get('text', '')[:100] + '...'
            print(f"{i}. [{score:.3f}] {title} ({source})")
            print(f"   {text_preview}")
            print()

    elif args.command == 'rebuild':
        # Rebuild entire FTS index
        result = await service.rebuild_fts_index()
        print(f"FTS rebuild complete: {result}")

    elif args.command == 'service':
        # Run continuous service
        service.run_service(args.interval)


if __name__ == "__main__":
    asyncio.run(main())