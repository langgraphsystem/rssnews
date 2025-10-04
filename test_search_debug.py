#!/usr/bin/env python3
"""Debug search with detailed logging"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')

from ranking_api import RankingAPI, SearchRequest

async def debug_search():
    print("=" * 80)
    print("🐛 DEBUG: Search Test with Full Logging")
    print("=" * 80)
    print()

    # Initialize ranking API
    print("🔧 Initializing Ranking API...")
    ranking = RankingAPI()
    print("✅ Ranking API initialized")
    print()

    # Test single query
    query = "Trump election"
    print(f"🔍 Testing query: '{query}'")
    print()

    try:
        search_request = SearchRequest(query=query, limit=5, method='semantic')
        print(f"📝 SearchRequest created: {search_request}")
        print()

        print("🚀 Calling ranking.search()...")
        search_response = await ranking.search(search_request)

        print(f"✅ Response received: {search_response}")
        print()

        if hasattr(search_response, 'chunks'):
            print(f"📊 Chunks count: {len(search_response.chunks)}")
            for i, chunk in enumerate(search_response.chunks[:3]):
                print(f"  {i+1}. {chunk.get('title_norm', 'No title')[:50]}")
        elif hasattr(search_response, 'results'):
            print(f"📊 Results count: {len(search_response.results)}")
            for i, result in enumerate(search_response.results[:3]):
                print(f"  {i+1}. {result.get('title_norm', 'No title')[:50]}")
        else:
            print(f"⚠️ Response attributes: {dir(search_response)}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_search())
