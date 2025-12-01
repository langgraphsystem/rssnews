import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class AnalysisStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize Analysis Database"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # Analysis Articles table
                # Stores a copy of necessary data + analysis results
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS analysis_articles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_id INTEGER,
                        url TEXT UNIQUE NOT NULL,
                        title TEXT,
                        content TEXT,
                        published_at TIMESTAMP,
                        
                        deep_analysis_status TEXT DEFAULT 'pending',
                        deep_analysis_result JSON,
                        deep_analysis_at TIMESTAMP,
                        
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init analysis DB: {e}")
            raise

    def sync_article(self, article: Dict[str, Any]) -> bool:
        """
        Sync an article from main DB to Analysis DB.
        Returns True if inserted, False if already exists.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # Check if exists by URL
                cursor.execute("SELECT 1 FROM analysis_articles WHERE url = ?", (article['url'],))
                if cursor.fetchone():
                    return False
                
                # Insert
                cursor.execute("""
                    INSERT INTO analysis_articles (
                        original_id, url, title, content, published_at
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    article['id'],
                    article['url'],
                    article.get('title'),
                    article.get('content'), # Full text
                    article.get('published_at') or article.get('created_at')
                ))
                return True
        except Exception as e:
            logger.error(f"Failed to sync article {article.get('url')}: {e}")
            return False

    def get_pending_analysis(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles pending deep analysis"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM analysis_articles 
                    WHERE deep_analysis_status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get pending analysis: {e}")
            return []

    def update_analysis_result(self, article_id: int, result: Dict[str, Any], status: str = 'processed'):
        """Save analysis result"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE analysis_articles 
                    SET deep_analysis_status = ?, 
                        deep_analysis_result = ?, 
                        deep_analysis_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, json.dumps(result), article_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update analysis result: {e}")
            raise

    def get_stats(self):
        """Get simple stats"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM analysis_articles")
                total = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM analysis_articles WHERE deep_analysis_status='processed'")
                processed = cursor.fetchone()[0]
                return {"total": total, "processed": processed, "pending": total - processed}
        except:
            return {}
