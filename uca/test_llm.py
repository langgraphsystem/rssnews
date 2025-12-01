import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uca.llm_client import LLMClient
from uca.modules.trend_analyzer import TrendAnalyzer
from pydantic import BaseModel

class TestModel(BaseModel):
    message: str
    sentiment: str

def test_connection():
    print("Testing LLM Connection...")
    # Use environment variable for API key
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        return
    
    # Test 1: Direct Client
    client = LLMClient(api_key=key)
    try:
        response = client.generate_structured(
            system_prompt="You are a test bot.",
            user_prompt="Say hello.",
            response_model=TestModel
        )
        print(f"Client Success! {response.message}")
    except Exception as e:
        print(f"Client Failed: {e}")
        
    # Test 2: Trend Analyzer
    print("Testing TrendAnalyzer...")
    analyzer = TrendAnalyzer()
    # Inject key manually since env might be broken
    analyzer.llm = LLMClient(api_key=key)
    
    try:
        analysis = analyzer.analyze("Bitcoin hits $100k! Everyone is going crazy.", search_volume_delta=5000)
        print(f"Analyzer Success! Emotion: {analysis.dominant_emotions[0]}")
    except Exception as e:
        print(f"Analyzer Failed: {e}")

if __name__ == "__main__":
    test_connection()
