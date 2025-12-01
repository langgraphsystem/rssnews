"""
Test processing of a single article
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from process_articles import ArticleProcessor

async def test_one():
    processor = ArticleProcessor()
    
    try:
        # Get one pending article
        articles = processor.storage.get_pending_articles(limit=1)
        
        if not articles:
            print("❌ No pending articles found.")
            return
        
        article = articles[0]
        print(f"\n{'='*80}")
        print(f"🧪 TESTING ARTICLE PROCESSING")
        print(f"{'='*80}")
        print(f"ID: {article['id']}")
        print(f"Title: {article['title']}")
        print(f"URL: {article['url'][:70]}...")
        print(f"Current content length: {len(article['content'])} chars")
        print(f"{'='*80}\n")
        
        # Process it
        await processor._process_single_article(article)
        
        print(f"\n{'='*80}")
        print(f"✅ Processing complete!")
        print(f"{'='*80}\n")
        
    finally:
        await processor.close()

if __name__ == "__main__":
    asyncio.run(test_one())
