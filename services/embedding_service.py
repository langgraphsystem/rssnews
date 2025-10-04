"""
Separate embedding service for RSS News System
"""

import os
import sys
import asyncio
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pg_client_new import PgClient
from local_embedding_generator import LocalEmbeddingGenerator
from config import load_config

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Dedicated service for generating and managing embeddings"""

    def __init__(self, db_client: Optional[PgClient] = None):
        # Single crossover database for all operations
        self.db = db_client or PgClient()
        self.generator = LocalEmbeddingGenerator()
        self.enabled = os.getenv("ENABLE_LOCAL_EMBEDDINGS", "true").lower() == "true"

    async def process_pending_embeddings(self, batch_size: int = 1500) -> Dict[str, Any]:
        """Process chunks that need embeddings"""
        if not self.enabled:
            logger.info("Embedding service disabled")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info("Starting embedding service")

        # Get chunks that need embeddings
        chunks = self.db.get_chunks_needing_embeddings(batch_size)

        if not chunks:
            logger.info("No chunks need embeddings")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info(f"Processing embeddings for {len(chunks)} chunks")

        stats = {
            'processed': 0,
            'successful': 0,
            'errors': 0,
            'error_details': []
        }

        # Extract texts for batch processing
        texts = [chunk.get('text', '') for chunk in chunks]

        try:
            # Generate embeddings in batch
            embeddings = await self.generator.generate_embeddings(texts)

            # Update chunks with embeddings
            for chunk, embedding in zip(chunks, embeddings):
                stats['processed'] += 1

                try:
                    if embedding:
                        # Update chunk with embedding
                        chunk_id = chunk['id']
                        success = self.db.update_chunk_embedding(chunk_id, embedding)

                        if success:
                            stats['successful'] += 1
                            logger.debug(f"Updated embedding for chunk {chunk_id}")
                        else:
                            stats['errors'] += 1
                            stats['error_details'].append({
                                'chunk_id': chunk_id,
                                'error': 'Failed to update chunk embedding in database'
                            })
                    else:
                        stats['errors'] += 1
                        stats['error_details'].append({
                            'chunk_id': chunk.get('id'),
                            'error': 'No embedding generated'
                        })

                except Exception as e:
                    stats['errors'] += 1
                    error_msg = f"Error processing embedding for chunk {chunk.get('id')}: {e}"
                    logger.error(error_msg)
                    stats['error_details'].append({
                        'chunk_id': chunk.get('id'),
                        'error': str(e)
                    })

        except Exception as e:
            # Batch generation failed
            stats['errors'] = len(chunks)
            error_msg = f"Batch embedding generation failed: {e}"
            logger.error(error_msg)
            stats['error_details'].append(error_msg)

        logger.info(f"Embedding processing complete: {stats['successful']}/{stats['processed']} successful")

        return stats

    async def search_similar_chunks(self, query_text: str, limit: int = 10,
                                   similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search for similar chunks using embedding similarity"""
        try:
            # Generate embedding for query
            query_embeddings = await self.generator.generate_embeddings([query_text])

            if not query_embeddings or not query_embeddings[0]:
                logger.error("Failed to generate embedding for query")
                return []

            query_embedding = query_embeddings[0]

            # Search similar chunks in database
            results = self.db.search_chunks_by_similarity(
                query_embedding=query_embedding,
                limit=limit,
                similarity_threshold=similarity_threshold
            )

            logger.info(f"Embedding search for '{query_text[:50]}...' returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Embedding search failed for query '{query_text[:50]}...': {e}")
            return []

    async def rebuild_embeddings(self, batch_size: int = 20) -> Dict[str, Any]:
        """Rebuild all embeddings from scratch"""
        logger.info("Starting embedding rebuild")

        try:
            # Get all chunk IDs and texts
            all_chunks = self.db.get_all_chunks_for_embedding()

            if not all_chunks:
                logger.info("No chunks found for embedding rebuild")
                return {'processed': 0, 'successful': 0, 'errors': 0}

            logger.info(f"Rebuilding embeddings for {len(all_chunks)} chunks")

            total_processed = 0
            total_successful = 0
            total_errors = 0

            # Process in batches
            for i in range(0, len(all_chunks), batch_size):
                batch_chunks = all_chunks[i:i + batch_size]

                try:
                    # Process batch
                    result = await self._process_embedding_batch(batch_chunks)

                    total_processed += result['processed']
                    total_successful += result['successful']
                    total_errors += result['errors']

                    logger.info(f"Embedding rebuild progress: {total_processed}/{len(all_chunks)} chunks")

                except Exception as e:
                    total_errors += len(batch_chunks)
                    logger.error(f"Error rebuilding embedding batch {i}-{i+len(batch_chunks)}: {e}")

            logger.info(f"Embedding rebuild complete: {total_successful} successful, {total_errors} errors")

            return {
                'processed': total_processed,
                'successful': total_successful,
                'errors': total_errors
            }

        except Exception as e:
            logger.error(f"Error during embedding rebuild: {e}")
            return {'processed': 0, 'successful': 0, 'errors': 1}

    async def _process_embedding_batch(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process a batch of chunks for embeddings"""
        texts = [chunk.get('text', '') for chunk in chunks]

        try:
            embeddings = await self.generator.generate_embeddings(texts)

            successful = 0
            errors = 0

            for chunk, embedding in zip(chunks, embeddings):
                try:
                    if embedding:
                        chunk_id = chunk['id']
                        success = self.db.update_chunk_embedding(chunk_id, embedding)
                        if success:
                            successful += 1
                        else:
                            errors += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

            return {
                'processed': len(chunks),
                'successful': successful,
                'errors': errors
            }

        except Exception as e:
            logger.error(f"Batch embedding processing failed: {e}")
            return {
                'processed': len(chunks),
                'successful': 0,
                'errors': len(chunks)
            }

    async def test_embedding_service(self) -> bool:
        """Test embedding service connectivity"""
        try:
            logger.info("Testing embedding service...")

            # Test connection to embedding generator
            connection_ok = await self.generator.test_connection()

            if connection_ok:
                logger.info("✅ Embedding service test passed")
                return True
            else:
                logger.error("❌ Embedding service test failed")
                return False

        except Exception as e:
            logger.error(f"❌ Embedding service test error: {e}")
            return False

    async def run_service_async(self, interval_seconds: int = 45):
        """Run embedding service loop (async)."""
        logger.info(f"Starting embedding service with {interval_seconds}s interval")
        while True:
            try:
                await self.process_pending_embeddings()
                await asyncio.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Embedding service stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in embedding service: {e}")
                await asyncio.sleep(interval_seconds)

    def run_service(self, interval_seconds: int = 45):
        """Synchronous wrapper to run the embedding service loop."""
        asyncio.run(self.run_service_async(interval_seconds))


async def main():
    """CLI entry point for embedding service"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News Embedding Service')
    parser.add_argument('command', choices=['process', 'search', 'rebuild', 'test', 'service'],
                       help='Command to run')
    parser.add_argument('--query', type=str, help='Search query for similarity search')
    parser.add_argument('--limit', type=int, default=10, help='Search result limit')
    parser.add_argument('--batch-size', type=int, default=20, help='Batch size for processing')
    parser.add_argument('--interval', type=int, default=45, help='Service loop interval in seconds')
    parser.add_argument('--threshold', type=float, default=0.7, help='Similarity threshold for search')

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

    # Create embedding service
    service = EmbeddingService(db)

    if args.command == 'process':
        # Process pending embeddings once
        result = await service.process_pending_embeddings(args.batch_size)
        print(f"Embedding processing complete: {result}")

    elif args.command == 'search':
        if not args.query:
            print("Error: --query is required for search command")
            return

        # Search similar chunks
        results = await service.search_similar_chunks(
            query_text=args.query,
            limit=args.limit,
            similarity_threshold=args.threshold
        )

        print(f"Found {len(results)} similar chunks for '{args.query}':")
        for i, result in enumerate(results, 1):
            similarity = result.get('similarity', 0)
            title = result.get('title_norm', 'No title')[:50]
            source = result.get('source_domain', 'Unknown')
            text_preview = result.get('text', '')[:100] + '...'
            print(f"{i}. [{similarity:.3f}] {title} ({source})")
            print(f"   {text_preview}")
            print()

    elif args.command == 'rebuild':
        # Rebuild all embeddings
        result = await service.rebuild_embeddings(args.batch_size)
        print(f"Embedding rebuild complete: {result}")

    elif args.command == 'test':
        # Test embedding service
        success = await service.test_embedding_service()
        print(f"Embedding service test: {'PASSED' if success else 'FAILED'}")

    elif args.command == 'service':
        # Run continuous service (async)
        await service.run_service_async(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
