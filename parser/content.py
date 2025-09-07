"""
Article content extraction from HTML using DOM parsing and heuristics
"""

import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, Tag, NavigableString
from urllib.parse import urljoin
import logging

logger = logging.getLogger(__name__)

def extract_article_content(html: str, base_url: str = '') -> Dict[str, Any]:
    """
    Extract article content including text, images, videos, and outlinks
    """
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}")
            return {}
    
    # Find main content container
    content_container = _find_article_container(soup)
    if not content_container:
        content_container = soup
    
    # Extract text content
    full_text = _extract_text_content(content_container)
    
    # Extract media
    images = _extract_images(content_container, base_url)
    videos = _extract_videos(content_container, base_url)
    
    # Extract outlinks
    outlinks = _extract_outlinks(content_container, base_url)
    
    # Find top image (first significant image or from figure)
    top_image = _find_top_image(soup, base_url) or (images[0].get('src') if images else '')
    
    return {
        'full_text': full_text.strip(),
        'top_image': top_image,
        'images': images,
        'videos': videos,
        'outlinks': outlinks
    }

def _find_article_container(soup: BeautifulSoup) -> Optional[Tag]:
    """
    Find the main article container using semantic HTML and common patterns
    """
    # Try semantic HTML first
    for tag_name in ['article', 'main']:
        container = soup.find(tag_name)
        if container:
            return container
    
    # Try common class/id patterns
    content_selectors = [
        # Common article containers
        '[role="main"]',
        '.article-content',
        '.entry-content', 
        '.post-content',
        '.content-body',
        '.article-body',
        '.story-body',
        '.article-text',
        '#article-content',
        '#content',
        '.content',
        
        # News-specific
        '.article-wrap',
        '.story-wrap',
        '.news-content',
        
        # Generic content areas
        '.main-content',
        '.primary-content',
        '.page-content'
    ]
    
    for selector in content_selectors:
        try:
            container = soup.select_one(selector)
            if container and _is_significant_content(container):
                return container
        except Exception:
            continue
    
    # Fallback: find div with most text content
    divs = soup.find_all('div')
    if divs:
        best_div = max(divs, key=lambda d: len(d.get_text()) if d else 0)
        if _is_significant_content(best_div):
            return best_div
    
    return None

def _is_significant_content(container: Tag) -> bool:
    """Check if container has significant content"""
    if not container:
        return False
    
    text = container.get_text().strip()
    return len(text) > 100  # At least 100 characters

def _extract_text_content(container: Tag) -> str:
    """
    Extract clean text content from container, preserving structure
    """
    if not container:
        return ''
    
    # Remove unwanted elements
    unwanted_selectors = [
        # Navigation and UI
        'nav', 'header', 'footer', 'aside',
        '.navigation', '.menu', '.sidebar',
        
        # Social sharing
        '.social-share', '.share-buttons', '.share-tools',
        '.social-links', '.sharing',
        
        # Advertising and promotion  
        '.advertisement', '.ad-container', '.ads',
        '.promo', '.promotion', '.newsletter',
        '.subscribe', '.subscription',
        
        # Comments and related
        '.comments', '.comment-section',
        '.related-articles', '.more-stories',
        '.recommended', '.also-read',
        
        # Media controls and captions (handled separately)
        '.video-player', '.audio-player',
        
        # Common junk
        '.tags', '.categories', '.meta',
        '.breadcrumbs', '.pagination'
    ]
    
    # Clone to avoid modifying original
    content_copy = BeautifulSoup(str(container), 'html.parser')
    
    for selector in unwanted_selectors:
        try:
            for element in content_copy.select(selector):
                element.decompose()
        except Exception:
            continue
    
    # Extract text while preserving some structure
    return _extract_structured_text(content_copy)

def _extract_structured_text(container: Tag) -> str:
    """Extract text preserving paragraph and heading structure"""
    if not container:
        return ''
    
    text_parts = []
    
    for element in container.descendants:
        if isinstance(element, NavigableString):
            text = str(element).strip()
            if text and text not in text_parts:
                text_parts.append(text)
        elif isinstance(element, Tag):
            # Add line breaks for block elements
            if element.name in ['p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']:
                if text_parts and not text_parts[-1].endswith('\n'):
                    text_parts.append('\n')
            # Add extra spacing for headers
            elif element.name in ['h1', 'h2', 'h3']:
                if text_parts and not text_parts[-1].endswith('\n\n'):
                    text_parts.append('\n\n')
    
    # Join and clean up
    full_text = ''.join(text_parts)
    
    # Clean up whitespace
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)  # Max 2 consecutive newlines
    full_text = re.sub(r' {2,}', ' ', full_text)       # Multiple spaces to single
    full_text = re.sub(r'\t+', ' ', full_text)         # Tabs to space
    
    return full_text.strip()

def _extract_images(container: Tag, base_url: str = '') -> List[Dict[str, Any]]:
    """Extract images from content with metadata"""
    if not container:
        return []
    
    images = []
    img_tags = container.find_all('img')
    
    for img in img_tags:
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if not src:
            continue
        
        # Resolve relative URLs
        if base_url:
            src = urljoin(base_url, src)
        
        # Skip tiny images (likely icons/decorative)
        width = _parse_dimension(img.get('width'))
        height = _parse_dimension(img.get('height'))
        
        if width and height and (width < 50 or height < 50):
            continue
        
        # Extract metadata
        alt_text = img.get('alt', '').strip()
        
        # Look for caption in surrounding elements
        caption = _find_image_caption(img)
        
        image_data = {
            'src': src,
            'alt': alt_text,
            'caption': caption,
            'width': width,
            'height': height
        }
        
        images.append(image_data)
    
    return images

def _find_image_caption(img_tag: Tag) -> str:
    """Find caption text for an image"""
    caption = ''
    
    # Check if image is in a figure with figcaption
    figure = img_tag.find_parent('figure')
    if figure:
        figcaption = figure.find('figcaption')
        if figcaption:
            caption = figcaption.get_text().strip()
    
    # Check for caption in nearby elements
    if not caption:
        # Look in next sibling
        next_sibling = img_tag.find_next_sibling()
        if next_sibling and next_sibling.name in ['p', 'div', 'span']:
            text = next_sibling.get_text().strip()
            # Heuristic: if it's short and mentions the image, it might be a caption
            if len(text) < 200 and any(word in text.lower() for word in ['photo', 'image', 'caption', 'credit']):
                caption = text
    
    return caption

def _extract_videos(container: Tag, base_url: str = '') -> List[Dict[str, Any]]:
    """Extract video elements and embedded videos"""
    if not container:
        return []
    
    videos = []
    
    # HTML5 video tags
    video_tags = container.find_all('video')
    for video in video_tags:
        src = video.get('src')
        if not src:
            # Check for source tags
            source = video.find('source')
            if source:
                src = source.get('src')
        
        if src and base_url:
            src = urljoin(base_url, src)
        
        if src:
            videos.append({
                'src': src,
                'kind': 'video'
            })
    
    # Embedded videos (iframes)
    iframe_tags = container.find_all('iframe')
    for iframe in iframe_tags:
        src = iframe.get('src')
        if not src:
            continue
        
        # Check if it's a video embed
        video_domains = ['youtube.com', 'vimeo.com', 'dailymotion.com', 'twitch.tv']
        if any(domain in src.lower() for domain in video_domains):
            videos.append({
                'src': src,
                'kind': 'embed'
            })
    
    return videos

def _extract_outlinks(container: Tag, base_url: str = '') -> List[str]:
    """Extract external links from content"""
    if not container:
        return []
    
    outlinks = []
    link_tags = container.find_all('a', href=True)
    
    for link in link_tags:
        href = link.get('href')
        if not href:
            continue
        
        # Resolve relative URLs
        if base_url:
            href = urljoin(base_url, href)
        
        # Skip internal links (anchors, javascript, etc.)
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        
        # Skip if it's the same domain as base_url (internal link)
        if base_url:
            from urllib.parse import urlparse
            try:
                base_domain = urlparse(base_url).netloc
                link_domain = urlparse(href).netloc
                if base_domain == link_domain:
                    continue
            except Exception:
                pass
        
        outlinks.append(href)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_outlinks = []
    for link in outlinks:
        if link not in seen:
            seen.add(link)
            unique_outlinks.append(link)
    
    return unique_outlinks

def _find_top_image(soup: BeautifulSoup, base_url: str = '') -> str:
    """Find the top/hero image for the article"""
    # Look in specific areas first
    top_image_selectors = [
        'figure img',
        '.hero-image img',
        '.featured-image img', 
        '.article-image img',
        '.story-image img',
        'header img',
        '.media img'
    ]
    
    for selector in top_image_selectors:
        try:
            img = soup.select_one(selector)
            if img:
                src = img.get('src') or img.get('data-src')
                if src:
                    # Check if it's a reasonable size (not an icon)
                    width = _parse_dimension(img.get('width'))
                    height = _parse_dimension(img.get('height'))
                    
                    if not width or not height or (width >= 200 and height >= 150):
                        if base_url:
                            src = urljoin(base_url, src)
                        return src
        except Exception:
            continue
    
    # Fallback: first large image in the document
    all_images = soup.find_all('img')
    for img in all_images:
        src = img.get('src') or img.get('data-src')
        if not src:
            continue
        
        # Skip small images
        width = _parse_dimension(img.get('width'))
        height = _parse_dimension(img.get('height'))
        
        if width and height and (width < 200 or height < 150):
            continue
        
        if base_url:
            src = urljoin(base_url, src)
        return src
    
    return ''

def _parse_dimension(dim_str: str) -> Optional[int]:
    """Parse dimension string to integer"""
    if not dim_str:
        return None
    
    try:
        # Remove 'px' and other units
        dim_str = re.sub(r'[^\d]', '', str(dim_str))
        return int(dim_str) if dim_str else None
    except (ValueError, TypeError):
        return None