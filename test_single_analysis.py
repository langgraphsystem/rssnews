import asyncio
import logging
import json
import config
from uca.modules.deep_analyzer import DeepAnalyzer
from analysis_storage import AnalysisStorage

# Configure logging to console only
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def test_single():
    cfg = config.load_config()
    storage = AnalysisStorage(cfg['analysis_db_path'])
    analyzer = DeepAnalyzer()
    
    print("🧪 Fetching one pending article for test...")
    articles = storage.get_pending_analysis(limit=1)
    
    if not articles:
        print("❌ No pending articles found in Analysis DB.")
        return

    article = articles[0]
    print(f"📄 Article ID: {article['id']}")
    print(f"Title: {article['title']}")
    print(f"Content Length: {len(article['content'])} chars")
    print("-" * 50)
    print("🤖 Sending to LLM (llama3.1:8b)...")
    
    try:
        # Run analysis
        result = analyzer.analyze(article['content'])
        
        print("\n✅ Analysis Result:")
        print("-" * 50)
        # Pretty print JSON
        print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
        print("-" * 50)
        print("NOTE: This was a test run. The result was NOT saved to DB.")
        
    except Exception as e:
        print(f"❌ Analysis Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_single())
