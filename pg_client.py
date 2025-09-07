import os
import logging
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from datetime import datetime

from utils import now_local_iso

logger = logging.getLogger(__name__)

class PgClient:
    def __init__(self):
        self.dsn = os.environ.get('PG_DSN')
        if not self.dsn:
            raise ValueError("PG_DSN environment variable is required")
        
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(self.dsn)
            self.conn.autocommit = True
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _create_tables(self):
        """Create tables if they don't exist"""
        schema_sql = """
        -- feeds
        create table if not exists feeds (
          id serial primary key,
          feed_url text,
          feed_url_canon text unique not null,
          lang text,
          status text default 'active',
          last_entry_date timestamptz,
          last_crawled text,
          no_updates_days integer,
          etag text,
          last_modified text,
          health_score text,
          notes text,
          checked_at text,
          updated_at timestamptz default now()
        );

        -- raw
        create table if not exists raw (
          id bigserial primary key,
          row_id integer,
          source text,
          feed_url text,
          article_url text,
          article_url_canon text,
          url_hash text unique not null,
          text_hash text,
          found_at text,
          fetched_at text,
          published_at text,
          language text,
          title text,
          subtitle text,
          authors text,
          section text,
          tags text,
          article_type text,
          clean_text text,
          clean_text_len integer,
          full_text_ref text,
          full_text_len integer,
          word_count integer,
          out_links text,
          category_guess text,
          status text default 'pending',
          lock_owner text default '',
          lock_at text default '',
          processed_at text,
          retries integer default 0,
          error_msg text,
          sources_list text,
          aliases text,
          last_seen_rss text,
          created_at timestamptz default now(),
          updated_at timestamptz default now()
        );
        create index if not exists idx_raw_status on raw(status);
        create index if not exists idx_raw_text_hash on raw(text_hash);

        -- articles_index
        create table if not exists articles_index (
          id bigserial primary key,
          url_hash text,
          text_hash text,
          article_url_canon text,
          row_id_raw integer,
          first_seen text,
          last_seen text,
          is_duplicate text,
          reason text,
          language text,
          category_guess text,
          rev_n integer,
          created_at timestamptz default now()
        );
        create index if not exists idx_articles_url_hash on articles_index(url_hash);
        create index if not exists idx_articles_text_hash on articles_index(text_hash);

        -- diagnostics
        create table if not exists diagnostics (
          id bigserial primary key,
          ts timestamptz default now(),
          level text,
          component text,
          message text,
          details jsonb
        );

        -- config
        create table if not exists config (
          k text primary key,
          v text
        );
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(schema_sql)
            logger.info("Database schema created/verified")
        except Exception as e:
            logger.error(f"Failed to create schema: {e}")
            self._log_diagnostics("error", "schema", f"Schema creation failed: {e}")
            raise

    def ensure_worksheets(self):
        """Compatibility method - equivalent to sheets ensure_worksheets"""
        # Tables are already created in __init__
        self.upsert_config("schema_version", "v1")
        self.upsert_config("created_or_migrated_at", now_local_iso())

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def _log_diagnostics(self, level: str, component: str, message: str, details: Dict = None):
        """Log to diagnostics table"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO diagnostics (level, component, message, details) 
                    VALUES (%s, %s, %s, %s)
                """, (level, component, message, details))
        except Exception as e:
            logger.error(f"Failed to log diagnostics: {e}")

    # Config operations
    def upsert_config(self, key: str, value: str):
        """Insert or update config key-value pair"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO config (k, v) VALUES (%s, %s)
                    ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v
                """, (key, str(value)))
        except Exception as e:
            logger.error(f"Failed to upsert config {key}: {e}")
            self._log_diagnostics("error", "config", f"Config upsert failed: {e}")
            raise

    def get_config(self, key: str) -> Optional[str]:
        """Get config value by key"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT v FROM config WHERE k = %s", (key,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get config {key}: {e}")
            return None

    # Feeds operations
    def upsert_feed(self, feed_row: Dict[str, Any]):
        """Insert or update feed"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO feeds (
                        feed_url, feed_url_canon, lang, status, last_entry_date,
                        last_crawled, no_updates_days, etag, last_modified,
                        health_score, notes, checked_at
                    ) VALUES (
                        %(feed_url)s, %(feed_url_canon)s, %(lang)s, %(status)s, %(last_entry_date)s,
                        %(last_crawled)s, %(no_updates_days)s, %(etag)s, %(last_modified)s,
                        %(health_score)s, %(notes)s, %(checked_at)s
                    )
                    ON CONFLICT (feed_url_canon) DO UPDATE SET
                        feed_url = EXCLUDED.feed_url,
                        lang = EXCLUDED.lang,
                        status = EXCLUDED.status,
                        last_entry_date = EXCLUDED.last_entry_date,
                        last_crawled = EXCLUDED.last_crawled,
                        no_updates_days = EXCLUDED.no_updates_days,
                        etag = EXCLUDED.etag,
                        last_modified = EXCLUDED.last_modified,
                        health_score = EXCLUDED.health_score,
                        notes = EXCLUDED.notes,
                        checked_at = EXCLUDED.checked_at,
                        updated_at = now()
                """, feed_row)
        except Exception as e:
            logger.error(f"Failed to upsert feed: {e}")
            self._log_diagnostics("error", "feeds", f"Feed upsert failed: {e}")
            raise

    def get_active_feeds(self) -> List[Dict[str, Any]]:
        """Get all active feeds for polling"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, feed_url, feed_url_canon, lang, status, 
                           last_entry_date, last_crawled, no_updates_days,
                           etag, last_modified, health_score, notes, checked_at
                    FROM feeds WHERE status = 'active'
                    ORDER BY id
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get active feeds: {e}")
            return []

    def update_feed(self, feed_id: int, patches: Dict[str, Any]):
        """Update specific feed fields"""
        if not patches:
            return
        
        set_clauses = []
        values = []
        
        for key, value in patches.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        values.append(feed_id)
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE feeds SET {', '.join(set_clauses)}, updated_at = now()
                    WHERE id = %s
                """, values)
        except Exception as e:
            logger.error(f"Failed to update feed {feed_id}: {e}")
            self._log_diagnostics("error", "feeds", f"Feed update failed: {e}")
            raise

    # Compatibility methods for sheets-like interface
    def ws(self, name: str):
        """Compatibility method - returns self for chaining"""
        self._current_ws = name
        return self
        
    def get_all_values(self):
        """Compatibility method for worksheets - returns rows like sheets"""
        if not hasattr(self, '_current_ws') or self._current_ws == 'Feeds':
            try:
                with self.conn.cursor() as cur:
                    cur.execute("""
                        SELECT feed_url, feed_url_canon, lang, status, 
                               last_entry_date, last_crawled, no_updates_days,
                               etag, last_modified, health_score, notes, checked_at
                        FROM feeds ORDER BY id
                    """)
                    rows = cur.fetchall()
                    # Return with headers as first row (like sheets)
                    header = ["feed_url", "feed_url_canon", "lang", "status", 
                             "last_entry_date", "last_crawled", "no_updates_days",
                             "etag", "last_modified", "health_score", "notes", "checked_at"]
                    result = [header] + [list(row) for row in rows]
                    return result
            except Exception as e:
                logger.error(f"Failed to get all feeds: {e}")
                return []
        elif self._current_ws == 'Raw':
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM raw")
                    count = cur.fetchone()[0]
                    # Return minimal structure for compatibility
                    return [self.row_values(1)] + [[] for _ in range(count)]
            except Exception as e:
                logger.error(f"Failed to get raw count: {e}")
                return []
        return []

    # Raw table operations
    def append_raw_minimal(self, data: Dict[str, Any]) -> int:
        """Append row to raw table and return row ID"""
        try:
            with self.conn.cursor() as cur:
                # Get all the RAW_HEADERS fields from data
                fields = [
                    'source', 'feed_url', 'article_url', 'article_url_canon', 'url_hash',
                    'text_hash', 'found_at', 'fetched_at', 'published_at', 'language',
                    'title', 'subtitle', 'authors', 'section', 'tags', 'article_type',
                    'clean_text', 'clean_text_len', 'full_text_ref', 'full_text_len',
                    'word_count', 'out_links', 'category_guess', 'status', 'lock_owner',
                    'lock_at', 'processed_at', 'retries', 'error_msg', 'sources_list',
                    'aliases', 'last_seen_rss'
                ]
                
                field_placeholders = ', '.join([f'%({field})s' for field in fields])
                field_names = ', '.join(fields)
                
                cur.execute(f"""
                    INSERT INTO raw ({field_names})
                    VALUES ({field_placeholders})
                    RETURNING id
                """, data)
                
                row_id = cur.fetchone()[0]
                
                # Update the row_id field with the actual row_id
                cur.execute("UPDATE raw SET row_id = %s WHERE id = %s", (row_id, row_id))
                
                return row_id
        except Exception as e:
            # Не логируем ошибки дедупликации как ошибки - это нормальное поведение
            if "duplicate key" not in str(e) or "url_hash" not in str(e):
                logger.error(f"Failed to append raw row: {e}")
                self._log_diagnostics("error", "raw", f"Raw append failed: {e}")
            raise

    def update_raw_row(self, row_id: int, patch: Dict[str, Any]):
        """Update specific fields in raw table row"""
        if not patch:
            return
            
        set_clauses = []
        values = []
        
        for key, value in patch.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        values.append(row_id)
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE raw SET {', '.join(set_clauses)}, updated_at = now()
                    WHERE row_id = %s
                """, values)
        except Exception as e:
            logger.error(f"Failed to update raw row {row_id}: {e}")
            self._log_diagnostics("error", "raw", f"Raw update failed: {e}")
            raise

    def get_pending_raw_rows(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending rows from raw table for processing"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM raw 
                    WHERE status = 'pending' AND (lock_owner IS NULL OR lock_owner = '')
                    ORDER BY id 
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pending raw rows: {e}")
            return []

    def row_values(self, row_num: int) -> List[str]:
        """Compatibility method - returns header row for raw table"""
        if row_num == 1:
            return [
                "row_id", "source", "feed_url", "article_url", "article_url_canon",
                "url_hash", "text_hash", "found_at", "fetched_at", "published_at",
                "language", "title", "subtitle", "authors", "section", "tags",
                "article_type", "clean_text", "clean_text_len", "full_text_ref",
                "full_text_len", "word_count", "out_links", "category_guess",
                "status", "lock_owner", "lock_at", "processed_at", "retries",
                "error_msg", "sources_list", "aliases", "last_seen_rss"
            ]
        return []

    def update_cell(self, row: int, col: int, value: str):
        """Compatibility method - update single cell in raw table"""
        # This requires mapping column numbers to field names
        header = self.row_values(1)
        if col <= len(header):
            field_name = header[col - 1]  # col is 1-based
            self.update_raw_row(row, {field_name: value})

    # Articles Index operations  
    def find_row_by_url_hash(self, url_hash: str) -> Optional[int]:
        """Find raw table row_id by url_hash in articles_index"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT row_id_raw FROM articles_index 
                    WHERE url_hash = %s
                """, (url_hash,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to find row by url_hash {url_hash}: {e}")
            return None

    def find_row_by_text_hash(self, text_hash: str) -> Optional[int]:
        """Find raw table row_id by text_hash in articles_index"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT row_id_raw FROM articles_index 
                    WHERE text_hash = %s
                """, (text_hash,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to find row by text_hash {text_hash}: {e}")
            return None

    def upsert_index(self, entry: Dict[str, Any]):
        """Insert or update article index entry"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO articles_index (
                        url_hash, text_hash, article_url_canon, row_id_raw,
                        first_seen, last_seen, is_duplicate, reason,
                        language, category_guess, rev_n
                    ) VALUES (
                        %(url_hash)s, %(text_hash)s, %(article_url_canon)s, %(row_id_raw)s,
                        %(first_seen)s, %(last_seen)s, %(is_duplicate)s, %(reason)s,
                        %(language)s, %(category_guess)s, %(rev_n)s
                    )
                    ON CONFLICT (url_hash) DO UPDATE SET
                        text_hash = EXCLUDED.text_hash,
                        article_url_canon = EXCLUDED.article_url_canon,
                        row_id_raw = EXCLUDED.row_id_raw,
                        last_seen = EXCLUDED.last_seen,
                        is_duplicate = EXCLUDED.is_duplicate,
                        reason = EXCLUDED.reason,
                        language = EXCLUDED.language,
                        category_guess = EXCLUDED.category_guess,
                        rev_n = EXCLUDED.rev_n
                """, entry)
        except Exception as e:
            # Не логируем constraint ошибки как критические - они ожидаемы при дедупликации  
            if "constraint" not in str(e).lower() and "conflict" not in str(e).lower():
                logger.error(f"Failed to upsert index entry: {e}")
                self._log_diagnostics("error", "articles_index", f"Index upsert failed: {e}")
            raise

    # Diagnostics operations (already implemented in _log_diagnostics)
    def log_diagnostics(self, level: str, component: str, message: str, details: Dict = None):
        """Public method to log diagnostics"""
        self._log_diagnostics(level, component, message, details)