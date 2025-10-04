#!/usr/bin/env python3
"""
Direct Search Test - No Telegram required
Tests search functionality directly via ranking API
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ranking_api import RankingAPI, SearchRequest
from openai_embedding_generator import OpenAIEmbeddingGenerator


async def test_search_direct():
    """Test search without Telegram bot"""

    print("=" * 80)
    print("🔍 Direct Search Test (No Telegram)")
    print("=" * 80)
    print()

    # Initialize ranking API
    print("🔧 Initializing Ranking API...")
    ranking = RankingAPI()
    print("✅ Ranking API ready")
    print()

    # Test queries
    queries = [
        "Trump election news",
        "Arizona shooting",
        "Biden politics",
        "latest technology news"
    ]

    results_summary = []

    for query in queries:
        print(f"🔍 Testing query: '{query}'")
        print("-" * 80)

        try:
            # Perform search
            search_request = SearchRequest(query=query, limit=5)
            search_response = await ranking.search(search_request)
            results = search_response.chunks if hasattr(search_response, 'chunks') else []

            if results and len(results) > 0:
                print(f"✅ Found {len(results)} results")
                print()
                print("📰 Top Results:")
                for i, result in enumerate(results[:3], 1):
                    title = result.get('title_norm', 'No title')[:70]
                    source = result.get('source_domain', 'unknown')
                    score = result.get('score', 0)
                    print(f"  {i}. [{score:.3f}] {title}... ({source})")

                results_summary.append({
                    'query': query,
                    'status': 'passed',
                    'count': len(results)
                })
            else:
                print("❌ No results found")
                results_summary.append({
                    'query': query,
                    'status': 'failed',
                    'count': 0
                })

        except Exception as e:
            print(f"❌ Search failed: {e}")
            results_summary.append({
                'query': query,
                'status': 'error',
                'error': str(e)
            })

        print()

    # Print summary
    print("=" * 80)
    print("📊 SEARCH TEST SUMMARY")
    print("=" * 80)
    total = len(results_summary)
    passed = sum(1 for r in results_summary if r['status'] == 'passed')
    failed = sum(1 for r in results_summary if r['status'] != 'passed')

    print(f"Total queries: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print()

    for result in results_summary:
        status_emoji = '✅' if result['status'] == 'passed' else '❌'
        count_info = f"({result.get('count', 0)} results)" if result['status'] == 'passed' else ''
        print(f"{status_emoji} {result['query']} {count_info}")

    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_search_direct())
    sys.exit(0 if success else 1)
