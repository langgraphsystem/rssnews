"""
Main content extraction orchestrator
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from .metadata import extract_metadata
from .content import extract_article_content
from utils.text import (
    compute_text_hash, compute_word_count, estimate_reading_time,
    extract_keywords, clean_text_content, is_sufficient_content,
    detect_paywall_indicators
)
from utils.url import canonicalize_url, extract_domain, compute_url_hash

logger = logging.getLogger(__name__)

@dataclass
class ParsedArticle:
    """Parsed article data structure"""
    # URLs
    url: str = ''
    canonical_url: str = ''
    url_hash: str = ''
    source: str = ''  # domain
    
    # Content
    title: str = ''
    description: str = ''
    full_text: str = ''
    text_hash: str = ''
    word_count: int = 0
    reading_time: int = 0
    
    # Metadata
    authors: List[str] = field(default_factory=list)
    publisher: str = ''
    section: str = ''
    keywords: List[str] = field(default_factory=list)
    
    # Media
    top_image: str = ''
    images: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[Dict[str, Any]] = field(default_factory=list)
    enclosures: List[Dict[str, Any]] = field(default_factory=list)
    outlinks: List[str] = field(default_factory=list)
    
    # Dates
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    
    # Quality indicators
    language: str = ''
    paywalled: bool = False
    partial: bool = False
    
    # Status
    status: str = 'pending'  # pending|processing|stored|duplicate|error|partial
    error_reason: str = ''

def extract_all(html: str, url: str, final_url: str = None, 
                headers: Dict[str, str] = None, rss_data: Dict[str, Any] = None) -> ParsedArticle:
    """
    Extract all data from HTML and create ParsedArticle
    
    Args:
        html: Raw HTML content
        url: Original URL
        final_url: Final URL after redirects
        headers: HTTP response headers
        rss_data: Data from RSS feed (title, description, etc.)
    """
    article = ParsedArticle()
    
    # Set URLs
    article.url = url
    final_url = final_url or url
    
    try:
        # Extract metadata (JSON-LD, OG, etc.)
        metadata = extract_metadata(html, final_url) or {}
        
        # Extract content (text, media, links)
        content = extract_article_content(html, final_url) or {}
        
        # Determine canonical URL
        canonical = metadata.get('canonical_url') or final_url
        article.canonical_url = canonicalize_url(canonical)
        
        # Generate URL hash
        article.url_hash = compute_url_hash(article.canonical_url)
        
        # Extract domain
        article.source = extract_domain(article.canonical_url)
        
        # Basic metadata with fallbacks from RSS
        article.title = _get_best_value([
            metadata.get('title'),
            rss_data.get('title') if rss_data else None
        ])
        
        article.description = _get_best_value([
            metadata.get('description'), 
            rss_data.get('summary') if rss_data else None
        ])
        
        # Authors
        if metadata.get('authors'):
            article.authors = metadata['authors']
        elif rss_data and rss_data.get('authors'):
            article.authors = [rss_data['authors']]
        
        # Publisher
        article.publisher = metadata.get('publisher', '')
        
        # Section
        article.section = _get_best_value([
            metadata.get('section'),
            rss_data.get('category') if rss_data else None
        ])
        
        # Keywords
        if metadata.get('keywords'):
            article.keywords = metadata['keywords']
        elif rss_data and rss_data.get('tags'):
            article.keywords = rss_data['tags']
        
        # Content
        article.full_text = clean_text_content(content.get('full_text', ''))
        article.text_hash = compute_text_hash(article.full_text)
        article.word_count = compute_word_count(article.full_text)
        article.reading_time = estimate_reading_time(article.full_text)
        
        # Media
        article.top_image = _get_best_value([
            content.get('top_image'),
            metadata.get('top_image'),
            (rss_data.get('enclosures') or [{}])[0].get('href') if rss_data and rss_data.get('enclosures') else None
        ])
        
        article.images = content.get('images', [])
        article.videos = content.get('videos', [])
        article.outlinks = content.get('outlinks', [])
        
        # RSS enclosures
        if rss_data and rss_data.get('enclosures'):
            article.enclosures = rss_data['enclosures']
        
        # Dates
        article.published_at = _get_best_date([
            metadata.get('published_at'),
            rss_data.get('published') if rss_data else None
        ])
        
        article.updated_at = metadata.get('updated_at')
        
        # Language
        article.language = metadata.get('language', '')
        
        # Quality checks
        paywall_check = detect_paywall_indicators(article.full_text, html)
        article.paywalled = paywall_check['paywalled']
        article.partial = paywall_check['partial']
        
        # Determine status
        if not article.title:
            article.status = 'error'
            article.error_reason = 'No title found'
        elif not is_sufficient_content(article.full_text):
            if article.paywalled:
                article.status = 'partial'
                article.error_reason = 'Paywalled content'
            else:
                article.status = 'partial'
                article.error_reason = 'Insufficient content length'
        else:
            article.status = 'stored'
        
        # If we don't have extracted keywords, try to generate some
        if not article.keywords and article.full_text:
            article.keywords = extract_keywords(article.full_text)
        
        logger.info(f"Extracted article: {article.title[:50]}... "
                   f"({article.word_count} words, status: {article.status})")
        
    except Exception as e:
        import traceback
        logger.error(f"Failed to extract article from {url}: {e}")
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        article.status = 'error'
        article.error_reason = f'Extraction failed: {str(e)}'
    
    return article

def _get_best_value(candidates: List[Any]) -> str:
    """Get the best non-empty value from candidates"""
    for candidate in candidates:
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return ''

def _get_best_date(candidates: List[Any]) -> Optional[datetime]:
    """Get the best datetime from candidates"""
    for candidate in candidates:
        if candidate and isinstance(candidate, datetime):
            return candidate
    return None
