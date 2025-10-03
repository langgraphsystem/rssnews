"""
OpenAI Embedding Migration Service
Processes chunks without embeddings or with incorrect dimensions using text-embedding-3-large
"""

import os
import sys
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pg_client_new import PgClient
from openai_embedding_generator import OpenAIEmbeddingGenerator

logger = logging.getLogger(__name__)


class OpenAIEmbeddingMigrationService:
    """Service for migrating embeddings to OpenAI text-embedding-3-large (3072-dim)"""

    def __init__(self, db_client: Optional[PgClient] = None):
        self.db = db_client or PgClient()
        self.generator = OpenAIEmbeddingGenerator()
        self.enabled = os.getenv("OPENAI_EMBEDDING_SERVICE_ENABLED", "true").lower() == "true"
        self.batch_size = int(os.getenv("OPENAI_EMBEDDING_BATCH_SIZE", "100"))
        self.max_retries = int(os.getenv("OPENAI_EMBEDDING_MAX_RETRIES", "3"))

    def get_statistics(self) -> Dict[str, Any]:
        """Get current embedding statistics"""
        try:
            with self.db._cursor() as cur:
                # Total chunks
                cur.execute("SELECT COUNT(*) FROM article_chunks")
                total_chunks = cur.fetchone()[0]

                # Chunks with embeddings (TEXT column)
                cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL")
                with_text_embeddings = cur.fetchone()[0]

                # Chunks with pgvector embeddings
                cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL")
                with_pgvector_embeddings = cur.fetchone()[0]

                # Chunks without any embeddings
                cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NULL")
                without_embeddings = cur.fetchone()[0]

                stats = {
                    'total_chunks': total_chunks,
                    'with_text_embeddings': with_text_embeddings,
                    'with_pgvector_embeddings': with_pgvector_embeddings,
                    'without_embeddings': without_embeddings,
                    'percentage_complete': round(100 * with_pgvector_embeddings / total_chunks, 2) if total_chunks > 0 else 0
                }

                return stats

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    async def migrate_backlog(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Migrate all chunks without embeddings

        Args:
            limit: Maximum number of chunks to process (None = all)

        Returns:
            Statistics about the migration
        """
        if not self.enabled:
            logger.info("OpenAI embedding migration service is disabled")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info("Starting embedding backlog migration")

        # Get chunks that need embeddings
        chunks = self._get_chunks_needing_embeddings(limit or 999999)

        if not chunks:
            logger.info("No chunks need embeddings")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info(f"Migrating embeddings for {len(chunks)} chunks")

        stats = {
            'processed': 0,
            'successful': 0,
            'errors': 0,
            'error_details': []
        }

        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i + self.batch_size]
            batch_stats = await self._process_batch(batch)

            stats['processed'] += batch_stats['processed']
            stats['successful'] += batch_stats['successful']
            stats['errors'] += batch_stats['errors']
            stats['error_details'].extend(batch_stats.get('error_details', []))

            logger.info(f"Migration progress: {stats['successful']}/{len(chunks)} successful ({stats['errors']} errors)")

        logger.info(f"Migration complete: {stats['successful']} successful, {stats['errors']} errors")
        return stats

    async def process_continuous(self, interval_seconds: int = 60) -> None:
        """Run continuous migration service

        Args:
            interval_seconds: Interval between migration runs
        """
        logger.info(f"Starting continuous migration service with {interval_seconds}s interval")

        while True:
            try:
                # Get statistics
                stats_before = self.get_statistics()
                backlog = stats_before.get('without_embeddings', 0)

                if backlog > 0:
                    logger.info(f"Found {backlog} chunks without embeddings, processing...")
                    result = await self.migrate_backlog(limit=self.batch_size)
                    logger.info(f"Processed {result['successful']} chunks")
                else:
                    logger.info("No backlog, waiting...")

                await asyncio.sleep(interval_seconds)

            except KeyboardInterrupt:
                logger.info("Continuous migration service stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in continuous migration: {e}")
                await asyncio.sleep(interval_seconds)

    def _get_chunks_needing_embeddings(self, limit: int) -> List[Dict[str, Any]]:
        """Get chunks that need embeddings

        Args:
            limit: Maximum number of chunks to retrieve

        Returns:
            List of chunk dictionaries
        """
        try:
            with self.db._cursor() as cur:
                cur.execute("""
                    SELECT id, text, article_id, chunk_index
                    FROM article_chunks
                    WHERE embedding IS NULL
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

                chunks = []
                for row in cur.fetchall():
                    chunks.append({
                        'id': row[0],
                        'text': row[1],
                        'article_id': row[2],
                        'chunk_index': row[3]
                    })

                return chunks

        except Exception as e:
            logger.error(f"Failed to get chunks needing embeddings: {e}")
            return []

    async def _process_batch(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process a batch of chunks

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Statistics about the batch processing
        """
        texts = [chunk['text'] for chunk in chunks]

        stats = {
            'processed': len(chunks),
            'successful': 0,
            'errors': 0,
            'error_details': []
        }

        try:
            # Generate embeddings
            embeddings = await self.generator.generate_embeddings(texts)

            # Update database
            for chunk, embedding in zip(chunks, embeddings):
                chunk_id = chunk['id']

                if embedding:
                    try:
                        success = self.db.update_chunk_embedding(chunk_id, embedding)
                        if success:
                            stats['successful'] += 1
                        else:
                            stats['errors'] += 1
                            stats['error_details'].append({
                                'chunk_id': chunk_id,
                                'error': 'Failed to update embedding in database'
                            })
                    except Exception as e:
                        stats['errors'] += 1
                        stats['error_details'].append({
                            'chunk_id': chunk_id,
                            'error': str(e)
                        })
                else:
                    stats['errors'] += 1
                    stats['error_details'].append({
                        'chunk_id': chunk_id,
                        'error': 'No embedding generated'
                    })

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            stats['errors'] = len(chunks)
            stats['error_details'].append(f"Batch error: {str(e)}")

        return stats


async def main():
    """CLI entry point for migration service"""
    import argparse

    parser = argparse.ArgumentParser(description='OpenAI Embedding Migration Service')
    parser.add_argument('command', choices=['migrate', 'continuous', 'stats', 'validate'],
                       help='Command to run')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of chunks to process')
    parser.add_argument('--interval', type=int, default=60, help='Interval in seconds for continuous mode')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for processing')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create service
    service = OpenAIEmbeddingMigrationService()

    if args.batch_size:
        service.batch_size = args.batch_size

    if args.command == 'migrate':
        # One-time migration
        result = await service.migrate_backlog(args.limit)
        print(f"\n✅ Migration complete:")
        print(f"   Processed: {result['processed']}")
        print(f"   Successful: {result['successful']}")
        print(f"   Errors: {result['errors']}")

        if result['errors'] > 0 and result.get('error_details'):
            print(f"\n⚠️ Error details:")
            for error in result['error_details'][:5]:  # Show first 5 errors
                print(f"   {error}")

    elif args.command == 'continuous':
        # Continuous service
        await service.process_continuous(args.interval)

    elif args.command == 'stats':
        # Show statistics
        stats = service.get_statistics()
        print(f"\n📊 Embedding Statistics:")
        print(f"   Total chunks: {stats.get('total_chunks', 0)}")
        print(f"   With TEXT embeddings: {stats.get('with_text_embeddings', 0)}")
        print(f"   With pgvector embeddings: {stats.get('with_pgvector_embeddings', 0)}")
        print(f"   Without embeddings: {stats.get('without_embeddings', 0)}")
        print(f"   Completion: {stats.get('percentage_complete', 0)}%")

    elif args.command == 'validate':
        # Validate embedding dimensions
        print("\n🔍 Validating embedding dimensions...")
        stats = service.get_statistics()

        if stats.get('with_pgvector_embeddings', 0) > 0:
            print(f"✅ Found {stats['with_pgvector_embeddings']} chunks with pgvector embeddings")
        else:
            print("⚠️ No chunks with pgvector embeddings found")

        if stats.get('without_embeddings', 0) > 0:
            print(f"⚠️ Found {stats['without_embeddings']} chunks without embeddings")
            print(f"   Run: python services/openai_embedding_migration_service.py migrate")


if __name__ == "__main__":
    asyncio.run(main())
