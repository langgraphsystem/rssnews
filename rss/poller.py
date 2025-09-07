"""
RSS feed polling with batch processing and conditional headers
"""

import asyncio
import concurrent.futures
import feedparser
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urljoin
import uuid

from net.http import HttpClient
from utils.url import canonicalize_url, extract_domain, compute_url_hash

logger = logging.getLogger(__name__)

class RSSPoller:
    """RSS feed poller with batch processing"""
    
    def __init__(self, db_client, batch_size: int = 10, max_workers: int = 10):
        self.db = db_client
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.http_client = HttpClient()
        
    def poll_active_feeds(self, feed_limit: int = None) -> Dict[str, Any]:
        """
        Poll active feeds in batches
        Returns statistics about the polling operation
        """
        logger.info("Starting RSS feed polling")
        
        # Get active feeds
        feeds = self.db.get_active_feeds(feed_limit)
        if not feeds:
            logger.info("No active feeds to poll")
            return {'feeds_polled': 0, 'new_articles': 0, 'errors': 0}
        
        logger.info(f"Polling {len(feeds)} active feeds")
        
        # Process feeds in batches
        stats = {
            'feeds_polled': 0,
            'feeds_successful': 0,
            'feeds_cached': 0,
            'feeds_errors': 0,
            'new_articles': 0,
            'duplicate_articles': 0,
            'errors': []
        }
        
        # Process in batches with concurrent workers
        for batch_start in range(0, len(feeds), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(feeds))
            batch_feeds = feeds[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//self.batch_size + 1}: "
                       f"feeds {batch_start+1}-{batch_end}")
            
            batch_stats = self._process_feed_batch(batch_feeds)
            
            # Merge stats
            for key, value in batch_stats.items():
                if isinstance(value, list):
                    stats[key].extend(value)
                else:
                    stats[key] += value
        
        logger.info(f"Polling complete: {stats['feeds_successful']}/{stats['feeds_polled']} successful, "
                   f"{stats['new_articles']} new articles")
        
        # Log to diagnostics
        self.db.log_diagnostics(
            level='INFO',
            component='poller',
            message=f"Polled {stats['feeds_polled']} feeds",
            details={**stats, 'correlation_id': str(uuid.uuid4())}
        )
        
        return stats
    
    def _process_feed_batch(self, feeds: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process a batch of feeds concurrently"""
        batch_stats = {
            'feeds_polled': 0,
            'feeds_successful': 0,
            'feeds_cached': 0,
            'feeds_errors': 0,
            'new_articles': 0,
            'duplicate_articles': 0,
            'errors': []
        }
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all feed polling tasks
            future_to_feed = {
                executor.submit(self._poll_single_feed, feed): feed 
                for feed in feeds
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_feed):
                feed = future_to_feed[future]
                batch_stats['feeds_polled'] += 1
                
                try:
                    feed_stats = future.result()
                    
                    if feed_stats['success']:
                        batch_stats['feeds_successful'] += 1
                        if feed_stats['cached']:
                            batch_stats['feeds_cached'] += 1
                        batch_stats['new_articles'] += feed_stats['new_articles']
                        batch_stats['duplicate_articles'] += feed_stats['duplicate_articles']
                    else:
                        batch_stats['feeds_errors'] += 1
                        batch_stats['errors'].append({
                            'feed_id': feed['id'],
                            'url': feed['url'],
                            'error': feed_stats['error']
                        })
                        
                except Exception as e:
                    batch_stats['feeds_errors'] += 1
                    error_msg = f"Exception polling feed {feed['url']}: {e}"
                    logger.error(error_msg)
                    batch_stats['errors'].append({
                        'feed_id': feed['id'],
                        'url': feed['url'], 
                        'error': str(e)
                    })
        
        return batch_stats
    
    def _poll_single_feed(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Poll a single RSS feed"""
        feed_stats = {
            'success': False,
            'cached': False,
            'new_articles': 0,
            'duplicate_articles': 0,
            'error': None
        }
        
        feed_url = feed['url']
        feed_id = feed['id']
        
        try:
            logger.debug(f"Polling feed: {feed_url}")
            
            # Make conditional GET request
            response, final_url, was_cached = self.http_client.get_with_conditional_headers(
                feed_url,
                etag=feed.get('last_etag'),
                last_modified=feed.get('last_modified')
            )
            
            if response is None:
                feed_stats['error'] = f"Failed to fetch {feed_url}"
                return feed_stats
            
            # Update feed metadata
            feed_updates = {
                'last_etag': response.headers.get('ETag'),
                'last_modified': response.headers.get('Last-Modified')
            }
            
            if was_cached:
                # Content not modified (304)
                feed_stats['success'] = True
                feed_stats['cached'] = True
                self.db.update_feed(feed_id, **feed_updates)
                logger.debug(f"Feed not modified: {feed_url}")
                return feed_stats
            
            # Parse RSS/Atom feed
            feed_data = feedparser.parse(response.content)
            
            if feed_data.bozo and not feed_data.entries:
                feed_stats['error'] = f"Invalid feed format: {feed_url}"
                return feed_stats
            
            # Process entries
            newest_entry_date = feed.get('last_entry_date')
            
            for entry in feed_data.entries:
                try:
                    article_stats = self._process_feed_entry(entry, feed, final_url or feed_url)
                    if article_stats['new']:
                        feed_stats['new_articles'] += 1
                        
                        # Track newest entry date
                        if article_stats['published_at']:
                            current_date = article_stats['published_at']
                            # Convert string date to datetime for comparison if needed
                            if isinstance(newest_entry_date, str) and newest_entry_date:
                                try:
                                    from dateutil.parser import parse
                                    newest_entry_date = parse(newest_entry_date)
                                except:
                                    newest_entry_date = None
                            
                            if not newest_entry_date or current_date > newest_entry_date:
                                newest_entry_date = current_date
                    else:
                        feed_stats['duplicate_articles'] += 1
                        
                except Exception as e:
                    logger.error(f"Error processing entry from {feed_url}: {e}")
                    continue
            
            # Update feed with new metadata
            if newest_entry_date != feed.get('last_entry_date'):
                feed_updates['last_entry_date'] = newest_entry_date
            
            self.db.update_feed(feed_id, **feed_updates)
            
            feed_stats['success'] = True
            logger.debug(f"Feed polled successfully: {feed_url} "
                        f"({feed_stats['new_articles']} new articles)")
            
        except Exception as e:
            feed_stats['error'] = str(e)
            logger.error(f"Error polling feed {feed_url}: {e}")
        
        return feed_stats
    
    def _process_feed_entry(self, entry, feed: Dict[str, Any], feed_url: str) -> Dict[str, Any]:
        """Process a single RSS entry"""
        entry_stats = {
            'new': False,
            'published_at': None
        }
        
        # Extract entry URL
        entry_url = self._extract_entry_url(entry)
        if not entry_url:
            return entry_stats
        
        # Normalize (canonicalize) URL and compute stable URL hash
        canonical = canonicalize_url(entry_url)
        # url_hash_v2 must be SHA256 of canonical URL
        url_hash_v2 = compute_url_hash(canonical)
        
        # Check for duplicate by URL (use the v2 hash value)
        if self.db.check_duplicate_by_url_hash(url_hash_v2):
            return entry_stats
        
        # Extract basic metadata
        title = entry.get('title', '').strip()
        summary = entry.get('summary', '').strip()
        
        # Extract publish date
        published_at = self._extract_entry_date(entry)
        entry_stats['published_at'] = published_at
        
        # Extract authors
        authors = self._extract_entry_authors(entry)
        
        # Extract categories/tags
        keywords = self._extract_entry_keywords(entry)
        
        # Extract enclosures
        enclosures = self._extract_entry_enclosures(entry)
        
        # Prepare article data for insertion
        article_data = {
            'url': entry_url,
            'canonical_url': canonical,
            'url_hash_v2': url_hash_v2,
            'source': extract_domain(canonical),
            'title': title,
            'description': summary,
            'authors': authors,
            'keywords': keywords,
            'published_at': published_at,
            'enclosures': enclosures,
            'status': 'pending',
            'fetched_at': datetime.now(timezone.utc),
            # Initialize other fields
            'section': '',
            'publisher': '',
            'top_image': '',
            'images': [],
            'videos': [],
            'outlinks': [],
            'updated_at': None,
            'language': feed.get('lang', ''),
            'paywalled': False,
            'partial': False,
            'full_text': '',
            'text_hash': '',
            'word_count': 0,
            'reading_time': 0,
            'error_reason': ''
        }
        
        try:
            # insert into raw using url_hash_v2 during migration window (and/or url_hash fallback)
            article_id = self.db.insert_raw_article(article_data)
            if article_id:
                entry_stats['new'] = True
                logger.debug(f"New article queued: {title[:50]}...")
        except Exception as e:
            logger.error(f"Failed to insert article {entry_url}: {e}")
        
        return entry_stats
    
    def _extract_entry_url(self, entry) -> Optional[str]:
        """Extract the best URL from RSS entry"""
        # Try different URL fields in order of preference
        for field in ['link', 'id', 'guid']:
            if hasattr(entry, field):
                url = getattr(entry, field)
                if url and isinstance(url, str) and url.startswith('http'):
                    return url
        
        # Check links array
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('rel') in (None, 'alternate') and link.get('href'):
                    href = link['href']
                    if href.startswith('http'):
                        return href
        
        return None
    
    def _extract_entry_date(self, entry) -> Optional[datetime]:
        """Extract publish date from entry"""
        # Try different date fields
        for field in ['published_parsed', 'updated_parsed', 'created_parsed']:
            if hasattr(entry, field):
                parsed_time = getattr(entry, field)
                if parsed_time:
                    try:
                        return datetime(*parsed_time[:6], tzinfo=timezone.utc)
                    except (TypeError, ValueError):
                        continue
        
        return None
    
    def _extract_entry_authors(self, entry) -> List[str]:
        """Extract authors from entry"""
        authors = []
        
        # Try author field
        if hasattr(entry, 'author') and entry.author:
            authors.append(entry.author)
        
        # Try authors array
        if hasattr(entry, 'authors'):
            for author in entry.authors:
                if isinstance(author, dict) and 'name' in author:
                    authors.append(author['name'])
                elif isinstance(author, str):
                    authors.append(author)
        
        return authors
    
    def _extract_entry_keywords(self, entry) -> List[str]:
        """Extract keywords/tags from entry"""
        keywords = []
        
        # Try tags field
        if hasattr(entry, 'tags'):
            for tag in entry.tags:
                if isinstance(tag, dict) and 'term' in tag:
                    keywords.append(tag['term'])
                elif isinstance(tag, str):
                    keywords.append(tag)
        
        return keywords
    
    def _extract_entry_enclosures(self, entry) -> List[Dict[str, Any]]:
        """Extract media enclosures from entry"""
        enclosures = []
        
        if hasattr(entry, 'enclosures'):
            for enclosure in entry.enclosures:
                if isinstance(enclosure, dict):
                    enclosures.append({
                        'href': enclosure.get('href', ''),
                        'type': enclosure.get('type', ''),
                        'length': enclosure.get('length', 0)
                    })
        
        return enclosures
    
    def close(self):
        """Clean up resources"""
        if self.http_client:
            self.http_client.close()
