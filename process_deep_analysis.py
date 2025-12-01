import asyncio
import logging
import json
import sqlite3
from typing import List, Dict, Any
from datetime import datetime

from uca.modules.deep_analyzer import DeepAnalyzer
from local_storage import LocalStorageClient
from analysis_storage import AnalysisStorage
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("deep_analysis.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DeepAnalysisProcessor:
    def __init__(self):
        self.cfg = config.load_config()
        
        # Main DB (Source)
        self.main_storage = LocalStorageClient(
            self.cfg['sqlite_db_path'], 
            self.cfg['chroma_db_path']
        )
        
        # Analysis DB (Target)
        self.analysis_storage = AnalysisStorage(self.cfg['analysis_db_path'])
        
        self.analyzer = DeepAnalyzer()
        
    def sync_database(self):
        """
        Copy processed articles from Main DB to Analysis DB.
        Only copies articles that have full text (status='processed').
        """
        logger.info("🔄 Syncing databases...")
        
        # Get all processed articles from Main DB
        # We fetch in batches to avoid memory issues if DB is huge
        offset = 0
        batch_size = 100
        total_synced = 0
        
        while True:
            try:
                with sqlite3.connect(self.cfg['sqlite_db_path'], timeout=30.0) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT * FROM articles 
                        WHERE status = 'processed' 
                        ORDER BY id DESC
                        LIMIT ? OFFSET ?
                    """, (batch_size, offset))
                    rows = cursor.fetchall()
                    articles = [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Sync fetch failed: {e}")
                break
                
            if not articles:
                break
                
            for article in articles:
                if self.analysis_storage.sync_article(article):
                    total_synced += 1
            
            offset += batch_size
            
        if total_synced > 0:
            logger.info(f"✅ Synced {total_synced} new articles to Analysis DB")
        else:
            logger.info("✅ Database is up to date")
            
        stats = self.analysis_storage.get_stats()
        logger.info(f"📊 Analysis DB Stats: Total={stats.get('total')}, Pending={stats.get('pending')}")

    async def process_batch(self, batch_size: int = 5):
        """Process a batch of pending articles from Analysis DB"""
        
        articles = self.analysis_storage.get_pending_analysis(limit=batch_size)
        
        if not articles:
            logger.info("No pending articles for Deep Analysis.")
            return 0
            
        logger.info(f"🧠 Deep Analyzing batch of {len(articles)} articles...")
        
        processed_count = 0
        
        for article in articles:
            try:
                await self._process_single_article(article)
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed to analyze article {article['id']}: {e}")
                self.analysis_storage.update_analysis_result(article['id'], {}, status='error')
                
        return processed_count

    async def _process_single_article(self, article: Dict[str, Any]):
        """Run Deep Analysis on a single article"""
        article_id = article['id']
        title = article['title']
        content = article['content']
        
        logger.info(f"Analyzing {article_id}: {title[:50]}...")
        
        if not content or len(content) < 100:
            logger.warning(f"Skipping {article_id}: Content too short")
            self.analysis_storage.update_analysis_result(article_id, {}, status='skipped_short')
            return

        # Run LLM Analysis
        result = self.analyzer.analyze(content)
        
        if result:
            # Save to Analysis DB
            self.analysis_storage.update_analysis_result(
                article_id, 
                result.model_dump(), 
                status='processed'
            )
            logger.info(f"✅ Analysis saved for {article_id}")
        else:
            logger.error(f"❌ Analysis failed for {article_id}")
            self.analysis_storage.update_analysis_result(article_id, {}, status='failed')

async def main():
    processor = DeepAnalysisProcessor()
    
    # 1. Sync Data
    processor.sync_database()
    
    # 2. Process
    try:
        total_processed = 0
        while True:
            count = await processor.process_batch(batch_size=5)
            if count == 0:
                break
            total_processed += count
            logger.info(f"Total analyzed so far: {total_processed}")
            
        logger.info("🎉 All pending analysis completed!")
    finally:
        # Cleanup if needed
        pass

if __name__ == "__main__":
    asyncio.run(main())
