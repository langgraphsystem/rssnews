"""
PostgreSQL client for RSS news aggregation with enhanced schema
"""

import os
import logging
from psycopg2 import pool as psycopg2_pool
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json

# Json wrapper compatibility (psycopg3 first, fallback to psycopg2)
try:
    # psycopg3
    from psycopg.types.json import Json  # type: ignore
except Exception:  # psycopg2 fallback
    from psycopg2.extras import Json  # type: ignore

logger = logging.getLogger(__name__)

class PgClient:
    def __init__(self):
        self.dsn = os.environ.get('PG_DSN')
        if not self.dsn:
            raise ValueError("PG_DSN environment variable is required")
        # Initialize connection pool (thread-safe) - increased for high load
        minconn = int(os.environ.get('DB_POOL_MIN', '5'))
        maxconn = int(os.environ.get('DB_POOL_MAX', '25'))
        try:
            self.pool = psycopg2_pool.ThreadedConnectionPool(minconn, maxconn, self.dsn)
            logger.info("DB pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize DB pool: {e}")
            raise

    def _cursor(self):
        class _Ctx:
            def __init__(self, outer):
                self.outer = outer
                self.conn = None
                self.cur = None
            def __enter__(self):
                self.conn = self.outer.pool.getconn()
                self.conn.autocommit = True
                self.cur = self.conn.cursor()
                return self.cur
            def __exit__(self, exc_type, exc, tb):
                try:
                    if self.cur:
                        self.cur.close()
                finally:
                    if self.conn:
                        self.outer.pool.putconn(self.conn)
        return _Ctx(self)

    def ensure_schema(self):
        """Create tables if they don't exist"""
        schema_sql = """
        -- feeds (using existing schema structure)
        CREATE TABLE IF NOT EXISTS feeds (
          id SERIAL PRIMARY KEY,
          feed_url TEXT UNIQUE NOT NULL,  -- matches existing schema
          feed_url_canon TEXT,
          lang TEXT,
          status TEXT DEFAULT 'active',
          last_entry_date TEXT,  -- matches existing as text
          last_crawled TEXT,
          no_updates_days INTEGER DEFAULT 0,
          etag TEXT,  -- matches existing
          last_modified TEXT,  -- matches existing
          health_score TEXT DEFAULT '100',
          notes TEXT DEFAULT '',
          checked_at TEXT,
          updated_at TIMESTAMPTZ DEFAULT NOW(),
          -- new fields for enhanced functionality
          category TEXT
        );

        -- raw (ingested articles)
        CREATE TABLE IF NOT EXISTS raw (
          id BIGSERIAL PRIMARY KEY,
          url TEXT NOT NULL,           -- original link
          canonical_url TEXT,          -- after normalization/canonical
          url_hash TEXT UNIQUE NOT NULL,
          source TEXT,                 -- domain
          section TEXT,                -- section/rubric
          title TEXT,
          description TEXT,
          keywords TEXT[],             -- normalized list
          authors TEXT[],              -- list of names
          publisher TEXT,
          top_image TEXT,
          images JSONB,                -- [{src,alt,caption,width,height}]
          videos JSONB,                -- [{src,kind}]
          enclosures JSONB,            -- from RSS
          outlinks TEXT[],             -- external links found in article body

          published_at TIMESTAMPTZ,
          updated_at TIMESTAMPTZ,
          fetched_at TIMESTAMPTZ DEFAULT NOW(),

          language TEXT,               -- e.g. en, en-US
          paywalled BOOLEAN,
          partial BOOLEAN,

          full_text TEXT,
          text_hash TEXT,              -- sha256(normalized text)
          word_count INTEGER,
          reading_time INTEGER,

          status TEXT DEFAULT 'pending', -- pending|processing|stored|duplicate|error|partial
          error_reason TEXT,

          created_at TIMESTAMPTZ DEFAULT NOW(),
          last_seen TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_raw_status ON raw(status);
        CREATE INDEX IF NOT EXISTS idx_raw_text_hash ON raw(text_hash);
        CREATE INDEX IF NOT EXISTS idx_raw_url_hash ON raw(url_hash);

        -- articles_index (for dedup across time + Stage6 readiness)
        CREATE TABLE IF NOT EXISTS articles_index (
          id BIGSERIAL PRIMARY KEY,
          url_hash TEXT,
          -- optional v2 column used by newer pipeline versions
          url_hash_v2 TEXT,
          text_hash TEXT UNIQUE,
          title TEXT,
          author TEXT,
          source TEXT,
          first_seen TIMESTAMPTZ DEFAULT NOW(),
          last_seen TIMESTAMPTZ DEFAULT NOW(),
          -- extended fields expected by Stage 6
          article_id TEXT,
          url TEXT,
          title_norm TEXT,
          clean_text TEXT,
          language TEXT,
          category TEXT,
          tags_norm JSONB,
          published_at TIMESTAMPTZ,
          processing_version INTEGER DEFAULT 1,
          ready_for_chunking BOOLEAN DEFAULT FALSE,
          chunking_completed BOOLEAN
        );
        CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles_index(url_hash);
        CREATE INDEX IF NOT EXISTS idx_articles_text_hash ON articles_index(text_hash);

        -- article_chunks (for Stage 6 & 7)
        CREATE TABLE IF NOT EXISTS article_chunks (
            id BIGSERIAL PRIMARY KEY,
            article_id TEXT NOT NULL,
            processing_version INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT,
            text_clean TEXT,
            word_count_chunk INTEGER,
            char_count_chunk INTEGER,
            char_start INTEGER,
            char_end INTEGER,
            semantic_type TEXT,
            importance_score REAL,
            chunk_strategy TEXT,
            url TEXT,
            title_norm TEXT,
            source_domain TEXT,
            published_at TIMESTAMPTZ,
            language TEXT,
            category TEXT,
            tags_norm JSONB,
            authors_norm JSONB,
            quality_score REAL,
            fts_vector TSVECTOR,
            embedding TEXT,  -- JSON array as text until pgvector is available
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(article_id, processing_version, chunk_index)
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_article_id ON article_chunks(article_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_source_domain_published ON article_chunks(source_domain, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chunks_fts_vector ON article_chunks USING GIN(fts_vector);
        -- CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON article_chunks USING HNSW(embedding public.vector_cosine_ops);

        -- diagnostics
        CREATE TABLE IF NOT EXISTS diagnostics (
          id BIGSERIAL PRIMARY KEY,
          ts TIMESTAMPTZ DEFAULT NOW(),
          level TEXT,                  -- INFO|WARN|ERROR
          component TEXT,              -- poller|worker|parser|db|http
          message TEXT,
          details JSONB
        );

        -- config key/value
        CREATE TABLE IF NOT EXISTS config (
          k TEXT PRIMARY KEY,
          v TEXT
        );
        """
        
        try:
            with self._cursor() as cur:
                cur.execute(schema_sql)
                # Backward-compatible ALTERs for instances created before extended fields
                cur.execute("""
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS url_hash_v2 TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS article_id TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS url TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS title_norm TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS clean_text TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS language TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS category TEXT;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS tags_norm JSONB;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS processing_version INTEGER DEFAULT 1;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS ready_for_chunking BOOLEAN DEFAULT FALSE;
                    ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS chunking_completed BOOLEAN;
                """)
                # Ensure article_chunks has fields produced by chunker
                cur.execute("""
                    ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS boundary_confidence REAL;
                    ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS llm_action TEXT;
                    ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS llm_confidence REAL;
                    ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS llm_reason TEXT;
                """)
                # Indices may fail if they already exist; IF NOT EXISTS guards above suffice for most
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_articles_url_hash_v2 ON articles_index(url_hash_v2);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_ready ON articles_index(ready_for_chunking) WHERE ready_for_chunking IS TRUE;
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_chunk_done ON articles_index(chunking_completed);
                """)
            logger.info("Database schema ensured")
        except Exception as e:
            logger.error(f"Failed to create schema: {e}")
            raise

    def close(self):
        """Close database connection"""
        try:
            if hasattr(self, 'pool') and self.pool:
                self.pool.closeall()
        except Exception:
            pass

    # Config operations
    def set_config(self, key: str, value: str):
        """Set configuration value"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    INSERT INTO config (k, v) VALUES (%s, %s)
                    ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v
                """, (key, str(value)))
        except Exception as e:
            logger.error(f"Failed to set config {key}: {e}")
            raise

    def get_config(self, key: str) -> Optional[str]:
        """Get configuration value"""
        try:
            with self._cursor() as cur:
                cur.execute("SELECT v FROM config WHERE k = %s", (key,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get config {key}: {e}")
            return None

    # Feed operations
    def insert_feed(self, url: str, lang: str = None, category: str = None) -> int:
        """Insert new feed"""
        try:
            with self._cursor() as cur:
                # First check if feed already exists
                cur.execute("SELECT id FROM feeds WHERE feed_url = %s", (url,))
                existing = cur.fetchone()
                if existing:
                    return existing[0]
                
                # Insert new feed
                cur.execute("""
                    INSERT INTO feeds (feed_url, lang, category) 
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (url, lang, category))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to insert feed {url}: {e}")
            raise

    def get_active_feeds(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get active feeds for polling"""
        try:
            with self._cursor() as cur:
                query = """
                    SELECT id, feed_url as url, status, lang, category, etag as last_etag, 
                           last_modified, last_entry_date
                    FROM feeds 
                    WHERE status = 'active'
                    ORDER BY last_entry_date NULLS FIRST, id
                """
                if limit:
                    query += f" LIMIT {limit}"
                
                cur.execute(query)
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get active feeds: {e}")
            return []

    def update_feed(self, feed_id: int, **kwargs):
        """Update feed with provided fields"""
        if not kwargs:
            return
        
        # Map new column names to existing schema
        column_mapping = {
            'last_etag': 'etag',
            'last_modified': 'last_modified',
            'last_entry_date': 'last_entry_date'
        }
        
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            # Map column names to existing schema
            db_column = column_mapping.get(key, key)
            set_clauses.append(f"{db_column} = %s")
            values.append(value)
        
        values.append(feed_id)
        
        try:
            with self._cursor() as cur:
                cur.execute(f"""
                    UPDATE feeds SET {', '.join(set_clauses)}, updated_at = NOW()
                    WHERE id = %s
                """, values)
        except Exception as e:
            logger.error(f"Failed to update feed {feed_id}: {e}")
            raise

    # Raw article operations
    def insert_raw_article(self, article_data: Dict[str, Any]) -> int:
        """Insert raw article using unified schema
        Accepts optional url_hash_v2 (alias) and maps it to url_hash for backward compatibility.
        Uses JSON wrappers for JSONB fields where applicable.
        """
        try:
            processed_data = article_data.copy()

            # Backward/forward compatibility: allow url_hash_v2 alias
            if 'url_hash' not in processed_data and 'url_hash_v2' in processed_data:
                processed_data['url_hash'] = processed_data['url_hash_v2']

            # Wrap JSONB fields with Json for proper casting
            for jsonb_field in ['images', 'videos', 'enclosures']:
                if jsonb_field in processed_data and isinstance(processed_data[jsonb_field], (list, dict)):
                    processed_data[jsonb_field] = Json(processed_data[jsonb_field])

            with self._cursor() as cur:
                try:
                    cur.execute("""
                        INSERT INTO raw (
                            url, canonical_url, url_hash_v2, source, section, title, description,
                            keywords, authors, publisher, top_image, images, videos, enclosures, outlinks,
                            published_at, updated_at, fetched_at, language, paywalled, partial,
                            full_text, text_hash, word_count, reading_time, status, error_reason
                        ) VALUES (
                            %(url)s, %(canonical_url)s, %(url_hash)s, %(source)s, %(section)s,
                            %(title)s, %(description)s, %(keywords)s, %(authors)s, %(publisher)s,
                            %(top_image)s, %(images)s, %(videos)s, %(enclosures)s, %(outlinks)s,
                            %(published_at)s, %(updated_at)s, %(fetched_at)s, %(language)s,
                            %(paywalled)s, %(partial)s, %(full_text)s, %(text_hash)s,
                            %(word_count)s, %(reading_time)s, %(status)s, %(error_reason)s
                        )
                        RETURNING id
                    """, processed_data)
                except Exception:
                    cur.execute("""
                        INSERT INTO raw (
                            url, canonical_url, url_hash, source, section, title, description,
                            keywords, authors, publisher, top_image, images, videos, enclosures, outlinks,
                            published_at, updated_at, fetched_at, language, paywalled, partial,
                            full_text, text_hash, word_count, reading_time, status, error_reason
                        ) VALUES (
                            %(url)s, %(canonical_url)s, %(url_hash)s, %(source)s, %(section)s,
                            %(title)s, %(description)s, %(keywords)s, %(authors)s, %(publisher)s,
                            %(top_image)s, %(images)s, %(videos)s, %(enclosures)s, %(outlinks)s,
                            %(published_at)s, %(updated_at)s, %(fetched_at)s, %(language)s,
                            %(paywalled)s, %(partial)s, %(full_text)s, %(text_hash)s,
                            %(word_count)s, %(reading_time)s, %(status)s, %(error_reason)s
                        )
                        RETURNING id
                    """, processed_data)

                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            if "duplicate key" in str(e) and "url_hash" in str(e):
                # URL already exists - not an error
                logger.debug(f"Article already exists: {article_data.get('url')}")
                return None
            logger.error(f"Failed to insert article: {e}")
            raise

    def bulk_upsert_raw(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Bulk insert (upsert by url_hash_v2 if available; otherwise url_hash) to minimize round-trips.
        Returns counts: {inserted, conflicted}.
        """
        from psycopg2.extras import execute_values
        if not items:
            return {"inserted": 0, "conflicted": 0}

        # Normalize payloads
        rows = []
        for it in items:
            d = it.copy()
            if 'url_hash' not in d and 'url_hash_v2' in d:
                d['url_hash'] = d['url_hash_v2']
            for jf in ['images', 'videos', 'enclosures']:
                if jf in d and isinstance(d[jf], (list, dict)):
                    d[jf] = Json(d[jf])
            rows.append(d)

        cols = [
            'url','canonical_url','url_hash','source','section','title','description',
            'keywords','authors','publisher','top_image','images','videos','enclosures','outlinks',
            'published_at','updated_at','fetched_at','language','paywalled','partial',
            'full_text','text_hash','word_count','reading_time','status','error_reason'
        ]

        inserted = 0
        conflicted = 0
        with self._cursor() as cur:
            # Use url_hash constraint (matches existing schema)
            sql = """
                INSERT INTO raw (
                    url, canonical_url, url_hash, source, section, title, description,
                    keywords, authors, publisher, top_image, images, videos, enclosures, outlinks,
                    published_at, updated_at, fetched_at, language, paywalled, partial,
                    full_text, text_hash, word_count, reading_time, status, error_reason
                ) VALUES %s
                ON CONFLICT (url_hash) DO NOTHING
            """
            values = [tuple(r.get(c) for c in cols) for r in rows]
            execute_values(cur, sql, values)
            inserted = cur.rowcount if cur.rowcount is not None else 0

        conflicted = len(rows) - inserted
        logger.info(f"bulk_upsert_raw", extra={"inserted": inserted, "conflicted": conflicted})
        return {"inserted": inserted, "conflicted": conflicted}

    def get_pending_articles(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending articles for processing"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT id, url, canonical_url, title, description, authors, section, keywords,
                           published_at, language, status, fetched_at, url_hash, text_hash,
                           enclosures
                    FROM raw 
                    WHERE status = 'pending'
                    ORDER BY created_at
                    LIMIT %s
                """, (limit,))
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get pending articles: {e}")
            return []

    def update_article_status(self, article_id: int, status: str, error_reason: str = None):
        """Update article processing status"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    UPDATE raw 
                    SET status = %s, error_reason = %s
                    WHERE id = %s
                """, (status, error_reason, article_id))
        except Exception as e:
            logger.error(f"Failed to update article {article_id} status: {e}")
            raise

    def update_article(self, article_id: int, **kwargs):
        """Update article with provided fields using unified schema"""
        if not kwargs:
            return
        
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            # Handle datetime conversion
            if key in ['fetched_at', 'published_at', 'updated_at'] and hasattr(value, 'isoformat'):
                value = value.isoformat()
            # Handle JSONB fields
            elif key in ['images', 'videos', 'enclosures'] and isinstance(value, (list, dict)):
                value = Json(value)
            
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        values.append(article_id)
        
        try:
            with self._cursor() as cur:
                cur.execute(f"""
                    UPDATE raw SET {', '.join(set_clauses)}
                    WHERE id = %s
                """, values)
        except Exception as e:
            logger.error(f"Failed to update article {article_id}: {e}")
            raise

    def check_duplicate_by_url_hash(self, url_hash: str) -> bool:
        """Check if article exists by URL hash.
        Tries url_hash_v2 first if present in schema, falls back to legacy url_hash.
        """
        try:
            with self._cursor() as cur:
                try:
                    # Try v2 column if it exists
                    cur.execute("SELECT 1 FROM raw WHERE url_hash_v2 = %s LIMIT 1", (url_hash,))
                    if cur.fetchone() is not None:
                        return True
                except Exception:
                    # Column may not exist yet; fall back to legacy field
                    pass

                cur.execute("SELECT 1 FROM raw WHERE url_hash = %s LIMIT 1", (url_hash,))
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to check URL hash duplicate: {e}")
            return False

    def check_duplicate_by_text_hash(self, text_hash: str) -> Optional[int]:
        """Check if article exists by text hash, return article ID if found"""
        try:
            with self._cursor() as cur:
                cur.execute("SELECT id FROM raw WHERE text_hash = %s AND text_hash != ''", (text_hash,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to check text hash duplicate: {e}")
            return None

    # Articles index operations
    def upsert_article_index(self, index_data: Dict[str, Any]):
        """Insert or update article index for deduplication and Stage 6 readiness.
        Accepts optional url_hash_v2 key and maps to url_hash for backward compatibility.
        Supports extended fields: article_id, url, title_norm, clean_text, language, category,
        tags_norm (JSON), published_at, processing_version, ready_for_chunking.
        """
        try:
            payload = index_data.copy()
            # Prefer v2 hash if provided
            if 'url_hash_v2' in payload:
                payload['url_hash'] = payload['url_hash_v2']
            # JSON fields
            if 'tags_norm' in payload and isinstance(payload['tags_norm'], (list, dict)):
                payload['tags_norm'] = Json(payload['tags_norm'])
            # Default processing_version
            if 'processing_version' not in payload or payload.get('processing_version') is None:
                payload['processing_version'] = 1
            with self._cursor() as cur:
                # Use url_hash (consistent with existing schema)
                cur.execute("""
                    INSERT INTO articles_index (
                        url_hash, text_hash, title, author, source,
                        article_id, url, title_norm, clean_text, language, category,
                        tags_norm, published_at, processing_version, ready_for_chunking
                    ) VALUES (
                        %(url_hash)s, %(text_hash)s, %(title)s, %(author)s, %(source)s,
                        %(article_id)s, %(url)s, %(title_norm)s, %(clean_text)s, %(language)s, %(category)s,
                        %(tags_norm)s, %(published_at)s, %(processing_version)s, %(ready_for_chunking)s
                    )
                    ON CONFLICT (text_hash) DO UPDATE SET
                            last_seen = NOW(),
                            title = COALESCE(EXCLUDED.title, articles_index.title),
                            author = COALESCE(EXCLUDED.author, articles_index.author),
                            source = COALESCE(EXCLUDED.source, articles_index.source),
                            article_id = COALESCE(EXCLUDED.article_id, articles_index.article_id),
                            url = COALESCE(EXCLUDED.url, articles_index.url),
                            title_norm = COALESCE(EXCLUDED.title_norm, articles_index.title_norm),
                            clean_text = COALESCE(EXCLUDED.clean_text, articles_index.clean_text),
                            language = COALESCE(EXCLUDED.language, articles_index.language),
                            category = COALESCE(EXCLUDED.category, articles_index.category),
                            tags_norm = COALESCE(EXCLUDED.tags_norm, articles_index.tags_norm),
                            published_at = COALESCE(EXCLUDED.published_at, articles_index.published_at),
                            processing_version = GREATEST(articles_index.processing_version, COALESCE(EXCLUDED.processing_version, 1)),
                            ready_for_chunking = (articles_index.ready_for_chunking OR COALESCE(EXCLUDED.ready_for_chunking, FALSE))
                    """, payload)
        except Exception as e:
            logger.error(f"Failed to upsert article index: {e}")
            raise

    # Diagnostics
    def log_diagnostics(self, level: str, component: str, message: str, details: Dict = None):
        """Log diagnostics event"""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    INSERT INTO diagnostics (level, component, message, details)
                    VALUES (%s, %s, %s, %s)
                """, (level, component, message, Json(details) if details else None))
        except Exception as e:
            logger.error(f"Failed to log diagnostics: {e}")

    # Statistics and monitoring
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            with self._cursor() as cur:
                stats = {}
                
                # Feed stats
                cur.execute("SELECT COUNT(*) FROM feeds WHERE status = 'active'")
                stats['active_feeds'] = cur.fetchone()[0]
                
                # Article stats by status
                cur.execute("""
                    SELECT status, COUNT(*) 
                    FROM raw 
                    WHERE status IS NOT NULL
                    GROUP BY status
                """)
                rows = cur.fetchall()
                article_stats = {row[0]: row[1] for row in rows}
                stats['articles'] = article_stats
                stats['total_articles'] = sum(article_stats.values())
                
                # Recent activity
                cur.execute("""
                    SELECT COUNT(*) FROM raw 
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                """)
                stats['articles_24h'] = cur.fetchone()[0]
                
                return stats
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    # ============== Stage 6 (Chunking) operations ==============
    def get_articles_ready_for_chunking(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch articles from articles_index that are ready for chunking."""
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        COALESCE(article_id, COALESCE(url_hash_v2, url_hash)) AS article_id,
                        COALESCE(url, '') AS url,
                        COALESCE(source, '') AS source,
                        COALESCE(title_norm, '') AS title_norm,
                        COALESCE(clean_text, '') AS clean_text,
                        COALESCE(language, '') AS language,
                        category,
                        tags_norm,
                        published_at,
                        COALESCE(processing_version, 1) AS processing_version
                    FROM articles_index
                    WHERE ready_for_chunking = TRUE
                      AND (chunking_completed IS DISTINCT FROM TRUE)
                    ORDER BY published_at NULLS LAST, id
                    LIMIT %s
                    """,
                    (limit,)
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get articles ready for chunking: {e}")
            return []

    def upsert_article_chunks(self, article_id: str, processing_version: int, chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        """Idempotent upsert of article chunks for a single article within a transaction.
        Uses unique (article_id, processing_version, chunk_index).
        """
        from psycopg2.extras import execute_values
        inserted = 0
        updated = 0
        if not chunks:
            return {"inserted": 0, "updated": 0}
        try:
            with self._cursor() as cur:
                cols = [
                    'article_id','processing_version','chunk_index','text','word_count_chunk',
                    'char_start','char_end','semantic_type','boundary_confidence','llm_action',
                    'llm_confidence','llm_reason','url','title_norm','source_domain',
                    'published_at','language','category','tags_norm'
                ]
                values = []
                for c in chunks:
                    tags = Json(c.get('tags_norm', [])) if isinstance(c.get('tags_norm'), (list, dict)) else c.get('tags_norm')
                    values.append((
                        article_id,
                        processing_version,
                        int(c['chunk_index']),
                        c['text'],
                        int(c['word_count_chunk']),
                        int(c['char_start']),
                        int(c['char_end']),
                        c.get('semantic_type'),
                        float(c.get('boundary_confidence', 0.0)),
                        c.get('llm_action', 'noop'),
                        float(c.get('llm_confidence', 0.0)),
                        c.get('llm_reason'),
                        c['url'],
                        c['title_norm'],
                        c['source_domain'],
                        c.get('published_at'),
                        c['language'],
                        c.get('category'),
                        tags
                    ))
                sql = """
                    INSERT INTO article_chunks (
                        article_id, processing_version, chunk_index, text, word_count_chunk,
                        char_start, char_end, semantic_type, boundary_confidence, llm_action,
                        llm_confidence, llm_reason, url, title_norm, source_domain,
                        published_at, language, category, tags_norm
                    ) VALUES %s
                    ON CONFLICT (article_id, processing_version, chunk_index) DO UPDATE SET
                        text = EXCLUDED.text,
                        word_count_chunk = EXCLUDED.word_count_chunk,
                        char_start = EXCLUDED.char_start,
                        char_end = EXCLUDED.char_end,
                        semantic_type = EXCLUDED.semantic_type,
                        boundary_confidence = EXCLUDED.boundary_confidence,
                        llm_action = EXCLUDED.llm_action,
                        llm_confidence = EXCLUDED.llm_confidence,
                        llm_reason = EXCLUDED.llm_reason,
                        url = EXCLUDED.url,
                        title_norm = EXCLUDED.title_norm,
                        source_domain = EXCLUDED.source_domain,
                        published_at = EXCLUDED.published_at,
                        language = EXCLUDED.language,
                        category = EXCLUDED.category,
                        tags_norm = EXCLUDED.tags_norm
                """
                execute_values(cur, sql, values)
                # rowcount is unreliable with execute_values; return conservative stats
                return {"inserted": 0, "updated": 0}
        except Exception as e:
            logger.error(f"Failed to upsert article chunks for {article_id}: {e}")
            raise

    def mark_chunking_completed(self, article_id: str, processing_version: int) -> None:
        """Mark article as chunking completed."""
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    UPDATE articles_index
                    SET chunking_completed = TRUE,
                        ready_for_chunking = FALSE
                    WHERE COALESCE(article_id::text, COALESCE(url_hash_v2, url_hash)) = %s::text
                """,
                    (str(article_id),)
                )
        except Exception as e:
            logger.error(f"Failed to mark chunking completed for {article_id}: {e}")
            raise

    # --------------- Stage 7 (Indexing) ---------------
    def get_chunks_for_indexing(self, limit: int = 128) -> List[Dict[str, Any]]:
        """Select chunks missing FTS or embedding."""
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT id, article_id, processing_version, chunk_index, text, language
                    FROM article_chunks
                    WHERE (fts_vector IS NULL) OR (embedding IS NULL)
                    ORDER BY id
                    LIMIT %s
                    """,
                    (limit,)
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get chunks for indexing: {e}")
            return []

    def update_chunks_fts(self, ids: List[int]) -> int:
        """Update FTS vectors for given chunk ids using simple config."""
        if not ids:
            return 0
        try:
            with self._cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE article_chunks
                    SET fts_vector = to_tsvector('english', coalesce(text, ''))
                    WHERE id = ANY(%s)
                    """,
                    (ids,)
                )
                return cur.rowcount or 0
        except Exception as e:
            logger.error(f"Failed to update FTS for chunks: {e}")
            return 0

    def update_chunk_embedding(self, chunk_id: int, embedding: List[float]) -> bool:
        """Update embedding vector for single chunk.
        Works with both pgvector and JSON string formats.
        """
        try:
            with self._cursor() as cur:
                vec_str = '[' + ','.join(str(float(x)) for x in embedding) + ']'

                # Try different approaches based on column type
                try:
                    # First try: assume vector column with correct dimensions
                    cur.execute(
                        """
                        UPDATE article_chunks
                        SET embedding = %s::vector
                        WHERE id = %s
                        """,
                        (vec_str, chunk_id)
                    )
                    return True
                except Exception as e1:
                    if "expected" in str(e1) and "dimensions" in str(e1):
                        # Column expects different dimensions - try text/json format
                        try:
                            cur.execute(
                                """
                                UPDATE article_chunks
                                SET embedding = %s::text
                                WHERE id = %s
                                """,
                                (vec_str, chunk_id)
                            )
                            return True
                        except Exception as e2:
                            # Last resort: plain string
                            cur.execute(
                                """
                                UPDATE article_chunks
                                SET embedding = %s
                                WHERE id = %s
                                """,
                                (vec_str, chunk_id)
                            )
                            return True
                    else:
                        raise e1
        except Exception as e:
            logger.error(f"Failed to update embedding for chunk {chunk_id}: {e}")
            return False

    # ============== Stage 8 (Retrieval) operations ==============
    def search_chunks_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search chunks using Full-Text Search (FTS) with BM25 ranking."""
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        id, article_id, chunk_index, text,
                        url, title_norm, source_domain,
                        ts_rank_cd(fts_vector, plainto_tsquery('english', %s)) as score
                    FROM article_chunks
                    WHERE fts_vector @@ plainto_tsquery('english', %s)
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (query, query, limit)
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"FTS search failed for query '{query}': {e}")
            return []

    def search_chunks_fts_ts(self, tsquery: Optional[str], plainto: str,
                              sources: List[str], since_days: Optional[int],
                              limit: int = 10) -> List[Dict[str, Any]]:
        """Search using to_tsquery when tsquery provided; otherwise plainto_tsquery.
        Can filter by source_domain list and published_at > now()-interval 'N days'.
        """
        try:
            where = ["TRUE"]
            params: List[Any] = []
            if tsquery:
                where.append("fts_vector @@ to_tsquery('english', %s)")
                params.append(tsquery)
                rank_expr = "ts_rank_cd(fts_vector, to_tsquery('english', %s))"
                rank_param_first = True
            else:
                where.append("fts_vector @@ plainto_tsquery('english', %s)")
                params.append(plainto)
                rank_expr = "ts_rank_cd(fts_vector, plainto_tsquery('english', %s))"
                rank_param_first = True

            if sources:
                where.append("source_domain = ANY(%s)")
                params.append(sources)
            if since_days:
                where.append("published_at IS NOT NULL AND published_at > NOW() - (%s || ' days')::interval")
                params.append(int(since_days))

            sql = f"""
                SELECT id, article_id, chunk_index, text, url, title_norm, source_domain,
                       {rank_expr} as score
                FROM article_chunks
                WHERE {' AND '.join(where)}
                ORDER BY score DESC
                LIMIT %s
            """
            if rank_param_first:
                params_rank = [params[0]]
            else:
                params_rank = []
            qparams = params_rank + params + [limit]
            with self._cursor() as cur:
                cur.execute(sql, qparams)
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"FTS TS search failed: {e}")
            return []

    def search_chunks_embedding(self, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """Search chunks using basic cosine similarity (fallback without pgvector)."""
        try:
            import json
            with self._cursor() as cur:
                # Get all chunks with embeddings and compute similarity in Python
                cur.execute(
                    """
                    SELECT
                        id, article_id, chunk_index, text,
                        url, title_norm, source_domain, embedding
                    FROM article_chunks
                    WHERE embedding IS NOT NULL
                    """)

                results = []
                for row in cur.fetchall():
                    try:
                        embedding_data = row[7]  # embedding column

                        # Handle both vector and JSON string formats
                        if isinstance(embedding_data, str):
                            # Try to parse as JSON string
                            try:
                                stored_vector = json.loads(embedding_data)
                            except json.JSONDecodeError:
                                # Try to parse as vector string format [1,2,3]
                                if embedding_data.startswith('[') and embedding_data.endswith(']'):
                                    stored_vector = [float(x.strip()) for x in embedding_data[1:-1].split(',')]
                                else:
                                    continue
                        elif isinstance(embedding_data, list):
                            # Already a list
                            stored_vector = embedding_data
                        else:
                            # Skip unknown formats
                            continue

                        if len(stored_vector) == len(query_vector):
                            # Simple cosine similarity
                            dot_product = sum(a * b for a, b in zip(query_vector, stored_vector))
                            norm_a = sum(a * a for a in query_vector) ** 0.5
                            norm_b = sum(b * b for b in stored_vector) ** 0.5
                            similarity = dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0

                            results.append({
                                'id': row[0], 'article_id': row[1], 'chunk_index': row[2],
                                'text': row[3], 'url': row[4], 'title_norm': row[5],
                                'source_domain': row[6], 'score': similarity
                            })
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Failed to parse embedding for chunk {row[0]}: {e}")
                        continue

                # Sort by similarity and limit
                results.sort(key=lambda x: x['score'], reverse=True)
                return results[:limit]

        except Exception as e:
            logger.error(f"Embedding search failed: {e}")
            return []

    def get_chunks_by_ids(self, chunk_ids: List[int]) -> List[Dict[str, Any]]:
        """Get chunks by their IDs with preserved order."""
        if not chunk_ids:
            return []

        try:
            with self._cursor() as cur:
                # Create a placeholder for each ID and preserve order using CASE
                placeholders = ','.join(['%s'] * len(chunk_ids))
                order_cases = []
                for i, chunk_id in enumerate(chunk_ids):
                    order_cases.append(f"WHEN id = {chunk_id} THEN {i}")

                order_clause = f"ORDER BY CASE {' '.join(order_cases)} ELSE {len(chunk_ids)} END"

                cur.execute(
                    f"""
                    SELECT
                        id, article_id, chunk_index, text,
                        url, title_norm, source_domain, language
                    FROM article_chunks
                    WHERE id IN ({placeholders})
                    {order_clause}
                    """,
                    chunk_ids
                )

                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Get chunks by IDs failed: {e}")
            return []

    def hybrid_search(self, query: str, query_vector: List[float], limit: int = 10, alpha: float = 0.5) -> List[Dict[str, Any]]:
        """Combines FTS and embedding search with weighted ranking (Reciprocal Rank Fusion)."""
        try:
            fts_results = self.search_chunks_fts(query, limit=limit * 2)
            emb_results = self.search_chunks_embedding(query_vector, limit=limit * 2)

            # Create rank maps
            fts_ranks = {res['id']: i + 1 for i, res in enumerate(fts_results)}
            emb_ranks = {res['id']: i + 1 for i, res in enumerate(emb_results)}

            all_ids = set(fts_ranks.keys()) | set(emb_ranks.keys())
            
            fused_scores = {}
            k = 60  # RRF constant
            for doc_id in all_ids:
                fts_score = 1 / (k + fts_ranks.get(doc_id, 1_000_000))
                emb_score = 1 / (k + emb_ranks.get(doc_id, 1_000_000))
                fused_scores[doc_id] = (alpha * fts_score) + ((1 - alpha) * emb_score)

            # Sort by fused score
            sorted_ids = sorted(fused_scores.keys(), key=lambda doc_id: fused_scores[doc_id], reverse=True)[:limit]

            # Fetch full chunk data for the top results
            all_results = {res['id']: res for res in fts_results + emb_results}
            final_results = [all_results[doc_id] for doc_id in sorted_ids if doc_id in all_results]
            
            return final_results

        except Exception as e:
            logger.error(f"Hybrid search failed for query '{query}': {e}")
            return []

    def get_chunks_needing_fts_update(self, limit: int = 100) -> List[int]:
        """Get chunk IDs that need FTS vector updates."""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT id FROM article_chunks
                    WHERE fts_vector IS NULL
                    ORDER BY id
                    LIMIT %s
                """, (limit,))
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get chunks needing FTS update: {e}")
            return []

    def get_chunks_needing_embeddings(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get chunks that need embeddings."""
        try:
            with self._cursor() as cur:
                cur.execute("""
                    SELECT id, text FROM article_chunks
                    WHERE embedding IS NULL
                    ORDER BY id
                    LIMIT %s
                """, (limit,))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get chunks needing embeddings: {e}")
            return []

    def get_all_chunks_for_embedding(self) -> List[Dict[str, Any]]:
        """Get all chunks for embedding rebuild."""
        try:
            with self._cursor() as cur:
                cur.execute("SELECT id, text FROM article_chunks ORDER BY id")
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get all chunks for embedding: {e}")
            return []

    def search_chunks_by_similarity(self, query_embedding: List[float],
                                   limit: int = 10, similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search chunks by embedding similarity using cosine similarity."""
        try:
            import json
            with self._cursor() as cur:
                # Get all chunks with embeddings and compute similarity in Python
                cur.execute("""
                    SELECT
                        id, article_id, chunk_index, text,
                        url, title_norm, source_domain, embedding
                    FROM article_chunks
                    WHERE embedding IS NOT NULL
                """)

                results = []
                for row in cur.fetchall():
                    try:
                        embedding_data = row[7]  # embedding column

                        # Handle both vector and JSON string formats
                        if isinstance(embedding_data, str):
                            # Try to parse as JSON string
                            try:
                                stored_vector = json.loads(embedding_data)
                            except json.JSONDecodeError:
                                # Try to parse as vector string format [1,2,3]
                                if embedding_data.startswith('[') and embedding_data.endswith(']'):
                                    stored_vector = [float(x.strip()) for x in embedding_data[1:-1].split(',')]
                                else:
                                    continue
                        elif isinstance(embedding_data, list):
                            # Already a list
                            stored_vector = embedding_data
                        else:
                            # Skip unknown formats
                            continue

                        if len(stored_vector) == len(query_embedding):
                            # Simple cosine similarity
                            dot_product = sum(a * b for a, b in zip(query_embedding, stored_vector))
                            norm_a = sum(a * a for a in query_embedding) ** 0.5
                            norm_b = sum(b * b for b in stored_vector) ** 0.5
                            similarity = dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0

                            if similarity >= similarity_threshold:
                                results.append({
                                    'id': row[0], 'article_id': row[1], 'chunk_index': row[2],
                                    'text': row[3], 'url': row[4], 'title_norm': row[5],
                                    'source_domain': row[6], 'similarity': similarity
                                })
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Failed to parse embedding for chunk {row[0]}: {e}")
                        continue

                # Sort by similarity and limit
                results.sort(key=lambda x: x['similarity'], reverse=True)
                return results[:limit]

        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []
