"""
Database migration to add UCA processing tracking fields
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = r"D:\Articles\SQLite\rag.db"

def migrate():
    """Add UCA processing tracking columns to articles table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(articles)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'uca_status' not in columns:
            logger.info("Adding uca_status column...")
            cursor.execute("""
                ALTER TABLE articles 
                ADD COLUMN uca_status TEXT
            """)
            
        if 'uca_result' not in columns:
            logger.info("Adding uca_result column...")
            cursor.execute("""
                ALTER TABLE articles 
                ADD COLUMN uca_result TEXT
            """)
            
        if 'uca_processed_at' not in columns:
            logger.info("Adding uca_processed_at column...")
            cursor.execute("""
                ALTER TABLE articles 
                ADD COLUMN uca_processed_at TIMESTAMP
            """)
        
        conn.commit()
        logger.info("✅ Migration completed successfully!")
        
        # Show stats
        cursor.execute("SELECT COUNT(*) FROM articles WHERE status='processed' AND uca_status IS NULL")
        pending_count = cursor.fetchone()[0]
        logger.info(f"📊 Articles ready for UCA processing: {pending_count}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    migrate()
