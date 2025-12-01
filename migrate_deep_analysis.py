"""
Database migration to add Deep Analysis tracking fields
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = r"D:\Articles\SQLite\rag.db"

def migrate():
    """Add Deep Analysis tracking columns to articles table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(articles)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'deep_analysis_status' not in columns:
            logger.info("Adding deep_analysis_status column...")
            cursor.execute("""
                ALTER TABLE articles 
                ADD COLUMN deep_analysis_status TEXT
            """)
            
        if 'deep_analysis_result' not in columns:
            logger.info("Adding deep_analysis_result column...")
            cursor.execute("""
                ALTER TABLE articles 
                ADD COLUMN deep_analysis_result TEXT
            """)
            
        if 'deep_analysis_at' not in columns:
            logger.info("Adding deep_analysis_at column...")
            cursor.execute("""
                ALTER TABLE articles 
                ADD COLUMN deep_analysis_at TIMESTAMP
            """)
        
        conn.commit()
        logger.info("✅ Migration completed successfully!")
        
        # Show stats
        cursor.execute("SELECT COUNT(*) FROM articles WHERE status='processed' AND deep_analysis_status IS NULL")
        pending_count = cursor.fetchone()[0]
        logger.info(f"📊 Articles ready for Deep Analysis: {pending_count}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    migrate()
