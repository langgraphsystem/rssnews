"""
UCA Batch Processor - Process all articles using local Ollama model
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_storage import LocalStorageClient
from uca.core import UCAEngine
from uca.constants import AgentMode
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("uca_batch_processing.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class UCABatchProcessor:
    def __init__(self):
        # Use local storage from config
        import config
        cfg = config.load_config()
        self.storage = LocalStorageClient(cfg['sqlite_db_path'], cfg['chroma_db_path'])
        
        # Initialize UCA Engine with local model
        self.uca = UCAEngine(mode=AgentMode.STORE_OWNER)
        
    def process_all(self, batch_size=10, max_articles=None):
        """
        Process all articles that need UCA analysis.
        
        Args:
            batch_size: Number of articles to fetch at once
            max_articles: Maximum number of articles to process (None = all)
        """
        logger.info("=" * 80)
        logger.info("🚀 Starting UCA Batch Processing")
        logger.info("=" * 80)
        
        total_processed = 0
        total_errors = 0
        
        while True:
            # Check if we've hit the limit
            if max_articles and total_processed >= max_articles:
                logger.info(f"Reached maximum article limit: {max_articles}")
                break
            
            # Get next batch
            articles = self.storage.get_articles_for_uca(limit=batch_size)
            
            if not articles:
                logger.info("✅ No more articles to process!")
                break
            
            logger.info(f"\n📦 Processing batch of {len(articles)} articles...")
            
            for article in articles:
                try:
                    self._process_single_article(article)
                    total_processed += 1
                    
                    # Log progress every 10 articles
                    if total_processed % 10 == 0:
                        logger.info(f"📊 Progress: {total_processed} articles processed, {total_errors} errors")
                        
                except Exception as e:
                    logger.error(f"❌ Failed to process article {article['id']}: {e}")
                    # Mark as error in DB
                    try:
                        self.storage.update_uca_result(
                            article['id'], 
                            {"error": str(e)}, 
                            status='uca_error'
                        )
                    except:
                        pass
                    total_errors += 1
                    continue
        
        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("🎉 BATCH PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"✅ Successfully processed: {total_processed}")
        logger.info(f"❌ Errors: {total_errors}")
        logger.info(f"📊 Success rate: {(total_processed / (total_processed + total_errors) * 100) if (total_processed + total_errors) > 0 else 0:.1f}%")
        logger.info("=" * 80)
        
        return total_processed, total_errors
    
    def _process_single_article(self, article):
        """Process a single article through UCA pipeline"""
        article_id = article['id']
        content = article.get('content', '')
        title = article.get('title', '')
        url = article.get('url', '')
        
        if not content or len(content) < 100:
            logger.warning(f"Article {article_id} has insufficient content, skipping")
            self.storage.update_uca_result(
                article_id,
                {"error": "Insufficient content"},
                status='uca_error'
            )
            return
        
        logger.info(f"Processing article {article_id}: {title[:50]}...")
        
        # Run UCA pipeline
        start_time = datetime.now()
        result = self.uca.process_news_event(content, source_id=str(article_id))
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Save result to database
        self.storage.update_uca_result(article_id, result, status='uca_processed')
        
        logger.info(f"✅ Article {article_id} processed successfully in {elapsed:.1f}s")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='UCA Batch Processor')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for fetching articles')
    parser.add_argument('--limit', type=int, default=None, help='Maximum number of articles to process')
    
    args = parser.parse_args()
    
    processor = UCABatchProcessor()
    processor.process_all(batch_size=args.batch_size, max_articles=args.limit)


if __name__ == "__main__":
    main()
