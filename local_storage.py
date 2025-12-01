import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class LocalStorageClient:
    def __init__(self, sqlite_path: str, chroma_path: str):
        self.sqlite_path = sqlite_path
        self.chroma_path = chroma_path
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
        os.makedirs(self.chroma_path, exist_ok=True)
        
        # Initialize SQLite
        self._init_sqlite()
        
        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.chroma_client.get_or_create_collection(name="rss_chunks")

    def _init_sqlite(self):
        """Initialize SQLite tables"""
        with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            # Articles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT,
                    content TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    meta JSON
                )
            """)
            
            # Chunks table (text storage)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER,
                    chunk_index INTEGER,
                    text TEXT,
                    meta JSON,
                    FOREIGN KEY(article_id) REFERENCES articles(id)
                )
            """)
            
            # Feeds table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    last_checked TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            """)
            conn.commit()

    def insert_article(self, article_data: Dict[str, Any]) -> Optional[int]:
        """Insert an article into SQLite"""
        try:
            # Convert datetime objects to strings for JSON serialization
            meta_data = article_data.copy()
            if 'published_at' in meta_data and meta_data['published_at']:
                if hasattr(meta_data['published_at'], 'isoformat'):
                    meta_data['published_at'] = meta_data['published_at'].isoformat()
            
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO articles (url, title, content, status, meta)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    article_data.get('url'),
                    article_data.get('title'),
                    article_data.get('full_text', ''),
                    'pending',
                    json.dumps(meta_data)
                ))
                
                # Get ID (whether inserted or existing)
                cursor.execute("SELECT id FROM articles WHERE url = ?", (article_data.get('url'),))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:

            logger.error(f"Failed to insert article: {e}")
            return None

    def article_exists(self, url: str) -> bool:
        """Check if an article with the given URL already exists"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to check article existence: {e}")
            return False

    def get_pending_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles waiting for processing"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM articles WHERE status = 'pending' LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get pending articles: {e}")
            return []

    def update_article_status(self, article_id: int, status: str):
        """Update article status"""
        with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE articles SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, article_id))
            conn.commit()

    def update_article_content(self, article_id: int, content: str, meta: Dict[str, Any]):
        """Update article content and metadata"""
        with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE articles 
                SET content = ?, meta = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (content, json.dumps(meta), article_id))
            conn.commit()


    def save_chunks(self, article_id: int, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Save chunks to SQLite and Embeddings to ChromaDB"""
        if not chunks:
            return

        try:
            # 1. Save text to SQLite
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                for i, chunk in enumerate(chunks):
                    cursor.execute("""
                        INSERT INTO chunks (article_id, chunk_index, text, meta)
                        VALUES (?, ?, ?, ?)
                    """, (
                        article_id,
                        i,
                        chunk.get('text', ''),
                        json.dumps(chunk)
                    ))
            
            # 2. Save vectors to ChromaDB
            ids = [f"{article_id}_{i}" for i in range(len(chunks))]
            metadatas = [{
                "article_id": article_id,
                "chunk_index": i,
                "url": chunks[i].get('url', ''),
                "title": chunks[i].get('title', '')
            } for i in range(len(chunks))]
            documents = [c.get('text', '') for c in chunks]
            
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            
            logger.info(f"Saved {len(chunks)} chunks for article {article_id}")
            
        except Exception as e:
            logger.error(f"Failed to save chunks: {e}")
            raise

    def search(self, query_embedding: List[float], n_results: int = 5):
        """Search for similar chunks"""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        return results

    # Feed management
    def insert_feed(self, url: str, lang: str = None, category: str = None) -> Optional[int]:
        """Insert a new RSS feed"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO feeds (url, status)
                    VALUES (?, 'active')
                """, (url,))
                
                cursor.execute("SELECT id FROM feeds WHERE url = ?", (url,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Failed to insert feed: {e}")
            return None

    def get_active_feeds(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get active feeds for polling"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                query = "SELECT * FROM feeds WHERE status = 'active'"
                if limit:
                    query += f" LIMIT {limit}"
                cursor.execute(query)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get active feeds: {e}")
            return []

    # UCA Processing methods
    def get_articles_for_uca(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles ready for UCA processing"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM articles 
                    WHERE status = 'processed' 
                    AND uca_status IS NULL
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get UCA articles: {e}")
            return []

    def update_uca_result(self, article_id: int, uca_output: Dict[str, Any], status: str = 'uca_processed'):
        """Save UCA analysis result to database"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE articles 
                    SET uca_status = ?, 
                        uca_result = ?, 
                        uca_processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, json.dumps(uca_output), article_id))
                conn.commit()
                logger.info(f"Updated UCA result for article {article_id}")
        except Exception as e:
            logger.error(f"Failed to update UCA result: {e}")
            raise

    # Deep Analysis methods
    def get_articles_for_deep_analysis(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles ready for Deep Analysis"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM articles 
                    WHERE status = 'processed' 
                    AND deep_analysis_status IS NULL
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get Deep Analysis articles: {e}")
            return []

    def update_deep_analysis_result(self, article_id: int, result: Dict[str, Any], status: str = 'processed'):
        """Save Deep Analysis result to database"""
        try:
            with sqlite3.connect(self.sqlite_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE articles 
                    SET deep_analysis_status = ?, 
                        deep_analysis_result = ?, 
                        deep_analysis_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, json.dumps(result), article_id))
                conn.commit()
                logger.info(f"Updated Deep Analysis result for article {article_id}")
        except Exception as e:
            logger.error(f"Failed to update Deep Analysis result: {e}")
            raise

