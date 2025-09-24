"""
Clustering and Trends Detection Service
Uses HDBSCAN for automatic topic discovery and trend analysis
"""

import os
import sys
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.production_db_client import ProductionDBClient

logger = logging.getLogger(__name__)


@dataclass
class ClusterConfig:
    """Configuration for clustering analysis"""
    min_cluster_size: int = 5
    min_samples: int = 3
    cluster_selection_epsilon: float = 0.0
    max_cluster_size: int = 0
    metric: str = 'euclidean'
    alpha: float = 1.0


class ClusteringService:
    """Service for clustering articles and detecting trends"""

    def __init__(self, db_client: ProductionDBClient = None):
        self.db = db_client or ProductionDBClient()
        self.config = ClusterConfig()

        # Choose HDBSCAN implementation
        self._init_clustering_backend()

    def _init_clustering_backend(self):
        """Initialize HDBSCAN clustering backend"""
        try:
            # Try scikit-learn integrated HDBSCAN first (recommended for 2025)
            from sklearn.cluster import HDBSCAN
            self.use_sklearn_hdbscan = True
            logger.info("Using scikit-learn integrated HDBSCAN 1.7.2+")
        except ImportError:
            # Fallback to standalone hdbscan package
            try:
                import hdbscan
                self.use_sklearn_hdbscan = False
                logger.info("Using standalone HDBSCAN 0.8.40")
            except ImportError:
                logger.error("No HDBSCAN implementation available")
                raise ImportError("Please install either scikit-learn>=1.7.2 or hdbscan>=0.8.40")

    def create_clusterer(self) -> Any:
        """Create HDBSCAN clusterer with current configuration"""
        if self.use_sklearn_hdbscan:
            from sklearn.cluster import HDBSCAN
            # Note: scikit-learn HDBSCAN includes the point itself in min_samples
            # so we need to add 1 to match standalone hdbscan behavior
            return HDBSCAN(
                min_cluster_size=self.config.min_cluster_size,
                min_samples=self.config.min_samples + 1,  # +1 for sklearn compatibility
                cluster_selection_epsilon=self.config.cluster_selection_epsilon,
                max_cluster_size=self.config.max_cluster_size,
                metric=self.config.metric,
                alpha=self.config.alpha
            )
        else:
            import hdbscan
            return hdbscan.HDBSCAN(
                min_cluster_size=self.config.min_cluster_size,
                min_samples=self.config.min_samples,
                cluster_selection_epsilon=self.config.cluster_selection_epsilon,
                max_cluster_size=self.config.max_cluster_size,
                metric=self.config.metric,
                alpha=self.config.alpha
            )

    async def detect_trends(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """Detect trending topics in recent articles"""
        try:
            logger.info(f"Detecting trends for last {time_window_hours} hours")

            # Get recent articles with embeddings
            recent_articles = self._get_recent_articles_with_embeddings(time_window_hours)

            if len(recent_articles) < self.config.min_cluster_size:
                logger.warning(f"Not enough articles ({len(recent_articles)}) for clustering")
                return {'trends': [], 'total_articles': len(recent_articles)}

            # Extract embeddings
            embeddings = np.array([article['embedding'] for article in recent_articles])

            # Perform clustering
            clusterer = self.create_clusterer()
            cluster_labels = clusterer.fit_predict(embeddings)

            # Analyze clusters
            trends = self._analyze_clusters(recent_articles, cluster_labels, clusterer)

            # Store trends in database
            await self._store_trends(trends, time_window_hours)

            logger.info(f"Detected {len(trends)} trends from {len(recent_articles)} articles")

            return {
                'trends': trends,
                'total_articles': len(recent_articles),
                'time_window_hours': time_window_hours,
                'clusters_found': len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
            }

        except Exception as e:
            logger.error(f"Trend detection failed: {e}")
            return {'error': str(e)}

    def _get_recent_articles_with_embeddings(self, hours: int) -> List[Dict[str, Any]]:
        """Get recent articles that have embeddings"""
        try:
            with self.db._cursor() as cur:
                cur.execute("""
                    SELECT
                        ai.article_id,
                        ai.title_norm,
                        ai.clean_text,
                        ai.source,
                        ai.published_at,
                        ac.embedding
                    FROM articles_index ai
                    JOIN article_chunks ac ON ai.article_id = ac.article_id
                    WHERE ai.published_at >= NOW() - INTERVAL '%s hours'
                        AND ac.embedding IS NOT NULL
                        AND ai.language = 'en'
                    ORDER BY ai.published_at DESC
                    LIMIT 1000
                """, (hours,))

                rows = cur.fetchall()
                articles = []

                for row in rows:
                    articles.append({
                        'article_id': row[0],
                        'title': row[1],
                        'text': row[2],
                        'source': row[3],
                        'published_at': row[4],
                        'embedding': row[5]  # pgvector array
                    })

                return articles

        except Exception as e:
            logger.error(f"Failed to get recent articles: {e}")
            return []

    def _analyze_clusters(self, articles: List[Dict[str, Any]],
                         labels: np.ndarray, clusterer: Any) -> List[Dict[str, Any]]:
        """Analyze clusters to extract trend information"""
        trends = []

        try:
            unique_labels = set(labels)
            if -1 in unique_labels:
                unique_labels.remove(-1)  # Remove noise points

            for cluster_id in unique_labels:
                cluster_mask = labels == cluster_id
                cluster_articles = [articles[i] for i in np.where(cluster_mask)[0]]

                if len(cluster_articles) < self.config.min_cluster_size:
                    continue

                # Extract trend information
                trend = self._extract_trend_info(cluster_id, cluster_articles, clusterer)
                trends.append(trend)

            # Sort by cluster size and recency
            trends.sort(key=lambda x: (x['size'], x['avg_freshness']), reverse=True)

            return trends

        except Exception as e:
            logger.error(f"Cluster analysis failed: {e}")
            return []

    def _extract_trend_info(self, cluster_id: int, articles: List[Dict[str, Any]],
                           clusterer: Any) -> Dict[str, Any]:
        """Extract information about a trend cluster"""
        try:
            # Basic statistics
            size = len(articles)
            sources = list(set(article['source'] for article in articles))

            # Time analysis
            timestamps = [article['published_at'] for article in articles if article['published_at']]
            if timestamps:
                timestamps.sort()
                earliest = timestamps[0]
                latest = timestamps[-1]
                span_hours = (latest - earliest).total_seconds() / 3600
            else:
                earliest = latest = None
                span_hours = 0

            # Content analysis
            all_titles = ' '.join(article['title'] for article in articles)
            keywords = self._extract_keywords(all_titles)

            # Generate topic label
            topic_label = self._generate_topic_label(articles, keywords)

            # Freshness score (how recent on average)
            now = datetime.utcnow()
            avg_age_hours = np.mean([
                (now - article['published_at']).total_seconds() / 3600
                for article in articles if article['published_at']
            ]) if timestamps else 0

            avg_freshness = max(0, 1 - (avg_age_hours / 72))  # 72h decay

            return {
                'cluster_id': int(cluster_id),
                'topic_label': topic_label,
                'size': size,
                'sources': sources,
                'keywords': keywords[:10],  # Top 10 keywords
                'time_span_hours': span_hours,
                'earliest_article': earliest.isoformat() if earliest else None,
                'latest_article': latest.isoformat() if latest else None,
                'avg_freshness': avg_freshness,
                'sample_articles': [
                    {
                        'title': article['title'],
                        'source': article['source'],
                        'published_at': article['published_at'].isoformat() if article['published_at'] else None
                    }
                    for article in articles[:3]  # Sample articles
                ]
            }

        except Exception as e:
            logger.error(f"Trend info extraction failed: {e}")
            return {'cluster_id': cluster_id, 'error': str(e)}

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        try:
            # Simple keyword extraction
            words = text.lower().split()

            # Filter out common words
            stop_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                'should', 'may', 'might', 'must', 'this', 'that', 'these', 'those'
            }

            # Count word frequency
            word_freq = {}
            for word in words:
                if (len(word) > 3 and
                    word.isalpha() and
                    word not in stop_words):
                    word_freq[word] = word_freq.get(word, 0) + 1

            # Return top keywords
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [word for word, freq in sorted_words if freq >= 2]

        except Exception as e:
            logger.error(f"Keyword extraction failed: {e}")
            return []

    def _generate_topic_label(self, articles: List[Dict[str, Any]],
                            keywords: List[str]) -> str:
        """Generate a human-readable topic label"""
        try:
            if keywords:
                # Use top keywords
                top_keywords = keywords[:3]
                return ' + '.join(word.title() for word in top_keywords)
            else:
                # Fallback to most common source
                sources = [article['source'] for article in articles]
                most_common_source = max(set(sources), key=sources.count)
                return f"Topic from {most_common_source}"

        except Exception as e:
            logger.error(f"Topic label generation failed: {e}")
            return "Unknown Topic"

    async def _store_trends(self, trends: List[Dict[str, Any]], time_window_hours: int):
        """Store detected trends in database"""
        try:
            with self.db._cursor() as cur:
                now = datetime.utcnow()
                window_start = now - timedelta(hours=time_window_hours)

                for trend in trends:
                    topic_id = f"trend_{now.strftime('%Y%m%d_%H')}_{trend['cluster_id']}"

                    cur.execute("""
                        INSERT INTO clusters_topics (
                            topic_id, topic_label, confidence_score,
                            top_keywords, total_articles,
                            time_window_start, time_window_end,
                            category, trend_status, cluster_algorithm,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (topic_id) DO UPDATE SET
                            total_articles = EXCLUDED.total_articles,
                            updated_at = EXCLUDED.updated_at
                    """, (
                        topic_id,
                        trend['topic_label'],
                        trend['avg_freshness'],
                        trend['keywords'],
                        trend['size'],
                        window_start,
                        now,
                        'news_trend',
                        'emerging' if trend['avg_freshness'] > 0.7 else 'established',
                        'HDBSCAN-2025',
                        now,
                        now
                    ))

                logger.info(f"Stored {len(trends)} trends in database")

        except Exception as e:
            logger.error(f"Failed to store trends: {e}")


async def main():
    """CLI entry point for clustering service"""
    import argparse

    parser = argparse.ArgumentParser(description='RSS News Clustering Service')
    parser.add_argument('command', choices=['trends', 'test'],
                       help='Command to run')
    parser.add_argument('--hours', type=int, default=24,
                       help='Time window for trend detection')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize service
    service = ClusteringService()

    if args.command == 'trends':
        # Detect trends
        result = await service.detect_trends(args.hours)

        print(f"🔍 Trend Detection Results ({args.hours}h window)")
        print(f"Total articles analyzed: {result.get('total_articles', 0)}")
        print(f"Trends found: {len(result.get('trends', []))}")

        for i, trend in enumerate(result.get('trends', [])[:5], 1):
            print(f"\n{i}. {trend['topic_label']}")
            print(f"   Size: {trend['size']} articles")
            print(f"   Sources: {', '.join(trend['sources'][:3])}")
            print(f"   Keywords: {', '.join(trend['keywords'][:5])}")
            print(f"   Freshness: {trend['avg_freshness']:.2f}")

    elif args.command == 'test':
        # Test clustering setup
        try:
            clusterer = service.create_clusterer()
            print(f"✅ Clustering backend initialized: {'sklearn' if service.use_sklearn_hdbscan else 'standalone'}")
            print(f"Configuration: {service.config}")
        except Exception as e:
            print(f"❌ Clustering test failed: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())