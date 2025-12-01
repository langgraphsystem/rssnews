import json
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uca.core import UCAEngine
from uca.constants import AgentMode
import logging

# Configure logging to see errors
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_on_real_data():
    print("🔌 Connecting to Database and fetching news...")
    
    uca = UCAEngine(mode=AgentMode.STORE_OWNER)
    
    # Process last 3 articles for a real test
    results = uca.process_recent_news(limit=3)
    
    if not results:
        print("⚠️ No articles found in DB (or DB is empty/locked).")
        return

    # Save full results to JSON file
    output_file = "uca_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Processed {len(results)} articles. Results saved to {output_file}\n")
    
    for i, res in enumerate(results):
        orig = res['original_article']
        trend = res['trend_analysis']
        products = res['commercial_opportunities']
        
        print(f"--- Article {i+1}: {orig['title']} ---")
        print(f"   ID: {orig['id']}")
        print(f"   Emotion: {trend['dominant_emotions'][0]}")
        print(f"   Velocity: {trend['velocity_score']}")
        print(f"   Products Generated: {len(products)}")
        
        for p in products:
            print(f"    > [{p['category_id']}] {p['product_title']}")
            
        print("")

if __name__ == "__main__":
    run_on_real_data()
