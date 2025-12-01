import json
import sys
import os

# Add parent directory to path so we can import uca
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uca.core import UCAEngine
from uca.constants import AgentMode

def run_solar_flare_simulation():
    print("☀️ Running Solar Flare Simulation...")
    
    # 1. Initialize Engine
    uca = UCAEngine(mode=AgentMode.STORE_OWNER)
    
    # 2. Simulate News Input
    # Scenario: NASA warns of solar flare disrupting internet
    news_text = """
    NASA has issued a warning about a massive X-class solar flare expected to hit Earth in 48 hours. 
    Scientists predict potential disruptions to global internet infrastructure and GPS systems lasting up to 24 hours. 
    Experts advise citizens to prepare for a temporary digital blackout. 
    Panic is starting to spread on social media as people worry about connectivity.
    """
    
    print(f"\n📰 Input News: {news_text[:100]}...")
    
    # 3. Process
    print("DEBUG: Calling process_news_event...")
    result = uca.process_news_event(news_text, source_id="sim_001")
    print("DEBUG: process_news_event returned.")
    
    # 4. Output Result
    print("\n✅ Simulation Complete. Generated JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 5. Validation
    products = result['commercial_opportunities']
    print(f"\n📦 Generated {len(products)} products:")
    for p in products:
        print(f" - [{p['category_id']}] {p['product_title']}")
        print(f"   Prompt: {p['visual_prompt']['prompt'][:50]}...")

if __name__ == "__main__":
    run_solar_flare_simulation()
