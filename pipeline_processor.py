"""
Production-grade 8-Stage RSS Processing Pipeline
High-throughput, fault-tolerant pipeline with idempotency guarantees and comprehensive monitoring.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4
import traceback

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field, validator
import fasttext
import langdetect
from readability import Document
from bs4 import BeautifulSoup
import dateutil.parser as date_parser
import newspaper
from textstat import flesch_reading_ease, flesch_kincaid_grade

from monitoring import MetricsCollector, Timer
from batch_planner import BatchCandidate
from config import Config

logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """Pipeline processing stages"""
    STAGE_0_VALIDATION = "stage_0_validation"
    STAGE_1_FEED_HEALTH = "stage_1_feed_health"
    STAGE_2_DEDUPLICATION = "stage_2_deduplication" 
    STAGE_3_NORMALIZATION = "stage_3_normalization"
    STAGE_4_TEXT_CLEANING = "stage_4_text_cleaning"
    STAGE_5_INDEXING = "stage_5_indexing"
    STAGE_6_CHUNKING = "stage_6_chunking"
    STAGE_7_SEARCH_INDEXING = "stage_7_search_indexing"
    STAGE_8_DIAGNOSTICS = "stage_8_diagnostics"


class ProcessingStatus(Enum):
    """Processing status for individual articles"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    REJECTED = "rejected"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"


class RejectReason(Enum):
    """Reasons for article rejection"""
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_CONTENT = "duplicate_content"
    LOW_QUALITY = "low_quality"
    INVALID_LANGUAGE = "invalid_language"
    TOO_SHORT = "too_short"
    TOO_OLD = "too_old"
    PAYWALL = "paywall"
    INVALID_CONTENT = "invalid_content"
    EXTRACTION_FAILED = "extraction_failed"
    FEED_QUOTA_EXCEEDED = "feed_quota_exceeded"
    DOMAIN_BLACKLISTED = "domain_blacklisted"


@dataclass
class ProcessingContext:
    """Context passed through pipeline stages"""
    batch_id: str
    worker_id: str
    correlation_id: str
    trace_id: str
    processing_version: str = "1.0"
    started_at: datetime = field(default_factory=datetime.utcnow)
    config: Dict[str, Any] = field(default_factory=dict)
    stage_timings: Dict[str, float] = field(default_factory=dict)
    stage_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ArticleData:
    """Article data structure passed through pipeline"""
    # Core identification
    id: int
    feed_id: int
    url: str
    canonical_url: Optional[str] = None
    url_hash: str = ""
    text_hash: Optional[str] = None
    
    # Content
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    clean_text: Optional[str] = None
    full_text: Optional[str] = None
    
    # Metadata
    authors: List[str] = field(default_factory=list)
    published_at: Optional[datetime] = None
    published_at_raw: Optional[str] = None
    language_raw: Optional[str] = None
    language_detected: Optional[str] = None
    language_confidence: float = 0.0
    
    # Processing state
    status: ProcessingStatus = ProcessingStatus.PENDING
    processing_stage: ProcessingStage = ProcessingStage.STAGE_0_VALIDATION
    idempotency_key: Optional[str] = None
    
    # Quality metrics
    word_count: int = 0
    char_count: int = 0
    quality_score: float = 0.0
    quality_flags: List[str] = field(default_factory=list)
    readability_score: Optional[float] = None
    
    # Classification
    category: Optional[str] = None
    category_confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    
    # Deduplication
    is_duplicate: bool = False
    dup_reason: Optional[str] = None
    dup_original_id: Optional[str] = None
    dup_similarity_score: Optional[float] = None
    
    # Processing metadata
    retry_count: int = 0
    error_log: List[Dict[str, Any]] = field(default_factory=list)
    processing_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    fetched_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    
    def add_error(self, stage: str, error_type: str, message: str, details: Optional[Dict] = None):
        """Add error to article's error log"""
        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "error_type": error_type,
            "message": message,
            "details": details or {},
            "trace_id": getattr(self, 'trace_id', None)
        }
        self.error_log.append(error_entry)
    
    def add_quality_flag(self, flag: str, severity: str = "warning"):
        """Add quality flag to article"""
        flag_entry = f"{severity}:{flag}"
        if flag_entry not in self.quality_flags:
            self.quality_flags.append(flag_entry)
    
    def set_rejected(self, reason: RejectReason, message: str = ""):
        """Mark article as rejected with reason"""
        self.status = ProcessingStatus.REJECTED
        self.dup_reason = reason.value
        if message:
            self.add_error(
                self.processing_stage.value,
                "rejection",
                message,
                {"reason": reason.value}
            )


class PipelineStage(ABC):
    """Abstract base class for pipeline stages"""
    
    def __init__(self, 
                 db_pool: asyncpg.Pool,
                 redis_client: redis.Redis,
                 metrics: MetricsCollector,
                 config: Config):
        self.db_pool = db_pool
        self.redis = redis_client
        self.metrics = metrics
        self.config = config
        self.stage_name = self.__class__.__name__
    
    @abstractmethod
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Process a batch of articles"""
        pass
    
    @abstractmethod
    def get_stage_enum(self) -> ProcessingStage:
        """Get the stage enum for this processor"""
        pass
    
    async def _start_stage_timing(self, context: ProcessingContext) -> Timer:
        """Start timing for this stage"""
        timer = Timer(self.metrics, f"pipeline.stage.{self.stage_name.lower()}.duration")
        context.stage_timings[self.stage_name] = time.time()
        return timer
    
    async def _end_stage_timing(self, context: ProcessingContext, timer: Timer):
        """End timing for this stage"""
        elapsed = time.time() - context.stage_timings[self.stage_name]
        context.stage_timings[self.stage_name] = elapsed
        timer.stop()
        
        await self.metrics.histogram(f"pipeline.stage.{self.stage_name.lower()}.duration", elapsed)
    
    async def _record_stage_metrics(self,
                                  context: ProcessingContext,
                                  articles_input: int,
                                  articles_output: int,
                                  articles_rejected: int,
                                  articles_errors: int):
        """Record metrics for this stage"""
        stage_metrics = {
            "articles_input": articles_input,
            "articles_output": articles_output,
            "articles_rejected": articles_rejected,
            "articles_errors": articles_errors,
            "processing_time": context.stage_timings.get(self.stage_name, 0),
            "success_rate": articles_output / max(articles_input, 1),
            "rejection_rate": articles_rejected / max(articles_input, 1),
            "error_rate": articles_errors / max(articles_input, 1)
        }
        
        context.stage_metrics[self.stage_name] = stage_metrics
        
        # Record individual metrics
        await self.metrics.histogram(f"pipeline.stage.{self.stage_name.lower()}.input_count", articles_input)
        await self.metrics.histogram(f"pipeline.stage.{self.stage_name.lower()}.output_count", articles_output)
        await self.metrics.histogram(f"pipeline.stage.{self.stage_name.lower()}.rejection_rate", stage_metrics["rejection_rate"])
        await self.metrics.histogram(f"pipeline.stage.{self.stage_name.lower()}.success_rate", stage_metrics["success_rate"])


class Stage0ValidationProcessor(PipelineStage):
    """Stage 0: Article validation and basic sanity checks"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_0_VALIDATION
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Validate articles and perform basic sanity checks"""
        timer = await self._start_stage_timing(context)
        
        valid_articles = []
        rejected_count = 0
        error_count = 0
        
        try:
            for article in articles:
                try:
                    article.processing_stage = ProcessingStage.STAGE_0_VALIDATION
                    
                    # Generate idempotency key if not present
                    if not article.idempotency_key:
                        article.idempotency_key = f"article_{article.id}_{context.batch_id}"
                    
                    # Basic URL validation
                    if not article.url or len(article.url) < 10:
                        article.set_rejected(RejectReason.INVALID_CONTENT, "Invalid or missing URL")
                        rejected_count += 1
                        continue
                    
                    # Generate URL hash for deduplication
                    article.url_hash = hashlib.sha256(article.url.encode()).hexdigest()
                    
                    # Basic content validation
                    if not article.title and not article.content:
                        article.set_rejected(RejectReason.INVALID_CONTENT, "No title or content")
                        rejected_count += 1
                        continue
                    
                    # Check article age
                    if article.fetched_at:
                        age_hours = (datetime.utcnow() - article.fetched_at).total_seconds() / 3600
                        max_age_hours = self.config.get('pipeline.max_article_age_hours', 168)  # 7 days
                        
                        if age_hours > max_age_hours:
                            article.set_rejected(RejectReason.TOO_OLD, f"Article is {age_hours:.1f} hours old")
                            rejected_count += 1
                            continue
                    
                    # Basic content length checks
                    content_text = (article.content or "") + (article.title or "")
                    if len(content_text) < 100:
                        article.set_rejected(RejectReason.TOO_SHORT, "Content too short")
                        rejected_count += 1
                        continue
                    
                    # Check for obviously invalid content
                    if self._is_invalid_content(article):
                        article.set_rejected(RejectReason.INVALID_CONTENT, "Invalid content detected")
                        rejected_count += 1
                        continue
                    
                    # URL canonicalization
                    article.canonical_url = self._canonicalize_url(article.url)
                    
                    # Mark as valid
                    article.status = ProcessingStatus.PROCESSING
                    valid_articles.append(article)
                    
                except Exception as e:
                    logger.error(f"Error validating article {article.id}: {e}", exc_info=True)
                    article.add_error("validation", "processing_error", str(e))
                    error_count += 1
            
            await self._end_stage_timing(context, timer)
            await self._record_stage_metrics(context, len(articles), len(valid_articles), rejected_count, error_count)
            
            logger.info(f"Stage 0 validation: {len(valid_articles)} valid, {rejected_count} rejected, {error_count} errors")
            
            return valid_articles
            
        except Exception as e:
            logger.error(f"Critical error in Stage 0 validation: {e}", exc_info=True)
            await self.metrics.increment("pipeline.stage.validation.critical_error")
            raise
    
    def _is_invalid_content(self, article: ArticleData) -> bool:
        """Check for obviously invalid content patterns"""
        content = (article.content or "") + (article.title or "")
        
        # Check for common invalid patterns
        invalid_patterns = [
            r"404\s+(not\s+found|error)",
            r"access\s+denied",
            r"page\s+not\s+found",
            r"site\s+maintenance",
            r"temporarily\s+unavailable",
            r"javascript\s+(required|disabled)",
            r"please\s+enable\s+javascript"
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, content.lower()):
                return True
        
        # Check for suspicious character patterns (might indicate encoding issues)
        weird_chars = len(re.findall(r'[^\w\s\-.,!?;:()\[\]{}"\'/\\]', content))
        if weird_chars > len(content) * 0.1:  # More than 10% weird characters
            return True
        
        return False
    
    def _canonicalize_url(self, url: str) -> str:
        """Canonicalize URL for deduplication"""
        # Remove common tracking parameters
        tracking_params = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
            'fbclid', 'gclid', 'msclkid', 'ref', 'referrer', 'source',
            'campaign_id', 'ad_id', 'click_id', 'affiliate_id'
        ]
        
        # Parse URL and remove tracking params
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        
        parsed = urlparse(url.lower().strip())
        
        if parsed.query:
            query_params = parse_qs(parsed.query)
            filtered_params = {
                k: v for k, v in query_params.items() 
                if k.lower() not in tracking_params
            }
            clean_query = urlencode(filtered_params, doseq=True) if filtered_params else ""
        else:
            clean_query = ""
        
        # Remove fragment (hash)
        canonical = urlunparse((
            parsed.scheme or 'https',
            parsed.netloc,
            parsed.path.rstrip('/') or '/',
            parsed.params,
            clean_query,
            ""  # Remove fragment
        ))
        
        return canonical


class Stage1FeedHealthProcessor(PipelineStage):
    """Stage 1: Feed health validation and quota management"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_1_FEED_HEALTH
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Validate feed health and manage quotas"""
        timer = await self._start_stage_timing(context)
        
        # Get feed health data
        feed_ids = list(set(article.feed_id for article in articles))
        feed_health = await self._get_feed_health_data(feed_ids)
        
        valid_articles = []
        rejected_count = 0
        error_count = 0
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_1_FEED_HEALTH
                
                health_data = feed_health.get(article.feed_id)
                if not health_data:
                    article.add_error("feed_health", "missing_data", "Feed health data not found")
                    error_count += 1
                    continue
                
                # Check feed health score
                min_health_score = self.config.get('feeds.min_health_score', 50)
                if health_data['health_score'] < min_health_score:
                    article.set_rejected(
                        RejectReason.LOW_QUALITY,
                        f"Feed health score {health_data['health_score']} below threshold {min_health_score}"
                    )
                    rejected_count += 1
                    continue
                
                # Check daily quota
                if health_data['daily_quota'] > 0:
                    if health_data['daily_processed'] >= health_data['daily_quota']:
                        article.set_rejected(
                            RejectReason.FEED_QUOTA_EXCEEDED,
                            f"Feed daily quota {health_data['daily_quota']} exceeded"
                        )
                        rejected_count += 1
                        continue
                
                # Check domain blacklist
                domain = self._extract_domain(article.url)
                if await self._is_domain_blacklisted(domain):
                    article.set_rejected(
                        RejectReason.DOMAIN_BLACKLISTED,
                        f"Domain {domain} is blacklisted"
                    )
                    rejected_count += 1
                    continue
                
                # Add feed metadata to article
                article.processing_metadata['feed_health'] = {
                    'health_score': health_data['health_score'],
                    'trust_score': health_data['trust_score'],
                    'domain': health_data['domain']
                }
                
                valid_articles.append(article)
                
            except Exception as e:
                logger.error(f"Error in feed health check for article {article.id}: {e}", exc_info=True)
                article.add_error("feed_health", "processing_error", str(e))
                error_count += 1
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(valid_articles), rejected_count, error_count)
        
        logger.info(f"Stage 1 feed health: {len(valid_articles)} valid, {rejected_count} rejected, {error_count} errors")
        
        return valid_articles
    
    async def _get_feed_health_data(self, feed_ids: List[int]) -> Dict[int, Dict]:
        """Get feed health data for given feed IDs"""
        if not feed_ids:
            return {}
        
        # Try cache first
        cache_keys = [f"feed_health:{feed_id}" for feed_id in feed_ids]
        cached_data = await self.redis.mget(cache_keys)
        
        cached_feeds = {}
        missing_feeds = []
        
        for i, data in enumerate(cached_data):
            if data:
                try:
                    cached_feeds[feed_ids[i]] = json.loads(data)
                except json.JSONDecodeError:
                    missing_feeds.append(feed_ids[i])
            else:
                missing_feeds.append(feed_ids[i])
        
        # Fetch missing data from database
        if missing_feeds:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, domain, trust_score, health_score, daily_quota, daily_processed,
                           error_rate_24h, duplicate_rate_24h, consecutive_failures
                    FROM feeds 
                    WHERE id = ANY($1) AND status = 'active'
                """, missing_feeds)
                
                for row in rows:
                    feed_data = dict(row)
                    cached_feeds[row['id']] = feed_data
                    
                    # Cache for 5 minutes
                    await self.redis.setex(
                        f"feed_health:{row['id']}",
                        300,
                        json.dumps(feed_data, default=str)
                    )
        
        return cached_feeds
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    
    async def _is_domain_blacklisted(self, domain: str) -> bool:
        """Check if domain is blacklisted"""
        # Check Redis blacklist cache
        is_blacklisted = await self.redis.sismember("blacklisted_domains", domain)
        return bool(is_blacklisted)


class Stage2DeduplicationProcessor(PipelineStage):
    """Stage 2: Advanced deduplication with multiple strategies"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_2_DEDUPLICATION
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Perform multi-level deduplication"""
        timer = await self._start_stage_timing(context)
        
        unique_articles = []
        duplicate_count = 0
        error_count = 0
        
        # Group articles for batch processing
        url_hashes = [article.url_hash for article in articles]
        existing_articles = await self._get_existing_articles(url_hashes)
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_2_DEDUPLICATION
                
                # Generate text hash if content is available
                if article.content:
                    article.text_hash = hashlib.sha256(
                        (article.content or "").encode('utf-8', errors='ignore')
                    ).hexdigest()
                
                # Check for URL duplicates
                if article.url_hash in existing_articles:
                    existing = existing_articles[article.url_hash]
                    article.is_duplicate = True
                    article.dup_reason = RejectReason.DUPLICATE_URL.value
                    article.dup_original_id = existing['article_id']
                    article.dup_similarity_score = 1.0
                    article.status = ProcessingStatus.DUPLICATE
                    duplicate_count += 1
                    continue
                
                # Check for content duplicates using text hash
                if article.text_hash:
                    content_duplicate = await self._find_content_duplicate(article)
                    if content_duplicate:
                        article.is_duplicate = True
                        article.dup_reason = RejectReason.DUPLICATE_CONTENT.value
                        article.dup_original_id = content_duplicate['article_id']
                        article.dup_similarity_score = content_duplicate['similarity']
                        article.status = ProcessingStatus.DUPLICATE
                        duplicate_count += 1
                        continue
                
                # Advanced semantic deduplication (optional, expensive)
                if self.config.get('deduplication.use_semantic', False):
                    semantic_duplicate = await self._find_semantic_duplicate(article)
                    if semantic_duplicate:
                        article.is_duplicate = True
                        article.dup_reason = RejectReason.DUPLICATE_CONTENT.value
                        article.dup_original_id = semantic_duplicate['article_id']
                        article.dup_similarity_score = semantic_duplicate['similarity']
                        article.status = ProcessingStatus.DUPLICATE
                        duplicate_count += 1
                        continue
                
                unique_articles.append(article)
                
            except Exception as e:
                logger.error(f"Error in deduplication for article {article.id}: {e}", exc_info=True)
                article.add_error("deduplication", "processing_error", str(e))
                error_count += 1
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(unique_articles), duplicate_count, error_count)
        
        logger.info(f"Stage 2 deduplication: {len(unique_articles)} unique, {duplicate_count} duplicates, {error_count} errors")
        
        return unique_articles
    
    async def _get_existing_articles(self, url_hashes: List[str]) -> Dict[str, Dict]:
        """Get existing articles by URL hash"""
        if not url_hashes:
            return {}
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT url_hash, article_id, created_at
                FROM articles_index
                WHERE url_hash = ANY($1)
                  AND created_at > NOW() - INTERVAL '30 days'
            """, url_hashes)
            
            return {row['url_hash']: dict(row) for row in rows}
    
    async def _find_content_duplicate(self, article: ArticleData) -> Optional[Dict]:
        """Find content duplicate using text hash"""
        if not article.text_hash:
            return None
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT article_id, url, title
                FROM articles_index
                WHERE text_hash = $1
                  AND created_at > NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT 1
            """, article.text_hash)
            
            if row:
                return {
                    'article_id': row['article_id'],
                    'similarity': 1.0,
                    'url': row['url'],
                    'title': row['title']
                }
        
        return None
    
    async def _find_semantic_duplicate(self, article: ArticleData) -> Optional[Dict]:
        """Find semantic duplicate using advanced similarity (placeholder)"""
        # This would implement more advanced semantic similarity
        # using embeddings, MinHash, or other techniques
        # For now, return None (disabled)
        return None


class Stage3NormalizationProcessor(PipelineStage):
    """Stage 3: Data normalization and language detection"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize FastText model (would be loaded from disk in production)
        # self.lang_detector = fasttext.load_model('lid.176.bin')
        self.lang_detector = None  # Placeholder
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_3_NORMALIZATION
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Normalize article data and detect language"""
        timer = await self._start_stage_timing(context)
        
        processed_articles = []
        rejected_count = 0
        error_count = 0
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_3_NORMALIZATION
                
                # Language detection
                await self._detect_language(article)
                
                # Date normalization
                await self._normalize_dates(article)
                
                # Author normalization
                await self._normalize_authors(article)
                
                # Title and content normalization
                await self._normalize_text_fields(article)
                
                # Category classification (basic)
                await self._classify_category(article)
                
                # Check if language is supported
                supported_languages = self.config.get('pipeline.supported_languages', ['en', 'es', 'fr', 'de'])
                if article.language_detected not in supported_languages:
                    article.set_rejected(
                        RejectReason.INVALID_LANGUAGE,
                        f"Unsupported language: {article.language_detected}"
                    )
                    rejected_count += 1
                    continue
                
                processed_articles.append(article)
                
            except Exception as e:
                logger.error(f"Error in normalization for article {article.id}: {e}", exc_info=True)
                article.add_error("normalization", "processing_error", str(e))
                error_count += 1
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(processed_articles), rejected_count, error_count)
        
        logger.info(f"Stage 3 normalization: {len(processed_articles)} processed, {rejected_count} rejected, {error_count} errors")
        
        return processed_articles
    
    async def _detect_language(self, article: ArticleData):
        """Detect article language using FastText and fallback methods"""
        text_for_detection = (article.title or "") + " " + (article.content or "")
        text_for_detection = text_for_detection.strip()[:1000]  # Use first 1000 chars
        
        if not text_for_detection:
            article.language_detected = "en"  # Default
            article.language_confidence = 0.5
            return
        
        try:
            # Try FastText first (if available)
            if self.lang_detector:
                predictions = self.lang_detector.predict(text_for_detection, k=1)
                language = predictions[0][0].replace('__label__', '')
                confidence = predictions[1][0]
                
                article.language_detected = language[:2]  # Get ISO 639-1 code
                article.language_confidence = confidence
            else:
                # Fallback to langdetect
                try:
                    import langdetect
                    detected = langdetect.detect_langs(text_for_detection)
                    if detected:
                        article.language_detected = detected[0].lang
                        article.language_confidence = detected[0].prob
                    else:
                        article.language_detected = "en"
                        article.language_confidence = 0.5
                except:
                    article.language_detected = "en"
                    article.language_confidence = 0.5
        
        except Exception as e:
            logger.warning(f"Language detection failed for article {article.id}: {e}")
            article.language_detected = article.language_raw or "en"
            article.language_confidence = 0.3
    
    async def _normalize_dates(self, article: ArticleData):
        """Normalize published dates from various formats"""
        if article.published_at:
            return  # Already normalized
        
        if not article.published_at_raw:
            # Use fetched_at as fallback
            article.published_at = article.fetched_at
            article.published_is_estimated = True
            return
        
        try:
            # Try to parse the raw date string
            parsed_date = date_parser.parse(article.published_at_raw)
            
            # Validate date (not in future, not too old)
            now = datetime.utcnow()
            if parsed_date > now + timedelta(hours=1):  # Allow 1 hour clock skew
                article.published_at = article.fetched_at
                article.published_is_estimated = True
                article.add_quality_flag("future_date", "warning")
            elif parsed_date < now - timedelta(days=365*2):  # Older than 2 years
                article.add_quality_flag("very_old", "info")
                article.published_at = parsed_date
            else:
                article.published_at = parsed_date
                
        except Exception as e:
            logger.debug(f"Failed to parse date '{article.published_at_raw}' for article {article.id}: {e}")
            article.published_at = article.fetched_at
            article.published_is_estimated = True
            article.add_quality_flag("unparseable_date", "warning")
    
    async def _normalize_authors(self, article: ArticleData):
        """Normalize author names"""
        if not article.authors:
            return
        
        normalized_authors = []
        for author in article.authors:
            if not author or not isinstance(author, str):
                continue
            
            # Clean up author name
            author = author.strip()
            author = re.sub(r'\s+', ' ', author)  # Normalize whitespace
            
            # Remove common prefixes/suffixes
            author = re.sub(r'^(by\s+|author:\s*)', '', author, flags=re.IGNORECASE)
            author = re.sub(r'\s*\([^)]*\)$', '', author)  # Remove parenthetical at end
            
            # Skip if too short or looks invalid
            if len(author) < 2 or len(author) > 100:
                continue
            
            # Skip obvious non-names
            if re.match(r'^(admin|editor|staff|unknown|anonymous)$', author, re.IGNORECASE):
                continue
            
            normalized_authors.append(author)
        
        article.authors = normalized_authors[:5]  # Limit to 5 authors
    
    async def _normalize_text_fields(self, article: ArticleData):
        """Normalize title and content fields"""
        # Title normalization
        if article.title:
            article.title = article.title.strip()
            article.title = re.sub(r'\s+', ' ', article.title)  # Normalize whitespace
            article.title = article.title[:500]  # Limit length
        
        # Content basic normalization (more detailed cleaning in next stage)
        if article.content:
            # Remove excessive whitespace
            article.content = re.sub(r'\s+', ' ', article.content)
            article.content = article.content.strip()
    
    async def _classify_category(self, article: ArticleData):
        """Basic category classification (placeholder for ML model)"""
        # This would use a trained ML model in production
        # For now, use simple keyword-based classification
        
        text = ((article.title or "") + " " + (article.content or "")).lower()
        
        categories = {
            'technology': ['tech', 'software', 'ai', 'computer', 'digital', 'internet'],
            'politics': ['election', 'government', 'congress', 'senate', 'president', 'policy'],
            'business': ['market', 'stock', 'economy', 'finance', 'company', 'earnings'],
            'sports': ['game', 'team', 'player', 'championship', 'league', 'score'],
            'health': ['medical', 'health', 'doctor', 'hospital', 'disease', 'treatment'],
            'science': ['research', 'study', 'scientist', 'discovery', 'experiment'],
            'entertainment': ['movie', 'music', 'celebrity', 'show', 'entertainment']
        }
        
        best_category = None
        best_score = 0
        
        for category, keywords in categories.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > best_score:
                best_score = score
                best_category = category
        
        if best_category and best_score >= 2:  # Minimum 2 keyword matches
            article.category = best_category
            article.category_confidence = min(0.8, best_score / 10.0)
        else:
            article.category = "general"
            article.category_confidence = 0.5


class Stage4TextCleaningProcessor(PipelineStage):
    """Stage 4: Advanced text cleaning and content extraction"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_4_TEXT_CLEANING
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Clean and extract article text content"""
        timer = await self._start_stage_timing(context)
        
        processed_articles = []
        rejected_count = 0
        error_count = 0
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_4_TEXT_CLEANING
                
                # Extract clean text from HTML content
                if article.content:
                    article.clean_text = await self._extract_clean_text(article.content)
                
                # Calculate text metrics
                await self._calculate_text_metrics(article)
                
                # Quality assessment
                quality_score = await self._assess_content_quality(article)
                article.quality_score = quality_score
                
                # Check minimum quality threshold
                min_quality = self.config.get('pipeline.min_quality_score', 0.3)
                if quality_score < min_quality:
                    article.set_rejected(
                        RejectReason.LOW_QUALITY,
                        f"Quality score {quality_score:.2f} below threshold {min_quality}"
                    )
                    rejected_count += 1
                    continue
                
                # Extract keywords and entities (basic)
                await self._extract_keywords(article)
                
                processed_articles.append(article)
                
            except Exception as e:
                logger.error(f"Error in text cleaning for article {article.id}: {e}", exc_info=True)
                article.add_error("text_cleaning", "processing_error", str(e))
                error_count += 1
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(processed_articles), rejected_count, error_count)
        
        logger.info(f"Stage 4 text cleaning: {len(processed_articles)} processed, {rejected_count} rejected, {error_count} errors")
        
        return processed_articles
    
    async def _extract_clean_text(self, html_content: str) -> str:
        """Extract clean text from HTML content"""
        try:
            # Use readability for main content extraction
            doc = Document(html_content)
            clean_html = doc.content()
            
            # Parse with BeautifulSoup for final cleaning
            soup = BeautifulSoup(clean_html, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize paragraph breaks
            text = re.sub(r' +', ' ', text)  # Normalize spaces
            text = text.strip()
            
            return text
            
        except Exception as e:
            logger.warning(f"Failed to extract clean text: {e}")
            # Fallback: simple HTML stripping
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text().strip()
    
    async def _calculate_text_metrics(self, article: ArticleData):
        """Calculate text-based metrics"""
        clean_text = article.clean_text or ""
        
        # Basic counts
        article.char_count = len(clean_text)
        article.word_count = len(clean_text.split()) if clean_text else 0
        
        # Readability scores
        if article.word_count > 10:
            try:
                article.readability_score = flesch_reading_ease(clean_text)
            except:
                article.readability_score = None
    
    async def _assess_content_quality(self, article: ArticleData) -> float:
        """Assess overall content quality (0-1 score)"""
        score = 0.0
        factors = []
        
        # Word count factor (sweet spot around 300-800 words)
        if article.word_count:
            if 100 <= article.word_count <= 200:
                word_score = 0.7
            elif 200 <= article.word_count <= 1000:
                word_score = 1.0
            elif 1000 <= article.word_count <= 2000:
                word_score = 0.9
            elif article.word_count > 2000:
                word_score = 0.8
            else:  # < 100 words
                word_score = max(0.1, article.word_count / 100.0)
            
            factors.append(('word_count', word_score, 0.3))
        
        # Title quality
        title_score = 0.5
        if article.title:
            title_len = len(article.title.split())
            if 5 <= title_len <= 15:
                title_score = 1.0
            elif 3 <= title_len <= 20:
                title_score = 0.8
            else:
                title_score = 0.6
        
        factors.append(('title', title_score, 0.2))
        
        # Language confidence
        lang_score = min(1.0, article.language_confidence * 2)  # Scale to 0-1
        factors.append(('language', lang_score, 0.2))
        
        # Readability
        readability_score = 0.7  # Default
        if article.readability_score is not None:
            # Flesch Reading Ease: 0-100, higher is better
            if article.readability_score >= 60:
                readability_score = 1.0
            elif article.readability_score >= 30:
                readability_score = 0.8
            else:
                readability_score = 0.6
        
        factors.append(('readability', readability_score, 0.1))
        
        # Author presence
        author_score = 1.0 if article.authors else 0.5
        factors.append(('authors', author_score, 0.1))
        
        # Published date presence
        date_score = 0.8 if not article.published_is_estimated else 0.6
        factors.append(('date', date_score, 0.1))
        
        # Calculate weighted average
        total_weight = sum(weight for _, _, weight in factors)
        if total_weight > 0:
            score = sum(score * weight for _, score, weight in factors) / total_weight
        
        # Apply quality flags penalties
        penalty = len([f for f in article.quality_flags if f.startswith('error:')]) * 0.1
        penalty += len([f for f in article.quality_flags if f.startswith('warning:')]) * 0.05
        
        score = max(0.0, min(1.0, score - penalty))
        
        return score
    
    async def _extract_keywords(self, article: ArticleData):
        """Extract basic keywords from content (placeholder for advanced NLP)"""
        text = (article.clean_text or "").lower()
        
        # Simple keyword extraction using word frequency
        # In production, this would use proper NLP libraries like spaCy or NLTK
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text)
        
        # Filter out common stop words (simplified list)
        stop_words = {
            'that', 'with', 'have', 'this', 'will', 'from', 'they', 'been', 'said',
            'each', 'which', 'their', 'time', 'about', 'would', 'there', 'could',
            'other', 'after', 'first', 'well', 'many', 'some', 'these', 'more'
        }
        
        filtered_words = [word for word in words if word not in stop_words]
        
        # Count frequency and take top keywords
        from collections import Counter
        word_freq = Counter(filtered_words)
        
        # Extract top 10 keywords
        article.keywords = [word for word, count in word_freq.most_common(10) if count >= 2]


class Stage5IndexingProcessor(PipelineStage):
    """Stage 5: Create enriched article passport and prepare for indexing"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_5_INDEXING
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Create article index entries"""
        timer = await self._start_stage_timing(context)
        
        # Batch insert into articles_index
        insert_data = []
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_5_INDEXING
                
                # Generate stable article ID
                article_id = self._generate_article_id(article)
                
                # Prepare index data
                index_entry = {
                    'article_id': article_id,
                    'raw_article_id': article.id,
                    'feed_id': article.feed_id,
                    'url': article.url,
                    'canonical_url': article.canonical_url or article.url,
                    'source_domain': self._extract_domain(article.url),
                    'url_hash': article.url_hash,
                    'text_hash': article.text_hash,
                    'title': article.title or "",
                    'title_norm': self._normalize_for_search(article.title or ""),
                    'description': article.description,
                    'clean_text': article.clean_text or "",
                    'full_text': article.content,
                    'authors': article.authors,
                    'authors_norm': [self._normalize_for_search(author) for author in article.authors],
                    'published_at': article.published_at,
                    'published_is_estimated': article.published_is_estimated,
                    'fetched_at': article.fetched_at,
                    'language': article.language_detected or 'en',
                    'language_confidence': article.language_confidence,
                    'category': article.category,
                    'category_confidence': article.category_confidence,
                    'tags_raw': article.tags,
                    'tags_norm': [self._normalize_for_search(tag) for tag in article.tags],
                    'keywords': article.keywords,
                    'entities': article.entities,
                    'word_count': article.word_count,
                    'char_count': article.char_count,
                    'readability_score': article.readability_score,
                    'quality_score': article.quality_score,
                    'quality_flags': article.quality_flags,
                    'is_duplicate': article.is_duplicate,
                    'dup_reason': article.dup_reason,
                    'dup_original_id': article.dup_original_id,
                    'dup_similarity_score': article.dup_similarity_score,
                    'ready_for_chunking': True,
                    'processing_version': context.processing_version,
                    'extraction_metadata': {
                        'processing_time_ms': sum(context.stage_timings.values()) * 1000,
                        'batch_id': context.batch_id,
                        'worker_id': context.worker_id,
                        'correlation_id': context.correlation_id
                    }
                }
                
                insert_data.append(index_entry)
                article.status = ProcessingStatus.PROCESSED
                article.processed_at = datetime.utcnow()
                
            except Exception as e:
                logger.error(f"Error preparing index for article {article.id}: {e}", exc_info=True)
                article.add_error("indexing", "processing_error", str(e))
        
        # Batch insert into database
        if insert_data:
            await self._batch_insert_articles(insert_data)
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(insert_data), 0, len(articles) - len(insert_data))
        
        logger.info(f"Stage 5 indexing: {len(insert_data)} articles indexed")
        
        return articles
    
    def _generate_article_id(self, article: ArticleData) -> str:
        """Generate stable article ID"""
        # Use URL hash + publish date for stable ID
        date_str = article.published_at.strftime('%Y%m%d') if article.published_at else 'unknown'
        id_source = f"{article.url_hash}_{date_str}"
        return hashlib.sha256(id_source.encode()).hexdigest()[:16]
    
    def _normalize_for_search(self, text: str) -> str:
        """Normalize text for search indexing"""
        if not text:
            return ""
        
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove punctuation and normalize spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized.strip()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    
    async def _batch_insert_articles(self, articles_data: List[Dict]):
        """Batch insert articles into index"""
        if not articles_data:
            return
        
        # Prepare SQL and values for batch insert
        columns = articles_data[0].keys()
        placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
        sql = f"""
        INSERT INTO articles_index ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (article_id) DO UPDATE SET
            updated_at = NOW(),
            processing_version = EXCLUDED.processing_version,
            extraction_metadata = EXCLUDED.extraction_metadata
        """
        
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                for article_data in articles_data:
                    values = [article_data[col] for col in columns]
                    await conn.execute(sql, *values)


class Stage6ChunkingProcessor(PipelineStage):
    """Stage 6: Split articles into searchable chunks with semantic awareness"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_6_CHUNKING
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Split articles into chunks for search and AI processing"""
        timer = await self._start_stage_timing(context)
        
        processed_articles = []
        error_count = 0
        total_chunks = 0
        
        # Get chunking configuration
        chunk_size = self.config.get('chunking.target_size', 500)  # words
        chunk_overlap = self.config.get('chunking.overlap', 50)   # words
        min_chunk_size = self.config.get('chunking.min_size', 100)
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_6_CHUNKING
                
                # Get article from index (it should be there from Stage 5)
                article_record = await self._get_article_record(article)
                if not article_record:
                    article.add_error("chunking", "missing_record", "Article not found in index")
                    error_count += 1
                    continue
                
                # Create chunks from clean text
                chunks = await self._create_chunks(
                    article_record['article_id'],
                    article_record['clean_text'],
                    article_record,
                    chunk_size,
                    chunk_overlap,
                    min_chunk_size
                )
                
                if chunks:
                    # Insert chunks into database
                    await self._insert_chunks(chunks)
                    total_chunks += len(chunks)
                    
                    # Mark article as chunked
                    await self._mark_article_chunked(article_record['article_id'])
                    
                processed_articles.append(article)
                
            except Exception as e:
                logger.error(f"Error chunking article {article.id}: {e}", exc_info=True)
                article.add_error("chunking", "processing_error", str(e))
                error_count += 1
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(processed_articles), 0, error_count)
        
        logger.info(f"Stage 6 chunking: {len(processed_articles)} articles, {total_chunks} chunks created, {error_count} errors")
        
        return processed_articles
    
    async def _get_article_record(self, article: ArticleData) -> Optional[Dict]:
        """Get article record from articles_index"""
        async with self.db_pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT article_id, clean_text, title, url, source_domain, 
                       published_at, language, category, tags_norm, authors_norm, quality_score
                FROM articles_index 
                WHERE raw_article_id = $1
            """, article.id)
    
    async def _create_chunks(self, 
                           article_id: str,
                           text: str, 
                           article_record: Dict,
                           chunk_size: int,
                           chunk_overlap: int,
                           min_chunk_size: int) -> List[Dict]:
        """Create semantic chunks from article text"""
        if not text or len(text.split()) < min_chunk_size:
            return []
        
        chunks = []
        words = text.split()
        
        # Strategy 1: Paragraph-based chunking (preferred)
        paragraphs = text.split('\n\n')
        if len(paragraphs) > 1:
            chunks.extend(await self._chunk_by_paragraphs(
                paragraphs, article_id, article_record, chunk_size, chunk_overlap, min_chunk_size
            ))
        else:
            # Strategy 2: Sliding window chunking
            chunks.extend(await self._chunk_by_sliding_window(
                words, article_id, article_record, chunk_size, chunk_overlap, min_chunk_size
            ))
        
        return chunks
    
    async def _chunk_by_paragraphs(self, 
                                 paragraphs: List[str],
                                 article_id: str,
                                 article_record: Dict,
                                 target_size: int,
                                 overlap: int,
                                 min_size: int) -> List[Dict]:
        """Create chunks respecting paragraph boundaries"""
        chunks = []
        current_chunk_paras = []
        current_chunk_words = 0
        char_position = 0
        
        for para in paragraphs:
            para_words = len(para.split())
            
            # If adding this paragraph exceeds target size, finalize current chunk
            if current_chunk_words + para_words > target_size and current_chunk_paras:
                chunk_text = '\n\n'.join(current_chunk_paras)
                chunk_start = char_position - len(chunk_text)
                
                if current_chunk_words >= min_size:
                    chunks.append(await self._create_chunk_record(
                        article_id, len(chunks), chunk_text, 
                        current_chunk_words, chunk_start, char_position,
                        article_record, "paragraph"
                    ))
                
                # Start new chunk with overlap
                if overlap > 0 and current_chunk_paras:
                    # Keep last few paragraphs for overlap
                    overlap_paras = current_chunk_paras[-(overlap // 50 + 1):]  # Rough overlap
                    current_chunk_paras = overlap_paras + [para]
                    current_chunk_words = sum(len(p.split()) for p in current_chunk_paras)
                else:
                    current_chunk_paras = [para]
                    current_chunk_words = para_words
            else:
                current_chunk_paras.append(para)
                current_chunk_words += para_words
            
            char_position += len(para) + 2  # +2 for \n\n
        
        # Handle final chunk
        if current_chunk_paras and current_chunk_words >= min_size:
            chunk_text = '\n\n'.join(current_chunk_paras)
            chunk_start = char_position - len(chunk_text)
            
            chunks.append(await self._create_chunk_record(
                article_id, len(chunks), chunk_text,
                current_chunk_words, chunk_start, char_position,
                article_record, "paragraph"
            ))
        
        return chunks
    
    async def _chunk_by_sliding_window(self,
                                     words: List[str],
                                     article_id: str,
                                     article_record: Dict,
                                     chunk_size: int,
                                     overlap: int,
                                     min_size: int) -> List[Dict]:
        """Create chunks using sliding window approach"""
        chunks = []
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            
            if len(chunk_words) < min_size and i > 0:
                break  # Don't create tiny final chunks
            
            chunk_text = ' '.join(chunk_words)
            
            # Calculate character positions (approximate)
            char_start = sum(len(w) + 1 for w in words[:i])  # +1 for space
            char_end = char_start + len(chunk_text)
            
            chunks.append(await self._create_chunk_record(
                article_id, len(chunks), chunk_text,
                len(chunk_words), char_start, char_end,
                article_record, "sliding_window"
            ))
        
        return chunks
    
    async def _create_chunk_record(self,
                                 article_id: str,
                                 chunk_index: int,
                                 text: str,
                                 word_count: int,
                                 char_start: int,
                                 char_end: int,
                                 article_record: Dict,
                                 strategy: str) -> Dict:
        """Create chunk record for database insertion"""
        
        # Determine semantic type based on position and content
        semantic_type = self._determine_semantic_type(text, chunk_index, word_count)
        
        # Calculate importance score
        importance_score = self._calculate_importance_score(
            text, chunk_index, semantic_type, article_record
        )
        
        # Clean text for search
        clean_text = self._clean_text_for_search(text)
        
        return {
            'article_id': article_id,
            'chunk_index': chunk_index,
            'text': text,
            'text_clean': clean_text,
            'word_count_chunk': word_count,
            'char_count_chunk': len(text),
            'char_start': char_start,
            'char_end': char_end,
            'semantic_type': semantic_type,
            'importance_score': importance_score,
            'chunk_strategy': strategy,
            'processing_version': "1.0",
            
            # Denormalized fields from article
            'url': article_record['url'],
            'title': article_record['title'] or '',
            'title_norm': self._normalize_for_search(article_record['title'] or ''),
            'source_domain': article_record['source_domain'],
            'published_at': article_record['published_at'],
            'language': article_record['language'],
            'category': article_record['category'],
            'tags_norm': article_record['tags_norm'] or [],
            'authors_norm': article_record['authors_norm'] or [],
            'quality_score': article_record['quality_score']
        }
    
    def _determine_semantic_type(self, text: str, chunk_index: int, word_count: int) -> str:
        """Determine semantic type of chunk"""
        text_lower = text.lower()
        
        # First chunk is likely introduction
        if chunk_index == 0:
            return "intro"
        
        # Look for conclusion markers
        conclusion_markers = ['conclusion', 'in conclusion', 'to summarize', 'finally', 'in summary']
        if any(marker in text_lower for marker in conclusion_markers):
            return "conclusion"
        
        # Look for list/enumeration patterns
        if text.count('\n-') > 2 or text.count('\n•') > 2 or text.count('\n1.') > 0:
            return "list"
        
        # Look for quote patterns
        if text.count('"') >= 2 or text.count(''') >= 2:
            return "quote"
        
        # Look for code patterns
        if '```' in text or text.count('`') > 4:
            return "code"
        
        # Default to body content
        return "body"
    
    def _calculate_importance_score(self, 
                                  text: str, 
                                  chunk_index: int, 
                                  semantic_type: str,
                                  article_record: Dict) -> float:
        """Calculate importance score for chunk (0.0-1.0)"""
        score = 0.5  # Base score
        
        # Position-based scoring
        if chunk_index == 0:
            score += 0.2  # First chunk is important
        elif semantic_type == "conclusion":
            score += 0.15
        
        # Content-based scoring
        if semantic_type == "intro":
            score += 0.1
        elif semantic_type == "quote":
            score += 0.05
        elif semantic_type == "list":
            score -= 0.05  # Lists are usually less important
        
        # Keyword density scoring (simplified)
        title_words = set((article_record.get('title') or '').lower().split())
        text_words = set(text.lower().split())
        
        if title_words and text_words:
            overlap = len(title_words.intersection(text_words))
            overlap_ratio = overlap / len(title_words)
            score += overlap_ratio * 0.2
        
        # Length-based adjustment
        word_count = len(text.split())
        if word_count < 50:
            score -= 0.1  # Very short chunks are less important
        elif word_count > 300:
            score += 0.05  # Longer chunks might be more detailed
        
        return max(0.0, min(1.0, score))
    
    def _clean_text_for_search(self, text: str) -> str:
        """Clean text for search indexing"""
        # Remove excessive whitespace
        clean_text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters that might interfere with FTS
        clean_text = re.sub(r'[^\w\s\-.,!?;:()\[\]{}"\'/]', ' ', clean_text)
        
        return clean_text.strip()
    
    def _normalize_for_search(self, text: str) -> str:
        """Normalize text for search (same as in Stage5)"""
        if not text:
            return ""
        
        normalized = text.lower()
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized.strip()
    
    async def _insert_chunks(self, chunks: List[Dict]):
        """Batch insert chunks into database"""
        if not chunks:
            return
        
        # Prepare bulk insert
        columns = list(chunks[0].keys())
        placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
        
        sql = f"""
        INSERT INTO article_chunks ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (article_id, chunk_index) DO UPDATE SET
            text = EXCLUDED.text,
            text_clean = EXCLUDED.text_clean,
            processing_version = EXCLUDED.processing_version,
            created_at = NOW()
        """
        
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                for chunk_data in chunks:
                    values = [chunk_data[col] for col in columns]
                    await conn.execute(sql, *values)
    
    async def _mark_article_chunked(self, article_id: str):
        """Mark article as chunked in articles_index"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE articles_index 
                SET chunking_completed = TRUE, updated_at = NOW()
                WHERE article_id = $1
            """, article_id)


class Stage7SearchIndexingProcessor(PipelineStage):
    """Stage 7: Create PostgreSQL full-text search indexes"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_7_SEARCH_INDEXING
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Update search indexes for processed articles"""
        timer = await self._start_stage_timing(context)
        
        processed_articles = []
        error_count = 0
        
        for article in articles:
            try:
                article.processing_stage = ProcessingStage.STAGE_7_SEARCH_INDEXING
                
                # Update article search vectors
                await self._update_article_search_vectors(article)
                
                # Update chunk search vectors (handled by trigger, but verify)
                await self._verify_chunk_search_vectors(article)
                
                # Update search statistics
                await self._update_search_statistics(article)
                
                # Mark as indexed
                await self._mark_article_indexed(article)
                
                processed_articles.append(article)
                
            except Exception as e:
                logger.error(f"Error indexing article {article.id}: {e}", exc_info=True)
                article.add_error("search_indexing", "processing_error", str(e))
                error_count += 1
        
        await self._end_stage_timing(context, timer)
        await self._record_stage_metrics(context, len(articles), len(processed_articles), 0, error_count)
        
        logger.info(f"Stage 7 search indexing: {len(processed_articles)} articles indexed, {error_count} errors")
        
        return processed_articles
    
    async def _update_article_search_vectors(self, article: ArticleData):
        """Update tsvector for article in articles_index"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE articles_index 
                SET 
                    search_vector = 
                        setweight(to_tsvector(coalesce(language, 'english')::regconfig, coalesce(title_norm, '')), 'A') ||
                        setweight(to_tsvector(coalesce(language, 'english')::regconfig, coalesce(clean_text, '')), 'B') ||
                        setweight(to_tsvector(coalesce(language, 'english')::regconfig, array_to_string(coalesce(tags_norm, '{}'), ' ')), 'C') ||
                        setweight(to_tsvector(coalesce(language, 'english')::regconfig, array_to_string(coalesce(keywords, '{}'), ' ')), 'D'),
                    updated_at = NOW()
                WHERE raw_article_id = $1
            """, article.id)
    
    async def _verify_chunk_search_vectors(self, article: ArticleData):
        """Verify chunk search vectors are properly generated"""
        async with self.db_pool.acquire() as conn:
            # The text_vector column should be auto-generated by the GENERATED ALWAYS AS clause
            # But we can verify it's working
            result = await conn.fetchval("""
                SELECT COUNT(*) 
                FROM article_chunks ac
                JOIN articles_index ai ON ac.article_id = ai.article_id
                WHERE ai.raw_article_id = $1 AND ac.text_vector IS NULL
            """, article.id)
            
            if result and result > 0:
                logger.warning(f"Found {result} chunks with missing search vectors for article {article.id}")
    
    async def _update_search_statistics(self, article: ArticleData):
        """Update search-related statistics"""
        async with self.db_pool.acquire() as conn:
            # Update language distribution stats
            await conn.execute("""
                INSERT INTO performance_metrics (
                    metric_name, metric_type, metric_value, tags, recorded_at
                ) VALUES (
                    'search.articles_indexed', 'counter', 1,
                    $1, NOW()
                )
            """, json.dumps({
                "language": article.language_detected or "unknown",
                "category": getattr(article, 'category', 'general')
            }))
    
    async def _mark_article_indexed(self, article: ArticleData):
        """Mark article as search indexed"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE articles_index 
                SET indexing_completed = TRUE, updated_at = NOW()
                WHERE raw_article_id = $1
            """, article.id)


class Stage8DiagnosticsProcessor(PipelineStage):
    """Stage 8: Generate comprehensive batch diagnostics and metrics"""
    
    def get_stage_enum(self) -> ProcessingStage:
        return ProcessingStage.STAGE_8_DIAGNOSTICS
    
    async def process_batch(self, 
                          articles: List[ArticleData],
                          context: ProcessingContext) -> List[ArticleData]:
        """Generate final diagnostics for the batch"""
        timer = await self._start_stage_timing(context)
        
        try:
            # Collect stage-by-stage diagnostics
            diagnostics = await self._collect_batch_diagnostics(articles, context)
            
            # Store diagnostics in database
            await self._store_batch_diagnostics(context.batch_id, diagnostics, context)
            
            # Update batch completion status
            await self._update_batch_completion(context.batch_id, articles, context)
            
            # Record final metrics
            await self._record_final_metrics(articles, diagnostics, context)
            
            # Generate alerts if needed
            await self._check_and_generate_alerts(diagnostics, context)
            
            await self._end_stage_timing(context, timer)
            await self._record_stage_metrics(context, len(articles), len(articles), 0, 0)
            
            logger.info(f"Stage 8 diagnostics: Completed diagnostics for batch {context.batch_id}")
            
            return articles
            
        except Exception as e:
            logger.error(f"Error in diagnostics stage: {e}", exc_info=True)
            raise
    
    async def _collect_batch_diagnostics(self, 
                                       articles: List[ArticleData],
                                       context: ProcessingContext) -> Dict[str, Any]:
        """Collect comprehensive batch diagnostics"""
        
        # Article status distribution
        status_counts = defaultdict(int)
        quality_scores = []
        processing_times = []
        error_types = defaultdict(int)
        rejection_reasons = defaultdict(int)
        
        for article in articles:
            status_counts[article.status.value] += 1
            
            if article.quality_score > 0:
                quality_scores.append(article.quality_score)
            
            # Collect error types
            for error in article.error_log:
                error_types[error.get('error_type', 'unknown')] += 1
            
            # Collect rejection reasons
            if article.dup_reason:
                rejection_reasons[article.dup_reason] += 1
        
        # Stage performance analysis
        stage_performance = {}
        for stage_name, duration in context.stage_timings.items():
            stage_metrics = context.stage_metrics.get(stage_name, {})
            stage_performance[stage_name] = {
                'duration_seconds': duration,
                'success_rate': stage_metrics.get('success_rate', 0),
                'error_rate': stage_metrics.get('error_rate', 0),
                'articles_processed': stage_metrics.get('articles_output', 0)
            }
        
        # Language and category distribution
        language_dist = defaultdict(int)
        category_dist = defaultdict(int)
        domain_dist = defaultdict(int)
        
        for article in articles:
            if article.language_detected:
                language_dist[article.language_detected] += 1
            if hasattr(article, 'category') and article.category:
                category_dist[article.category] += 1
            
            # Extract domain from URL
            try:
                from urllib.parse import urlparse
                domain = urlparse(article.url).netloc
                domain_dist[domain] += 1
            except:
                pass
        
        # Calculate percentiles for quality scores
        quality_stats = {}
        if quality_scores:
            quality_scores.sort()
            n = len(quality_scores)
            quality_stats = {
                'mean': sum(quality_scores) / n,
                'min': quality_scores[0],
                'max': quality_scores[-1],
                'p25': quality_scores[int(n * 0.25)],
                'p50': quality_scores[int(n * 0.50)],
                'p75': quality_scores[int(n * 0.75)],
                'p95': quality_scores[int(n * 0.95)] if n > 20 else quality_scores[-1]
            }
        
        # Resource usage (basic)
        total_processing_time = sum(context.stage_timings.values())
        
        return {
            'batch_id': context.batch_id,
            'worker_id': context.worker_id,
            'correlation_id': context.correlation_id,
            'processing_version': context.processing_version,
            
            # Article metrics
            'articles_total': len(articles),
            'status_distribution': dict(status_counts),
            'language_distribution': dict(language_dist),
            'category_distribution': dict(category_dist),
            'domain_distribution': dict(domain_dist),
            
            # Quality metrics
            'quality_stats': quality_stats,
            'avg_quality_score': quality_stats.get('mean', 0),
            
            # Performance metrics
            'total_processing_time_seconds': total_processing_time,
            'articles_per_second': len(articles) / max(total_processing_time, 1),
            'stage_performance': stage_performance,
            
            # Error analysis
            'error_types': dict(error_types),
            'rejection_reasons': dict(rejection_reasons),
            'error_rate': sum(error_types.values()) / max(len(articles), 1),
            'rejection_rate': sum(rejection_reasons.values()) / max(len(articles), 1),
            
            # Success metrics
            'success_rate': status_counts.get('processed', 0) / max(len(articles), 1),
            'duplicate_rate': status_counts.get('duplicate', 0) / max(len(articles), 1),
            
            # Timestamps
            'started_at': context.started_at.isoformat(),
            'completed_at': datetime.utcnow().isoformat()
        }
    
    async def _store_batch_diagnostics(self, 
                                     batch_id: str,
                                     diagnostics: Dict[str, Any],
                                     context: ProcessingContext):
        """Store diagnostics in batch_diagnostics table"""
        
        # Create diagnostic record for each stage
        stage_name_to_enum = {
            'Stage0ValidationProcessor': ProcessingStage.STAGE_0_VALIDATION,
            'Stage1FeedHealthProcessor': ProcessingStage.STAGE_1_FEED_HEALTH,
            'Stage2DeduplicationProcessor': ProcessingStage.STAGE_2_DEDUPLICATION,
            'Stage3NormalizationProcessor': ProcessingStage.STAGE_3_NORMALIZATION,
            'Stage4TextCleaningProcessor': ProcessingStage.STAGE_4_TEXT_CLEANING,
            'Stage5IndexingProcessor': ProcessingStage.STAGE_5_INDEXING,
            'Stage6ChunkingProcessor': ProcessingStage.STAGE_6_CHUNKING,
            'Stage7SearchIndexingProcessor': ProcessingStage.STAGE_7_SEARCH_INDEXING,
            'Stage8DiagnosticsProcessor': ProcessingStage.STAGE_8_DIAGNOSTICS
        }
        
        for stage_name, stage_perf in diagnostics['stage_performance'].items():
            stage_enum = stage_name_to_enum.get(stage_name, ProcessingStage.STAGE_0_VALIDATION)
            stage_order = list(ProcessingStage).index(stage_enum)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO batch_diagnostics (
                        batch_id, stage, stage_order, worker_id, worker_node,
                        articles_input, articles_output, articles_errors,
                        avg_processing_time_ms, duration_ms, status,
                        correlation_id, started_at, completed_at, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
                    ON CONFLICT (batch_id, stage) DO UPDATE SET
                        duration_ms = EXCLUDED.duration_ms,
                        articles_output = EXCLUDED.articles_output,
                        status = EXCLUDED.status,
                        completed_at = EXCLUDED.completed_at
                """,
                batch_id,
                stage_name,
                stage_order,
                context.worker_id,
                'localhost',  # worker_node - could be made configurable
                diagnostics['articles_total'],
                stage_perf.get('articles_processed', 0),
                int(diagnostics['articles_total'] * stage_perf.get('error_rate', 0)),
                stage_perf.get('duration_seconds', 0) * 1000,  # Convert to ms
                stage_perf.get('duration_seconds', 0) * 1000,  # duration_ms
                'completed',
                context.correlation_id,
                context.started_at,
                datetime.utcnow())
    
    async def _update_batch_completion(self, 
                                     batch_id: str,
                                     articles: List[ArticleData],
                                     context: ProcessingContext):
        """Update batch record with final completion status"""
        
        successful = len([a for a in articles if a.status == ProcessingStatus.PROCESSED])
        failed = len([a for a in articles if a.status == ProcessingStatus.FAILED])
        duplicates = len([a for a in articles if a.status == ProcessingStatus.DUPLICATE])
        rejected = len([a for a in articles if a.status == ProcessingStatus.REJECTED])
        
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE batches SET
                    status = 'completed',
                    articles_successful = $1,
                    articles_failed = $2,
                    articles_skipped = $3,
                    processing_time_ms = $4,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE batch_id = $5
            """,
            successful,
            failed,
            duplicates + rejected,  # skipped = duplicates + rejected
            sum(context.stage_timings.values()) * 1000,  # Convert to ms
            batch_id)
    
    async def _record_final_metrics(self, 
                                  articles: List[ArticleData],
                                  diagnostics: Dict[str, Any],
                                  context: ProcessingContext):
        """Record final batch metrics"""
        
        # Record to performance_metrics table
        metrics_to_record = [
            ('batch.completed', 'counter', 1, {'worker_id': context.worker_id}),
            ('batch.articles_processed', 'histogram', len(articles), {}),
            ('batch.success_rate', 'histogram', diagnostics['success_rate'], {}),
            ('batch.duplicate_rate', 'histogram', diagnostics['duplicate_rate'], {}),
            ('batch.error_rate', 'histogram', diagnostics['error_rate'], {}),
            ('batch.processing_time', 'histogram', diagnostics['total_processing_time_seconds'], {}),
            ('batch.throughput_articles_per_second', 'histogram', diagnostics['articles_per_second'], {})
        ]
        
        async with self.db_pool.acquire() as conn:
            for metric_name, metric_type, value, tags in metrics_to_record:
                await conn.execute("""
                    INSERT INTO performance_metrics (
                        metric_name, metric_type, metric_value, tags,
                        correlation_id, recorded_at
                    ) VALUES ($1, $2, $3, $4, $5, NOW())
                """, metric_name, metric_type, value, json.dumps(tags), context.correlation_id)
    
    async def _check_and_generate_alerts(self, 
                                       diagnostics: Dict[str, Any],
                                       context: ProcessingContext):
        """Check metrics against thresholds and generate alerts if needed"""
        
        alerts_to_generate = []
        
        # Check error rate
        if diagnostics['error_rate'] > 0.1:  # 10% error rate
            alerts_to_generate.append({
                'severity': 'warning',
                'message': f"High error rate in batch {context.batch_id}: {diagnostics['error_rate']:.2%}",
                'metric_name': 'batch.error_rate',
                'metric_value': diagnostics['error_rate']
            })
        
        # Check processing time
        if diagnostics['total_processing_time_seconds'] > 300:  # 5 minutes
            alerts_to_generate.append({
                'severity': 'warning',
                'message': f"Slow batch processing in {context.batch_id}: {diagnostics['total_processing_time_seconds']:.1f}s",
                'metric_name': 'batch.processing_time',
                'metric_value': diagnostics['total_processing_time_seconds']
            })
        
        # Check success rate
        if diagnostics['success_rate'] < 0.8:  # Less than 80% success
            alerts_to_generate.append({
                'severity': 'critical',
                'message': f"Low success rate in batch {context.batch_id}: {diagnostics['success_rate']:.2%}",
                'metric_name': 'batch.success_rate',
                'metric_value': diagnostics['success_rate']
            })
        
        # Store alerts (would integrate with AlertManager in production)
        if alerts_to_generate:
            async with self.db_pool.acquire() as conn:
                for alert in alerts_to_generate:
                    await conn.execute("""
                        INSERT INTO performance_metrics (
                            metric_name, metric_type, metric_value, tags, recorded_at
                        ) VALUES ('alert.generated', 'counter', 1, $1, NOW())
                    """, json.dumps({
                        'batch_id': context.batch_id,
                        'severity': alert['severity'],
                        'alert_type': alert['metric_name']
                    }))
            
            logger.warning(f"Generated {len(alerts_to_generate)} alerts for batch {context.batch_id}")


# Update the main PipelineProcessor to include all stages

class PipelineProcessor:
    """Main pipeline processor coordinating all stages"""
    
    def __init__(self,
                 db_pool: asyncpg.Pool,
                 redis_client: redis.Redis,
                 metrics: MetricsCollector,
                 config: Config):
        self.db_pool = db_pool
        self.redis = redis_client
        self.metrics = metrics
        self.config = config
        
        # Initialize all stages
        self.stages = [
            Stage0ValidationProcessor(db_pool, redis_client, metrics, config),
            Stage1FeedHealthProcessor(db_pool, redis_client, metrics, config),
            Stage2DeduplicationProcessor(db_pool, redis_client, metrics, config),
            Stage3NormalizationProcessor(db_pool, redis_client, metrics, config),
            Stage4TextCleaningProcessor(db_pool, redis_client, metrics, config),
            Stage5IndexingProcessor(db_pool, redis_client, metrics, config),
            Stage6ChunkingProcessor(db_pool, redis_client, metrics, config),
            Stage7SearchIndexingProcessor(db_pool, redis_client, metrics, config),
            Stage8DiagnosticsProcessor(db_pool, redis_client, metrics, config)
        ]
    
    async def process_batch(self, batch_id: str, worker_id: str) -> Dict[str, Any]:
        """Process a complete batch through all pipeline stages"""
        start_time = time.time()
        
        # Create processing context
        context = ProcessingContext(
            batch_id=batch_id,
            worker_id=worker_id,
            correlation_id=f"corr_{uuid4().hex[:16]}",
            trace_id=f"trace_{uuid4().hex[:16]}",
            processing_version="1.0"
        )
        
        try:
            # Load articles for batch
            articles = await self._load_batch_articles(batch_id)
            
            if not articles:
                logger.warning(f"No articles found for batch {batch_id}")
                return {"success": False, "error": "No articles found"}
            
            logger.info(f"Processing batch {batch_id} with {len(articles)} articles")
            
            # Process through all stages
            current_articles = articles
            
            for stage in self.stages:
                try:
                    current_articles = await stage.process_batch(current_articles, context)
                    
                    # Update batch progress
                    await self._update_batch_progress(batch_id, stage.get_stage_enum(), len(current_articles))
                    
                    if not current_articles:
                        logger.info(f"No articles remaining after {stage.stage_name}")
                        break
                        
                except Exception as e:
                    logger.error(f"Stage {stage.stage_name} failed: {e}", exc_info=True)
                    await self.metrics.increment(f"pipeline.stage.{stage.stage_name.lower()}.error")
                    raise
            
            # Update final batch status
            processing_time = time.time() - start_time
            success_count = len([a for a in articles if a.status == ProcessingStatus.PROCESSED])
            
            await self._complete_batch(batch_id, success_count, len(articles), processing_time, context)
            
            # Record final metrics
            await self.metrics.histogram("pipeline.batch.duration", processing_time)
            await self.metrics.histogram("pipeline.batch.success_rate", success_count / len(articles))
            
            logger.info(f"Batch {batch_id} completed: {success_count}/{len(articles)} successful in {processing_time:.2f}s")
            
            return {
                "success": True,
                "articles_processed": len(articles),
                "articles_successful": success_count,
                "processing_time": processing_time,
                "context": context
            }
            
        except Exception as e:
            logger.error(f"Pipeline failed for batch {batch_id}: {e}", exc_info=True)
            await self._fail_batch(batch_id, str(e))
            await self.metrics.increment("pipeline.batch.failed")
            raise
    
    async def _load_batch_articles(self, batch_id: str) -> List[ArticleData]:
        """Load articles for batch processing"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, feed_id, url, url_hash, text_hash, title, description, content,
                       authors, published_at_raw, published_at, language_raw, 
                       fetched_at, retry_count, idempotency_key
                FROM raw_articles 
                WHERE batch_id = $1 AND status = 'processing'
                ORDER BY id
            """, batch_id)
            
            articles = []
            for row in rows:
                article = ArticleData(
                    id=row['id'],
                    feed_id=row['feed_id'],
                    url=row['url'],
                    url_hash=row['url_hash'] or "",
                    text_hash=row['text_hash'],
                    title=row['title'],
                    description=row['description'],
                    content=row['content'],
                    authors=list(row['authors']) if row['authors'] else [],
                    published_at_raw=row['published_at_raw'],
                    published_at=row['published_at'],
                    language_raw=row['language_raw'],
                    fetched_at=row['fetched_at'],
                    retry_count=row['retry_count'],
                    idempotency_key=row['idempotency_key']
                )
                articles.append(article)
            
            return articles
    
    async def _update_batch_progress(self, batch_id: str, stage: ProcessingStage, articles_remaining: int):
        """Update batch processing progress"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE batches 
                SET current_stage = $1, updated_at = NOW()
                WHERE batch_id = $2
            """, stage.value, batch_id)
    
    async def _complete_batch(self, 
                            batch_id: str, 
                            success_count: int, 
                            total_count: int,
                            processing_time: float,
                            context: ProcessingContext):
        """Mark batch as completed"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE batches 
                SET 
                    status = 'completed',
                    articles_successful = $1,
                    articles_processed = $2,
                    processing_time_ms = $3,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE batch_id = $4
            """, success_count, total_count, int(processing_time * 1000), batch_id)
    
    async def _fail_batch(self, batch_id: str, error_message: str):
        """Mark batch as failed"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE batches 
                SET 
                    status = 'failed',
                    completed_at = NOW(),
                    updated_at = NOW(),
                    last_error = $1
                WHERE batch_id = $2
            """, json.dumps({"error": error_message, "timestamp": datetime.utcnow().isoformat()}), batch_id)


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_pipeline():
        # This would work with real database connections
        print("Pipeline processor initialized successfully")
        
        # Mock test data
        test_article = ArticleData(
            id=1,
            feed_id=1,
            url="https://example.com/test-article",
            title="Test Article",
            content="<p>This is a test article content with some <b>bold</b> text.</p>",
            fetched_at=datetime.utcnow()
        )
        
        print(f"Test article: {test_article.title}")
        print(f"Content length: {len(test_article.content or '')}")
        
    # asyncio.run(test_pipeline())