"""
Content Deduplication Engine
Implements MinHash, content fingerprinting, and canonicalization
"""

import hashlib
import re
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from datasketch import MinHashLSH, MinHash

logger = logging.getLogger(__name__)


@dataclass
class DuplicationConfig:
    """Configuration for deduplication engine"""
    similarity_threshold: float = 0.8  # Jaccard similarity threshold
    title_similarity_threshold: float = 0.7
    content_hash_similarity: float = 0.9
    num_perm: int = 128  # MinHash permutations
    lsh_threshold: float = 0.8  # LSH threshold


class DeduplicationEngine:
    """Production-ready content deduplication with canonicalization"""

    def __init__(self, config: Optional[DuplicationConfig] = None):
        self.config = config or DuplicationConfig()
        self.lsh = MinHashLSH(threshold=self.config.lsh_threshold,
                             num_perm=self.config.num_perm)
        self.content_cache = {}  # article_id -> MinHash
        self.canonical_map = {}  # duplicate_id -> canonical_id

        # Domain priority for canonicalization
        self.domain_priority = {
            'reuters.com': 10,
            'ap.org': 10,
            'bbc.com': 9,
            'nytimes.com': 8,
            'theguardian.com': 8,
            'washingtonpost.com': 8,
            'bloomberg.com': 8,
            'wsj.com': 8,
            'cnn.com': 7,
            'economist.com': 9,
            'npr.org': 8,
            'abcnews.go.com': 7,
            'cbsnews.com': 7,
            'nbcnews.com': 7,
        }

    def clean_text_for_hashing(self, text: str) -> str:
        """Clean and normalize text for consistent hashing"""
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        # Remove email addresses
        text = re.sub(r'\S+@\S+', '', text)

        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Remove common patterns that vary between sources
        patterns_to_remove = [
            r'\(.*?reuters.*?\)',
            r'\(.*?ap.*?\)',
            r'\(.*?breaking.*?\)',
            r'\(.*?updating.*?\)',
            r'this story is developing.*',
            r'this is a breaking news.*',
            r'more details to follow.*',
        ]

        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    def create_content_hash(self, article: Dict[str, Any]) -> str:
        """Create stable content hash for article"""
        # Combine title and content for hashing
        title = article.get('title_norm', article.get('title', ''))
        content = article.get('clean_text', article.get('text', ''))

        # Clean and combine
        clean_title = self.clean_text_for_hashing(title)
        clean_content = self.clean_text_for_hashing(content)

        combined = f"{clean_title}|{clean_content}"

        # Create SHA-256 hash
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def create_minhash(self, text: str) -> MinHash:
        """Create MinHash for text similarity"""
        minhash = MinHash(num_perm=self.config.num_perm)

        # Tokenize and add to MinHash
        words = text.split()
        for word in words:
            minhash.update(word.encode('utf-8'))

        return minhash

    def calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate Jaccard similarity between titles"""
        if not title1 or not title2:
            return 0.0

        # Clean titles
        t1 = self.clean_text_for_hashing(title1)
        t2 = self.clean_text_for_hashing(title2)

        # Tokenize
        words1 = set(t1.split())
        words2 = set(t2.split())

        if not words1 or not words2:
            return 0.0

        # Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    def find_duplicates(self, articles: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Find duplicate articles using MinHash LSH"""
        duplicate_groups = {}
        processed_hashes = {}

        for article in articles:
            article_id = article.get('article_id', article.get('id'))
            if not article_id:
                continue

            # Create content hash
            content_hash = self.create_content_hash(article)
            article['content_hash'] = content_hash

            # Create MinHash for similarity
            content = article.get('clean_text', article.get('text', ''))
            if not content:
                continue

            clean_content = self.clean_text_for_hashing(content)
            minhash = self.create_minhash(clean_content)

            # Check for similar articles using LSH
            similar_articles = self.lsh.query(minhash)

            if similar_articles:
                # Found similar articles
                for similar_id in similar_articles:
                    if similar_id not in duplicate_groups:
                        duplicate_groups[similar_id] = []
                    if article_id not in duplicate_groups[similar_id]:
                        duplicate_groups[similar_id].append(article_id)
            else:
                # New unique article
                self.lsh.insert(article_id, minhash)
                duplicate_groups[article_id] = [article_id]

            processed_hashes[article_id] = minhash

        return duplicate_groups

    def choose_canonical_article(self, article_group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Choose canonical article from duplicate group"""
        if len(article_group) == 1:
            return article_group[0]

        # Scoring criteria for canonicalization
        def canonicalization_score(article):
            score = 0

            # Domain priority
            domain = article.get('source_domain', article.get('domain', article.get('source', '')))
            score += self.domain_priority.get(domain.lower(), 0)

            # Earlier publication gets bonus
            published_at = article.get('published_at')
            if published_at:
                try:
                    if isinstance(published_at, str):
                        pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    else:
                        pub_date = published_at

                    # Bonus for being earlier (up to 5 points)
                    now = datetime.utcnow().replace(tzinfo=None)
                    if pub_date.tzinfo:
                        pub_date = pub_date.replace(tzinfo=None)

                    hours_old = (now - pub_date).total_seconds() / 3600
                    if hours_old > 0:
                        score += min(5, hours_old / 24)  # More points for older articles
                except:
                    pass

            # Content length bonus (longer is often more comprehensive)
            content_length = len(article.get('clean_text', article.get('text', '')))
            score += min(3, content_length / 1000)  # Up to 3 points for length

            # Title clarity (no weird characters, reasonable length)
            title = article.get('title_norm', article.get('title', ''))
            if 20 <= len(title) <= 150:  # Reasonable title length
                score += 1

            return score

        # Sort by canonicalization score
        scored_articles = [(canonicalization_score(article), article) for article in article_group]
        scored_articles.sort(key=lambda x: x[0], reverse=True)

        canonical = scored_articles[0][1]

        logger.debug(f"Chose canonical from {len(article_group)} duplicates: {canonical.get('title_norm', '')[:50]}")
        return canonical

    def canonicalize_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Canonicalize articles by removing duplicates and setting canonical references"""
        if not articles:
            return articles

        # Find duplicate groups
        duplicate_groups = self.find_duplicates(articles)

        # Group articles by their duplicate groups
        articles_by_id = {article.get('article_id', article.get('id')): article for article in articles}
        canonical_articles = []
        canonical_map = {}

        for group_key, article_ids in duplicate_groups.items():
            if len(article_ids) == 1:
                # Single article, no duplicates
                article = articles_by_id.get(article_ids[0])
                if article:
                    article['is_canonical'] = True
                    article['alternatives_count'] = 0
                    canonical_articles.append(article)
            else:
                # Multiple articles, need canonicalization
                group_articles = [articles_by_id[aid] for aid in article_ids if aid in articles_by_id]

                # Choose canonical
                canonical = self.choose_canonical_article(group_articles)
                canonical_id = canonical.get('article_id', canonical.get('id'))

                # Mark canonical and alternatives
                canonical['is_canonical'] = True
                canonical['alternatives_count'] = len(group_articles) - 1
                canonical['alternative_ids'] = [
                    article.get('article_id', article.get('id'))
                    for article in group_articles
                    if article != canonical
                ]

                canonical_articles.append(canonical)

                # Update canonical map
                for article in group_articles:
                    aid = article.get('article_id', article.get('id'))
                    canonical_map[aid] = canonical_id

        logger.info(f"Canonicalization: {len(articles)} -> {len(canonical_articles)} unique articles")

        # Store canonical map for future reference
        self.canonical_map.update(canonical_map)

        return canonical_articles

    def get_canonical_id(self, article_id: str) -> str:
        """Get canonical ID for given article ID"""
        return self.canonical_map.get(article_id, article_id)

    def is_duplicate(self, article1: Dict[str, Any], article2: Dict[str, Any]) -> bool:
        """Check if two articles are duplicates"""
        # Quick hash check
        hash1 = article1.get('content_hash') or self.create_content_hash(article1)
        hash2 = article2.get('content_hash') or self.create_content_hash(article2)

        if hash1 == hash2:
            return True

        # Title similarity check
        title1 = article1.get('title_norm', article1.get('title', ''))
        title2 = article2.get('title_norm', article2.get('title', ''))

        title_sim = self.calculate_title_similarity(title1, title2)
        if title_sim >= self.config.title_similarity_threshold:
            return True

        # Content MinHash similarity
        content1 = self.clean_text_for_hashing(article1.get('clean_text', article1.get('text', '')))
        content2 = self.clean_text_for_hashing(article2.get('clean_text', article2.get('text', '')))

        if content1 and content2:
            minhash1 = self.create_minhash(content1)
            minhash2 = self.create_minhash(content2)

            similarity = minhash1.jaccard(minhash2)
            return similarity >= self.config.similarity_threshold

        return False

    def update_database_canonical_refs(self, pg_client, canonical_articles: List[Dict[str, Any]]):
        """Update database with canonical references"""
        try:
            with pg_client._cursor() as cur:
                for article in canonical_articles:
                    article_id = article.get('article_id', article.get('id'))
                    if not article_id:
                        continue

                    # Update canonical references
                    cur.execute("""
                        UPDATE articles_index
                        SET
                            content_hash = %s,
                            is_canonical = %s,
                            canonical_article_id = %s,
                            alternatives_count = %s
                        WHERE article_id = %s OR id = %s
                    """, (
                        article.get('content_hash'),
                        article.get('is_canonical', False),
                        article_id if article.get('is_canonical') else self.get_canonical_id(article_id),
                        article.get('alternatives_count', 0),
                        article_id,
                        article_id
                    ))

                logger.info(f"Updated canonical references for {len(canonical_articles)} articles")

        except Exception as e:
            logger.error(f"Failed to update canonical references: {e}")
            raise