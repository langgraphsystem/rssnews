"""
HTTP client with retry logic and backoff
"""

import time
import random
import requests
import os
import socket
import ipaddress
from typing import Dict, Optional, Tuple, Any, List
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

@dataclass
class RetryItem:
    """Item to retry"""
    url: str
    headers: Dict[str, str]
    attempt: int
    next_retry: datetime
    max_attempts: int
    error: str
    context: Dict[str, Any]

class RetryQueue:
    """Persistent retry queue for failed HTTP requests"""
    
    def __init__(self, queue_file: str = 'storage/queue/retry_queue.json'):
        self.queue_file = queue_file
        self._ensure_queue_dir()
        self._use_redis = False
        self._redis = None
        try:
            redis_url = os.environ.get('REDIS_URL')
            use_redis = os.environ.get('RETRY_QUEUE_USE_REDIS', '1')
            if redis_url and use_redis not in ('0', 'false', 'False'):
                import redis  # type: ignore
                self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
                # validate connection lazily
                self._use_redis = True
                self._zset_key = 'rssnews:retry_queue:zset'
                self._hash_key = 'rssnews:retry_queue:data'
        except Exception as e:
            logger.warning(f"Redis not available for retry queue, falling back to file: {e}")
            
    def _ensure_queue_dir(self):
        """Ensure queue directory exists"""
        queue_dir = os.path.dirname(self.queue_file)
        if queue_dir:
            os.makedirs(queue_dir, exist_ok=True)

    # ------------- File lock helpers -------------
    def _lock_paths(self):
        lock_path = f"{self.queue_file}.lock"
        return lock_path

    def _acquire_lock(self):
        lock_path = self._lock_paths()
        self._lock_fh = open(lock_path, 'a+')
        try:
            if os.name == 'nt':
                import msvcrt  # type: ignore
                msvcrt.locking(self._lock_fh.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl  # type: ignore
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_EX)
        except Exception:
            # Best-effort lock
            pass

    def _release_lock(self):
        try:
            if hasattr(self, '_lock_fh') and self._lock_fh:
                if os.name == 'nt':
                    import msvcrt  # type: ignore
                    msvcrt.locking(self._lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl  # type: ignore
                    fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
                self._lock_fh.close()
        except Exception:
            pass
    
    def add(self, url: str, headers: Dict[str, str], error: str, 
            context: Dict[str, Any] = None, max_attempts: int = 5):
        """Add item to retry queue"""
        # Calculate backoff: 2^attempt minutes with jitter
        attempt = 1
        backoff_minutes = (2 ** attempt) + random.uniform(0, 1)
        next_retry = datetime.now() + timedelta(minutes=backoff_minutes)

        if self._use_redis and self._redis is not None:
            try:
                payload = {
                    'url': url,
                    'headers': dict(headers) if headers else {},
                    'attempt': attempt,
                    'next_retry': next_retry.isoformat(),
                    'max_attempts': max_attempts,
                    'error': error,
                    'context': dict(context) if context else {}
                }
                score = next_retry.timestamp()
                pipe = self._redis.pipeline()
                pipe.hset(self._hash_key, url, json.dumps(payload))
                pipe.zadd(self._zset_key, {url: score})
                pipe.execute()
                logger.info(f"Added to retry queue (redis): {url} (attempt {attempt}/{max_attempts})")
                return
            except Exception as e:
                logger.warning(f"Redis enqueue failed, fallback to file: {e}")

        queue = self._load_queue()
        item = RetryItem(url=url, headers=headers, attempt=attempt, next_retry=next_retry,
                         max_attempts=max_attempts, error=error, context=context or {})
        queue.append(item)
        self._save_queue(queue)
        logger.info(f"Added to retry queue: {url} (attempt {attempt}/{max_attempts})")
    
    def get_ready_items(self, limit: int = 10) -> list[RetryItem]:
        """Get items ready for retry"""
        if self._use_redis and self._redis is not None:
            try:
                now_ts = datetime.now().timestamp()
                urls = self._redis.zrangebyscore(self._zset_key, min='-inf', max=now_ts, start=0, num=limit)
                items: List[RetryItem] = []
                if not urls:
                    return items
                raw = self._redis.hmget(self._hash_key, urls)
                for u, data in zip(urls, raw):
                    if not data:
                        continue
                    item_data = json.loads(data)
                    items.append(RetryItem(
                        url=item_data['url'],
                        headers=item_data.get('headers', {}),
                        attempt=item_data.get('attempt', 1),
                        next_retry=datetime.fromisoformat(item_data['next_retry']),
                        max_attempts=item_data.get('max_attempts', 5),
                        error=item_data.get('error', ''),
                        context=item_data.get('context', {})
                    ))
                return items
            except Exception as e:
                logger.warning(f"Redis read ready items failed, fallback to file: {e}")

        queue = self._load_queue()
        now = datetime.now()
        ready_items = [item for item in queue if item.next_retry <= now and item.attempt <= item.max_attempts]
        return ready_items[:limit]
    
    def remove(self, url: str):
        """Remove item from queue"""
        if self._use_redis and self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.zrem(self._zset_key, url)
                pipe.hdel(self._hash_key, url)
                pipe.execute()
                return
            except Exception as e:
                logger.warning(f"Redis remove failed, fallback to file: {e}")
        queue = self._load_queue()
        queue = [item for item in queue if item.url != url]
        self._save_queue(queue)
    
    def update_attempt(self, url: str) -> bool:
        """
        Update attempt count and backoff for item
        Returns True if should retry, False if max attempts reached
        """
        if self._use_redis and self._redis is not None:
            try:
                data = self._redis.hget(self._hash_key, url)
                if not data:
                    return False
                item_data = json.loads(data)
                attempt = int(item_data.get('attempt', 1)) + 1
                if attempt > int(item_data.get('max_attempts', 5)):
                    pipe = self._redis.pipeline()
                    pipe.zrem(self._zset_key, url)
                    pipe.hdel(self._hash_key, url)
                    pipe.execute()
                    logger.warning(f"Max retry attempts reached for {url}")
                    return False
                backoff_minutes = (2 ** attempt) + random.uniform(0, 2)
                next_retry = datetime.now() + timedelta(minutes=backoff_minutes)
                item_data['attempt'] = attempt
                item_data['next_retry'] = next_retry.isoformat()
                score = next_retry.timestamp()
                pipe = self._redis.pipeline()
                pipe.hset(self._hash_key, url, json.dumps(item_data))
                pipe.zadd(self._zset_key, {url: score})
                pipe.execute()
                logger.info(f"Updated retry for {url}: attempt {attempt}/{item_data.get('max_attempts', 5)}")
                return True
            except Exception as e:
                logger.warning(f"Redis update attempt failed, fallback to file: {e}")

        queue = self._load_queue()
        for item in queue:
            if item.url == url:
                item.attempt += 1
                if item.attempt > item.max_attempts:
                    queue = [i for i in queue if i.url != url]
                    self._save_queue(queue)
                    logger.warning(f"Max retry attempts reached for {url}")
                    return False
                backoff_minutes = (2 ** item.attempt) + random.uniform(0, 2)
                item.next_retry = datetime.now() + timedelta(minutes=backoff_minutes)
                self._save_queue(queue)
                logger.info(f"Updated retry for {url}: attempt {item.attempt}/{item.max_attempts}")
                return True
        return False
    
    def _load_queue(self) -> list[RetryItem]:
        """Load queue from disk"""
        if not os.path.exists(self.queue_file):
            return []
        
        try:
            self._acquire_lock()
            with open(self.queue_file, 'r') as f:
                data = json.load(f)
            
            queue = []
            for item_data in data:
                item = RetryItem(
                    url=item_data['url'],
                    headers=item_data['headers'],
                    attempt=item_data['attempt'],
                    next_retry=datetime.fromisoformat(item_data['next_retry']),
                    max_attempts=item_data['max_attempts'],
                    error=item_data['error'],
                    context=item_data.get('context', {})
                )
                queue.append(item)
            
            return queue
            
        except Exception as e:
            logger.error(f"Failed to load retry queue: {e}")
            return []
        finally:
            self._release_lock()
    
    def _save_queue(self, queue: list[RetryItem]):
        """Save queue to disk"""
        try:
            data = []
            for item in queue:
                data.append({
                    'url': item.url,
                    'headers': dict(item.headers) if item.headers else {},
                    'attempt': item.attempt,
                    'next_retry': item.next_retry.isoformat(),
                    'max_attempts': item.max_attempts,
                    'error': item.error,
                    'context': dict(item.context) if item.context else {}
                })
            
            self._acquire_lock()
            with open(self.queue_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save retry queue: {e}")
        finally:
            self._release_lock()

class HttpClient:
    """HTTP client with retry logic and rate limiting"""
    
    def __init__(self, user_agent: str = None, timeout: int = 30):
        self.session = requests.Session()
        self.timeout = timeout
        self.retry_queue = RetryQueue()
        
        # Set user agent
        user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def get(self, url: str, headers: Dict[str, str] = None, 
            context: Dict[str, Any] = None) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        GET request with retry logic
        Returns (response, final_url) or (None, error_message)
        """
        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)
        
        try:
            # SSRF guard: scheme + private/loopback/link-local/multicast/reserved and metadata
            try:
                parsed = requests.utils.urlparse(url)
                if parsed.scheme not in ("http", "https"):
                    error_msg = f"Unsupported scheme: {parsed.scheme}"
                    logger.warning(f"SSRF guard: {error_msg}")
                    return None, error_msg
                host = parsed.hostname or ""
                if host.lower() in ("localhost", "127.0.0.1", "::1"):
                    logger.warning("SSRF guard: Blocked host localhost/loopback")
                    return None, f"Blocked host: {host}"
                try:
                    infos = socket.getaddrinfo(host, None)
                    for fam, _, _, _, sockaddr in infos:
                        ip = sockaddr[0]
                        ip_obj = ipaddress.ip_address(ip)
                        if (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
                            or ip_obj.is_multicast or ip_obj.is_reserved):
                            logger.warning(f"SSRF guard: Blocked private address {ip}")
                            return None, f"Blocked host: {host}"
                        # Block cloud metadata endpoint
                        if str(ip_obj) == '169.254.169.254':
                            logger.warning("SSRF guard: Blocked metadata endpoint")
                            return None, f"Blocked metadata endpoint"
                except Exception:
                    # DNS/parse errors handled by requests later
                    pass
            except Exception:
                return None, "URL parsing failed"
            response = self.session.get(
                url,
                headers=request_headers,
                timeout=self.timeout,
                allow_redirects=True
            )
            
            # Check for rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                        logger.info(f"Rate limited, waiting {wait_time}s: {url}")
                        time.sleep(wait_time)
                        # Try once more after waiting
                        response = self.session.get(
                            url, 
                            headers=request_headers,
                            timeout=self.timeout,
                            allow_redirects=True
                        )
                    except ValueError:
                        pass
                
                if response.status_code == 429:
                    error_msg = f"Rate limited (429): {url}"
                    self.retry_queue.add(url, request_headers, error_msg, context)
                    return None, error_msg
            
            # Handle server errors (5xx) - add to retry queue
            if 500 <= response.status_code < 600:
                error_msg = f"Server error ({response.status_code}): {url}"
                self.retry_queue.add(url, request_headers, error_msg, context)
                return None, error_msg
            
            # Handle client errors (4xx) - don't retry, but log
            if 400 <= response.status_code < 500:
                error_msg = f"Client error ({response.status_code}): {url}"
                logger.warning(error_msg)
                return None, error_msg
            
            # Success or redirect
            final_url = response.url
            return response, final_url
            
        except requests.exceptions.Timeout:
            error_msg = f"Timeout: {url}"
            self.retry_queue.add(url, request_headers, error_msg, context)
            return None, error_msg
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error: {url} - {str(e)}"
            self.retry_queue.add(url, request_headers, error_msg, context)
            return None, error_msg
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {url} - {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def get_with_conditional_headers(self, url: str, etag: str = None, 
                                   last_modified: str = None) -> Tuple[Optional[requests.Response], Optional[str], bool]:
        """
        GET with conditional headers (If-None-Match, If-Modified-Since)
        Returns (response, final_url, was_cached)
        """
        headers = {}
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified
        
        response, final_url = self.get(url, headers)
        
        if response is None:
            return None, final_url, False
        
        # Check if content was not modified (304)
        was_cached = response.status_code == 304
        
        return response, final_url or url, was_cached
    
    def process_retry_queue(self, limit: int = 10) -> int:
        """
        Process items from retry queue
        Returns number of items processed successfully
        """
        ready_items = self.retry_queue.get_ready_items(limit)
        if not ready_items:
            logger.info("No items ready for retry")
            return 0
        
        success_count = 0
        
        for item in ready_items:
            logger.info(f"Retrying {item.url} (attempt {item.attempt}/{item.max_attempts})")
            
            response, final_url = self.get(item.url, item.headers, item.context)
            
            if response is not None:
                # Success - remove from queue
                self.retry_queue.remove(item.url)
                success_count += 1
                logger.info(f"Retry successful: {item.url}")
                
                # Here you could trigger further processing of the successful response
                # For now, we just log success
                
            else:
                # Failed again - update attempt count
                should_retry = self.retry_queue.update_attempt(item.url)
                if not should_retry:
                    logger.error(f"Giving up on {item.url} after {item.max_attempts} attempts")
        
        logger.info(f"Processed {len(ready_items)} retry items, {success_count} successful")
        return success_count
    
    def close(self):
        """Close the session"""
        self.session.close()
