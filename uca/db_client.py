import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class UCADatabaseClient:
    """
    Client for interacting with the main RSSNews SQLite database.
    Path: D:\Articles\SQLite\rag.db
    """
    
    def __init__(self, db_path: str = r"D:\Articles\SQLite\rag.db"):
        self.db_path = db_path

    def get_recent_articles(self, days: int = 1, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch recent articles that have full text content within the last N days.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Calculate cutoff date string if needed, but SQLite's datetime function is safer
                query = f"""
                    SELECT id, url, title, content, meta, created_at 
                    FROM articles 
                    WHERE content IS NOT NULL 
                    AND length(content) > 500
                    AND created_at >= datetime('now', '-{days} days')
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                
                cursor.execute(query, (limit,))
                rows = cursor.fetchall()
                
                articles = []
                for row in rows:
                    article = dict(row)
                    # Parse meta JSON if it exists
                    if article.get('meta') and isinstance(article['meta'], str):
                        try:
                            article['meta'] = json.loads(article['meta'])
                        except:
                            article['meta'] = {}
                    articles.append(article)
                    
                return articles
                
        except Exception as e:
            logger.error(f"Failed to fetch articles from DB: {e}")
            return []

    def get_article_by_id(self, article_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific article by ID.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
                row = cursor.fetchone()
                if row:
                    article = dict(row)
                    if article.get('meta') and isinstance(article['meta'], str):
                        try:
                            article['meta'] = json.loads(article['meta'])
                        except:
                            article['meta'] = {}
                    return article
                return None
        except Exception as e:
            logger.error(f"Failed to fetch article {article_id}: {e}")
            return None
