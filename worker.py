"""
Enhanced article worker with new parsing pipeline
"""

import os
import logging
import uuid
import asyncio
import concurrent.futures
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from net.http import HttpClient
from parser.extract import extract_all, ParsedArticle
from utils.text import compute_text_hash, compute_word_count, estimate_reading_time
from utils.url import normalize_url, extract_domain
from pg_client_new import PgClient

logger = logging.getLogger(__name__)


class ArticleWorker:
    """Enhanced article worker with concurrent processing"""
    
    def __init__(self, db_client, batch_size: int = 50, max_workers: int = 10):
        self.db = db_client
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.http_client = HttpClient()
        
    def process_pending_articles(self) -> Dict[str, Any]:
        """
        Process pending articles in batches with concurrent processing
        Returns statistics about the processing operation
        """
        logger.info("Starting article processing")
        
        # Get pending articles
        articles = self.db.get_pending_articles(self.batch_size)
        if not articles:
            logger.info("No pending articles to process")
            return {'articles_processed': 0, 'successful': 0, 'errors': 0, 'duplicates': 0}
        
        logger.info(f"Processing {len(articles)} pending articles")
        
        stats = {
            'articles_processed': 0,
            'successful': 0,
            'duplicates': 0,
            'errors': 0,
            'partial': 0,
            'error_details': []
        }
        
        # Process articles concurrently (async)

        async def process_article_batch():
            tasks = []
            for article in articles:
                task = asyncio.create_task(self._process_single_article(article))
                tasks.append((task, article))

            for task, article in tasks:
                stats['articles_processed'] += 1

                try:
                    result = await task
                    
                    if result['status'] == 'stored':
                        stats['successful'] += 1
                    elif result['status'] == 'duplicate':
                        stats['duplicates'] += 1
                    elif result['status'] == 'partial':
                        stats['partial'] += 1
                    else:
                        stats['errors'] += 1
                        if result.get('error'):
                            stats['error_details'].append({
                                'article_id': article['id'],
                                'url': article['url'],
                                'error': result['error']
                            })
                        
                except Exception as e:
                    stats['errors'] += 1
                    error_msg = f"Exception processing article {article['url']}: {e}"
                    logger.error(error_msg)
                    stats['error_details'].append({
                        'article_id': article['id'],
                        'url': article['url'],
                        'error': str(e)
                    })
                    
                    # Update article status to error
                    try:
                        self.db.update_article_status(article['id'], 'error', str(e))
                    except Exception as update_e:
                        logger.error(f"Failed to update error status for article {article['id']}: {update_e}")

        # Run async processing
        asyncio.run(process_article_batch())

        logger.info(f"Processing complete: {stats['successful']}/{stats['articles_processed']} successful, "
                   f"{stats['duplicates']} duplicates, {stats['errors']} errors")

        # Log to diagnostics
        self.db.log_diagnostics(
            level='INFO',
            component='worker',
            message=f"Processed {stats['articles_processed']} articles",
            details={**stats, 'batch_id': str(uuid.uuid4())}
        )

        return stats


    async def _process_single_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single article"""
        result = {
            'status': 'error',
            'error': None
        }
        
        article_id = article['id']
        article_url = article['url']
        
        try:
            logger.debug(f"Processing article: {article_url}")
            
            # Update status to processing
            self.db.update_article_status(article_id, 'processing')
            
            # Fetch HTML content
            response, final_url, was_cached = self.http_client.get_with_conditional_headers(
                article_url
            )
            
            if response is None:
                result['error'] = f"Failed to fetch {article_url}"
                self.db.update_article_status(article_id, 'error', result['error'])
                return result
            
            # Parse and extract content
            rss_data = {
                'title': article.get('title'),
                'summary': article.get('description'),
                'authors': article.get('authors'),
                'published': article.get('published_at'),
                'tags': article.get('keywords'),
                'enclosures': article.get('enclosures')
            }
            
            parsed_article = extract_all(
                html=response.text if hasattr(response, 'text') else response.content.decode('utf-8', errors='ignore'),
                url=article_url,
                final_url=final_url,
                headers=dict(response.headers),
                rss_data=rss_data
            )
            
            # Check for text-based duplicates
            if parsed_article.text_hash:
                existing_id = self.db.check_duplicate_by_text_hash(parsed_article.text_hash)
                if existing_id:
                    self.db.update_article_status(article_id, 'duplicate', 
                                                f'Text duplicate of article {existing_id}')
                    result['status'] = 'duplicate'
                    logger.debug(f"Article is text duplicate: {article_url}")
                    return result
            
            # Update article with extracted data
            article_updates = {
                'canonical_url': parsed_article.canonical_url,
                'source': parsed_article.source,
                'section': parsed_article.section,
                'title': parsed_article.title or article.get('title', ''),
                'description': parsed_article.description or article.get('description', ''),
                'keywords': parsed_article.keywords,
                'authors': parsed_article.authors,
                'publisher': parsed_article.publisher,
                'top_image': parsed_article.top_image,
                'images': parsed_article.images,
                'videos': parsed_article.videos,
                'outlinks': parsed_article.outlinks,
                'published_at': parsed_article.published_at or article.get('published_at'),
                'updated_at': parsed_article.updated_at,
                'language': parsed_article.language,
                'paywalled': parsed_article.paywalled,
                'partial': parsed_article.partial,
                'full_text': parsed_article.full_text,
                'text_hash': parsed_article.text_hash,
                'word_count': parsed_article.word_count,
                'reading_time': parsed_article.reading_time,
                'status': parsed_article.status,
                'error_reason': parsed_article.error_reason
            }

            # Never attempt to change the unique url_hash in-place; it is set on insert.
            # This avoids UNIQUE violations (raw_url_hash_key) and empty-hash collisions
            # when extraction fails and returns a blank url_hash.
            
            self.db.update_article(article_id, **article_updates)
            
            # Note: Chunking is handled by a dedicated service now (ChunkingService).
            # Worker does not perform chunking to avoid duplication and reduce latency.

            # Add to articles index for deduplication
            if parsed_article.status == 'stored' and parsed_article.text_hash:
                # Determine readiness for chunking: must have full_text and not be duplicate
                has_text = bool(parsed_article.full_text)
                ready = has_text
                index_data = {
                    'url_hash': parsed_article.url_hash,
                    'text_hash': parsed_article.text_hash,
                    'title': parsed_article.title,
                    'author': ', '.join(parsed_article.authors) if parsed_article.authors else '',
                    'source': parsed_article.source,
                    # extended fields for Stage 6 readiness
                    'article_id': str(article_id),
                    'url': parsed_article.canonical_url or article_url,
                    'title_norm': (parsed_article.title or '').strip() if parsed_article.title else (article.get('title') or '').strip(),
                    'clean_text': parsed_article.full_text or '',
                    'language': parsed_article.language,
                    'category': parsed_article.section or article.get('section'),
                    'tags_norm': parsed_article.keywords or [],
                    'published_at': parsed_article.published_at or article.get('published_at'),
                    'processing_version': int(1),
                    'ready_for_chunking': bool(ready)
                }
                try:
                    self.db.upsert_article_index(index_data)
                except Exception as e:
                    # Handle duplicate constraint violations gracefully
                    if 'duplicate key value' in str(e) or 'already exists' in str(e):
                        logger.debug(f"Article already exists in index: {article_url}")
                        # Mark as duplicate instead of error
                        self.db.update_article_status(article_id, 'duplicate',
                                                    f'Duplicate detected during indexing: {str(e)[:100]}')
                        result['status'] = 'duplicate'
                    else:
                        # Re-raise other exceptions
                        raise
            
            result['status'] = parsed_article.status
            if parsed_article.error_reason:
                result['error'] = parsed_article.error_reason
            
            logger.debug(f"Article processed successfully: {article_url} "
                        f"({parsed_article.word_count} words, status: {parsed_article.status})")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error processing article {article_url}: {e}")
            
            try:
                self.db.update_article_status(article_id, 'error', str(e))
            except Exception as update_e:
                logger.error(f"Failed to update error status: {update_e}")
        
        return result

    def close(self):
        """Clean up resources"""
        if self.http_client:
            self.http_client.close()


# Legacy function for backward compatibility
def process_pending(db_client, worker_id: str = "worker-1", batch_size: int = 50):
    """Legacy function wrapper for the new worker"""
    worker = ArticleWorker(db_client, batch_size=batch_size)
    try:
        return worker.process_pending_articles()
    finally:
        worker.close()
