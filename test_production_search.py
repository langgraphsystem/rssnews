#!/usr/bin/env python3
"""
Test SimpleSearchService on Railway production database
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Test queries that should work with real data
TEST_QUERIES = [
    "Trump election 2024",
    "artificial intelligence regulation",
    "climate change",
    "Ukraine war",
    "economy inflation",
]


async def main():
    print("=" * 80)
    print("🧪 Testing SimpleSearchService on Production")
    print("=" * 80)
    print()

    # Import after env is loaded
    from services.simple_search_service import SimpleSearchService

    try:
        print("🔧 Initializing SimpleSearchService...")
        search_service = SimpleSearchService()
        print("✅ Service initialized")
        print()

        for query in TEST_QUERIES:
            print("-" * 80)
            print(f"🔍 Query: {query}")
            print("-" * 80)

            try:
                results = await search_service.search(query, limit=5)

                if results:
                    print(f"✅ Found {len(results)} results")
                    print()

                    for i, result in enumerate(results, 1):
                        print(f"#{i} Score: {result.similarity:.2%}")
                        print(f"   Title: {result.title[:80]}")
                        print(f"   Source: {result.source}")
                        print(f"   Published: {result.published_at[:10]}")
                        print()

                    # Test Telegram formatting
                    telegram_msg = search_service.format_results_for_telegram(
                        results, query, max_results=3
                    )
                    print("📱 Telegram formatted message:")
                    print(telegram_msg[:500] + "..." if len(telegram_msg) > 500 else telegram_msg)
                else:
                    print("❌ No results found")

            except Exception as e:
                print(f"❌ Search failed: {e}")
                import traceback
                traceback.print_exc()

            print()

    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=" * 80)
    print("✅ Production search testing completed")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
