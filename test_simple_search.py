#!/usr/bin/env python3
"""Test SimpleSearchService"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from services.simple_search_service import SimpleSearchService

async def test_simple_search():
    print("=" * 80)
    print("🔍 Testing SimpleSearchService")
    print("=" * 80)
    print()

    search_service = SimpleSearchService()

    queries = [
        "Trump election",
        "Arizona shooting",
        "Biden politics"
    ]

    for query in queries:
        print(f"Query: '{query}'")
        print("-" * 80)

        results = await search_service.search(query, limit=3)

        if results:
            print(f"✅ Found {len(results)} results\n")
            for i, r in enumerate(results, 1):
                print(f"{i}. [{r.similarity:.4f}] {r.title[:60]}")
                print(f"   {r.source} | {r.published_at[:10]}")
            print()

            # Test telegram formatting
            print("📱 Telegram Format:")
            telegram_msg = search_service.format_results_for_telegram(results, query, max_results=2)
            print(telegram_msg)
        else:
            print("❌ No results")

        print()

    print("=" * 80)
    print("✅ SimpleSearchService test complete!")

if __name__ == "__main__":
    asyncio.run(test_simple_search())
