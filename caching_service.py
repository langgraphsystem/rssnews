"""
Redis Caching Service
Provides caching layer for search results, trends, and system data
"""

import os
import json
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import hashlib

logger = logging.getLogger(__name__)


class CachingService:
    """Redis-based caching service for RSS News System"""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_client = None
        self.default_ttl = int(os.getenv('SEARCH_CACHE_TTL_SECONDS', '900'))  # 15 minutes

        # Initialize Redis connection
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            import redis

            # Parse Redis URL
            if self.redis_url.startswith('redis://'):
                self.redis_client = redis.from_url(self.redis_url, decode_responses=False)
            else:
                # Fallback to default connection
                self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)

            # Test connection
            self.redis_client.ping()
            logger.info("✅ Redis connection established")

        except ImportError:
            logger.warning("⚠️  Redis package not installed - caching disabled (optional)")
            self.redis_client = None
        except Exception as e:
            logger.warning(f"⚠️  Redis unavailable - caching disabled (optional): {type(e).__name__}")
            self.redis_client = None

    def is_available(self) -> bool:
        """Check if Redis is available"""
        try:
            if self.redis_client:
                self.redis_client.ping()
                return True
            return False
        except:
            return False

    def _make_key(self, prefix: str, data: Union[str, Dict, List]) -> str:
        """Create cache key from data"""
        if isinstance(data, str):
            content = data
        else:
            content = json.dumps(data, sort_keys=True)

        # Create hash for consistent key length
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"rss:{prefix}:{content_hash}"

    def cache_search_results(self, query: str, method: str, filters: Dict[str, Any],
                           results: List[Dict[str, Any]], ttl: int = None) -> bool:
        """Cache search results"""
        if not self.is_available():
            return False

        try:
            cache_data = {
                'query': query,
                'method': method,
                'filters': filters or {},
                'results': results,
                'timestamp': datetime.utcnow().isoformat(),
                'cached_at': datetime.utcnow().timestamp()
            }

            cache_key = self._make_key('search', {
                'query': query,
                'method': method,
                'filters': filters or {}
            })

            # Serialize data
            serialized_data = pickle.dumps(cache_data)

            # Store with TTL
            cache_ttl = ttl or self.default_ttl
            self.redis_client.setex(cache_key, cache_ttl, serialized_data)

            logger.debug(f"Cached search results: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to cache search results: {e}")
            return False

    def get_cached_search_results(self, query: str, method: str,
                                filters: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Get cached search results"""
        if not self.is_available():
            return None

        try:
            cache_key = self._make_key('search', {
                'query': query,
                'method': method,
                'filters': filters or {}
            })

            cached_data = self.redis_client.get(cache_key)
            if not cached_data:
                return None

            # Deserialize
            cache_data = pickle.loads(cached_data)

            # Validate cache freshness
            cached_at = cache_data.get('cached_at', 0)
            age_seconds = datetime.utcnow().timestamp() - cached_at

            if age_seconds > self.default_ttl:
                # Cache expired, remove it
                self.redis_client.delete(cache_key)
                return None

            logger.debug(f"Cache hit: {cache_key} (age: {int(age_seconds)}s)")
            return cache_data['results']

        except Exception as e:
            logger.error(f"Failed to get cached search results: {e}")
            return None

    def cache_trends(self, time_window_hours: int, trends: List[Dict[str, Any]],
                    ttl: int = None) -> bool:
        """Cache trend analysis results"""
        if not self.is_available():
            return False

        try:
            cache_data = {
                'time_window_hours': time_window_hours,
                'trends': trends,
                'timestamp': datetime.utcnow().isoformat(),
                'cached_at': datetime.utcnow().timestamp()
            }

            cache_key = self._make_key('trends', f"window_{time_window_hours}h")
            serialized_data = pickle.dumps(cache_data)

            # Cache trends for shorter time (trends change frequently)
            cache_ttl = ttl or min(600, self.default_ttl)  # 10 minutes max
            self.redis_client.setex(cache_key, cache_ttl, serialized_data)

            logger.debug(f"Cached trends: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to cache trends: {e}")
            return False

    def get_cached_trends(self, time_window_hours: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached trend results"""
        if not self.is_available():
            return None

        try:
            cache_key = self._make_key('trends', f"window_{time_window_hours}h")
            cached_data = self.redis_client.get(cache_key)

            if not cached_data:
                return None

            cache_data = pickle.loads(cached_data)

            # Check freshness
            cached_at = cache_data.get('cached_at', 0)
            age_seconds = datetime.utcnow().timestamp() - cached_at

            if age_seconds > 600:  # Trends expire after 10 minutes
                self.redis_client.delete(cache_key)
                return None

            logger.debug(f"Trends cache hit: {cache_key}")
            return cache_data['trends']

        except Exception as e:
            logger.error(f"Failed to get cached trends: {e}")
            return None

    def cache_system_health(self, health_data: Dict[str, Any], ttl: int = 300) -> bool:
        """Cache system health data"""
        if not self.is_available():
            return False

        try:
            cache_data = {
                'health': health_data,
                'cached_at': datetime.utcnow().timestamp()
            }

            cache_key = "rss:system:health"
            serialized_data = pickle.dumps(cache_data)

            # Health data cached for 5 minutes
            self.redis_client.setex(cache_key, ttl, serialized_data)
            return True

        except Exception as e:
            logger.error(f"Failed to cache system health: {e}")
            return False

    def get_cached_system_health(self) -> Optional[Dict[str, Any]]:
        """Get cached system health data"""
        if not self.is_available():
            return None

        try:
            cache_key = "rss:system:health"
            cached_data = self.redis_client.get(cache_key)

            if not cached_data:
                return None

            cache_data = pickle.loads(cached_data)
            return cache_data['health']

        except Exception as e:
            logger.error(f"Failed to get cached system health: {e}")
            return None

    def cache_domain_profiles(self, domain_profiles: List[Dict[str, Any]],
                            ttl: int = 3600) -> bool:
        """Cache domain profiles (authority scores)"""
        if not self.is_available():
            return False

        try:
            cache_data = {
                'domain_profiles': domain_profiles,
                'cached_at': datetime.utcnow().timestamp()
            }

            cache_key = "rss:domains:profiles"
            serialized_data = pickle.dumps(cache_data)

            # Domain profiles cached for 1 hour
            self.redis_client.setex(cache_key, ttl, serialized_data)
            return True

        except Exception as e:
            logger.error(f"Failed to cache domain profiles: {e}")
            return False

    def get_cached_domain_profiles(self) -> Optional[List[Dict[str, Any]]]:
        """Get cached domain profiles"""
        if not self.is_available():
            return None

        try:
            cache_key = "rss:domains:profiles"
            cached_data = self.redis_client.get(cache_key)

            if not cached_data:
                return None

            cache_data = pickle.loads(cached_data)
            return cache_data['domain_profiles']

        except Exception as e:
            logger.error(f"Failed to get cached domain profiles: {e}")
            return None

    def invalidate_cache(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern"""
        if not self.is_available():
            return 0

        try:
            keys = self.redis_client.keys(f"rss:{pattern}:*")
            if keys:
                count = self.redis_client.delete(*keys)
                logger.info(f"Invalidated {count} cache entries matching '{pattern}'")
                return count
            return 0

        except Exception as e:
            logger.error(f"Failed to invalidate cache: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.is_available():
            return {'error': 'Redis not available'}

        try:
            info = self.redis_client.info()
            keys = self.redis_client.keys("rss:*")

            # Count by prefix
            key_counts = {}
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                prefix = key_str.split(':')[1] if ':' in key_str else 'unknown'
                key_counts[prefix] = key_counts.get(prefix, 0) + 1

            return {
                'redis_version': info.get('redis_version', 'unknown'),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'total_keys': len(keys),
                'key_counts_by_type': key_counts,
                'cache_hit_ratio': self._calculate_hit_ratio(info),
                'uptime_seconds': info.get('uptime_in_seconds', 0)
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {'error': str(e)}

    def _calculate_hit_ratio(self, info: Dict) -> float:
        """Calculate cache hit ratio"""
        try:
            hits = info.get('keyspace_hits', 0)
            misses = info.get('keyspace_misses', 0)
            total = hits + misses

            if total == 0:
                return 0.0

            return round((hits / total) * 100, 2)

        except:
            return 0.0

    def warm_cache(self, ranking_api) -> Dict[str, int]:
        """Warm up cache with popular queries and data"""
        if not self.is_available():
            return {'error': 'Redis not available'}

        try:
            warmed = {'searches': 0, 'trends': 0, 'health': 0}

            # Popular search queries to pre-cache
            popular_queries = [
                'artificial intelligence',
                'machine learning',
                'technology news',
                'climate change',
                'politics',
                'economy',
                'sports',
                'science'
            ]

            # Pre-cache popular searches
            for query in popular_queries:
                try:
                    from ranking_api import SearchRequest
                    request = SearchRequest(query=query, method='hybrid', limit=10)
                    response = ranking_api.search(request)

                    if response and response.results:
                        if self.cache_search_results(query, 'hybrid', {}, response.results):
                            warmed['searches'] += 1

                except Exception as e:
                    logger.debug(f"Failed to warm cache for '{query}': {e}")

            # Pre-cache system health
            try:
                health = ranking_api.get_system_health()
                if health and self.cache_system_health(health):
                    warmed['health'] = 1
            except Exception as e:
                logger.debug(f"Failed to warm health cache: {e}")

            # Pre-cache trends
            try:
                if hasattr(ranking_api, 'clustering_service'):
                    trends = ranking_api.clustering_service.detect_trends(24)
                    if trends and trends.get('trends'):
                        if self.cache_trends(24, trends['trends']):
                            warmed['trends'] = 1
            except Exception as e:
                logger.debug(f"Failed to warm trends cache: {e}")

            logger.info(f"Cache warming completed: {warmed}")
            return warmed

        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            return {'error': str(e)}


def main():
    """CLI interface for caching service"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News Caching Service')
    parser.add_argument('command', choices=['stats', 'clear', 'test', 'warm'],
                       help='Command to run')
    parser.add_argument('--pattern', type=str, help='Pattern for cache clearing')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Initialize caching service
    cache = CachingService()

    if args.command == 'stats':
        # Show cache statistics
        stats = cache.get_cache_stats()
        print("📊 Redis Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    elif args.command == 'clear':
        # Clear cache
        pattern = args.pattern or '*'
        count = cache.invalidate_cache(pattern)
        print(f"🗑️  Cleared {count} cache entries matching '{pattern}'")

    elif args.command == 'test':
        # Test Redis connection
        if cache.is_available():
            print("✅ Redis connection successful")

            # Test basic operations
            test_key = "rss:test:connection"
            cache.redis_client.setex(test_key, 60, "test_value")

            value = cache.redis_client.get(test_key)
            if value == b"test_value":
                print("✅ Redis read/write test passed")
                cache.redis_client.delete(test_key)
            else:
                print("❌ Redis read/write test failed")
        else:
            print("❌ Redis connection failed")

    elif args.command == 'warm':
        # Warm up cache
        print("🔥 Cache warming not available without ranking API instance")
        print("Use: from caching_service import CachingService; cache.warm_cache(api)")


if __name__ == "__main__":
    main()