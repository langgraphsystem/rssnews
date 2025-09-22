"""
Separate chunking service for RSS News System
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
from local_llm_chunker import LocalLLMChunker
from config import load_config

logger = logging.getLogger(__name__)


class ChunkingService:
    """Dedicated service for article chunking"""

    def __init__(self, db_client: Optional[PgClient] = None):
        self.db = db_client or PgClient()
        self.chunker = LocalLLMChunker()
        self.enabled = os.getenv("ENABLE_LOCAL_CHUNKING", "true").lower() == "true"

    async def process_pending_chunks(self, batch_size: int = 10) -> Dict[str, Any]:
        """Process articles that need chunking"""
        if not self.enabled:
            logger.info("Chunking service disabled")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info("Starting chunking service")

        # Get articles ready for chunking
        articles = self.db.get_articles_ready_for_chunking(batch_size)

        if not articles:
            logger.info("No articles ready for chunking")
            return {'processed': 0, 'successful': 0, 'errors': 0}

        logger.info(f"Processing {len(articles)} articles for chunking")

        stats = {
            'processed': 0,
            'successful': 0,
            'errors': 0,
            'total_chunks': 0,
            'error_details': []
        }

        for article in articles:
            stats['processed'] += 1

            try:
                result = await self._chunk_article(article)

                if result['success']:
                    stats['successful'] += 1
                    stats['total_chunks'] += result['chunk_count']
                else:
                    stats['errors'] += 1
                    stats['error_details'].append({
                        'article_id': article['article_id'],
                        'error': result['error']
                    })

            except Exception as e:
                stats['errors'] += 1
                error_msg = f"Exception chunking article {article['article_id']}: {e}"
                logger.error(error_msg)
                stats['error_details'].append({
                    'article_id': article['article_id'],
                    'error': str(e)
                })

        logger.info(f"Chunking complete: {stats['successful']}/{stats['processed']} successful, "
                   f"{stats['total_chunks']} total chunks created")

        return stats

    async def _chunk_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Chunk a single article"""
        article_id = article['article_id']

        try:
            logger.debug(f"Chunking article: {article_id}")

            # Get article content
            content = article.get('clean_text', '')
            if not content or len(content.strip()) < 50:
                return {'success': False, 'error': 'Insufficient content for chunking'}

            # Prepare metadata
            metadata = {
                'title': article.get('title_norm', ''),
                'category': article.get('category', ''),
                'language': article.get('language', 'en'),
                'source': article.get('source', '')
            }

            # Create chunks using LLM
            chunks = await self.chunker.create_chunks(content, metadata)

            if not chunks:
                return {'success': False, 'error': 'No chunks generated'}

            # Add required metadata to chunks
            for chunk in chunks:
                chunk.update({
                    'url': article.get('url', ''),
                    'title_norm': article.get('title_norm', ''),
                    'source_domain': article.get('source', ''),
                    'published_at': article.get('published_at'),
                    'language': article.get('language', 'en'),
                    'category': article.get('category', ''),
                    'tags_norm': article.get('tags_norm', []),
                })

            # Save chunks to database
            processing_version = article.get('processing_version', 1)
            self.db.upsert_article_chunks(article_id, processing_version, chunks)
            self.db.mark_chunking_completed(article_id, processing_version)

            logger.info(f"Successfully chunked article {article_id}: {len(chunks)} chunks")

            return {
                'success': True,
                'chunk_count': len(chunks),
                'article_id': article_id
            }

        except Exception as e:
            logger.error(f"Error chunking article {article_id}: {e}")
            return {'success': False, 'error': str(e)}

    def run_service(self, interval_seconds: int = 30):
        """Run chunking service in a loop"""
        logger.info(f"Starting chunking service with {interval_seconds}s interval")

        async def service_loop():
            while True:
                try:
                    await self.process_pending_chunks()
                    await asyncio.sleep(interval_seconds)
                except KeyboardInterrupt:
                    logger.info("Chunking service stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in chunking service: {e}")
                    await asyncio.sleep(interval_seconds)

        asyncio.run(service_loop())


async def main():
    """CLI entry point for chunking service"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News Chunking Service')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for processing')
    parser.add_argument('--interval', type=int, default=30, help='Service loop interval in seconds')
    parser.add_argument('--once', action='store_true', help='Run once instead of continuous loop')

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

    # Create chunking service
    service = ChunkingService(db)

    if args.once:
        # Run once
        result = await service.process_pending_chunks(args.batch_size)
        print(f"Chunking complete: {result}")
    else:
        # Run continuous service
        service.run_service(args.interval)


if __name__ == "__main__":
    asyncio.run(main())