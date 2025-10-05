#!/usr/bin/env python3
"""Test retrieve_for_analysis method directly"""

import os
import sys
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

from ranking_api import RankingAPI

async def main():
    print("Testing retrieve_for_analysis method...")

    # Create RankingAPI instance
    api = RankingAPI()
    print("✅ RankingAPI initialized")

    # Test with query
    print("\nTest 1: retrieve_for_analysis with query='trump', window='24h'")
    results = await api.retrieve_for_analysis(
        query="trump",
        window="24h",
        k_final=5
    )

    print(f"Results: {len(results)} documents")
    if results:
        print("\nTop 3 results:")
        for i, doc in enumerate(results[:3], 1):
            title = doc.get('title_norm', doc.get('title', 'No title'))[:60]
            score = doc.get('final_score', doc.get('similarity', 0))
            print(f"{i}. {title}... (score: {score:.3f})")
    else:
        print("⚠️ No results returned")

    # Test without query (trends)
    print("\nTest 2: retrieve_for_analysis without query (trends), window='24h'")
    results2 = await api.retrieve_for_analysis(
        query=None,
        window="24h",
        k_final=10
    )

    print(f"Results: {len(results2)} documents")
    if results2:
        print("\nTop 3 results:")
        for i, doc in enumerate(results2[:3], 1):
            title = doc.get('title_norm', doc.get('title', 'No title'))[:60]
            score = doc.get('final_score', doc.get('semantic_score', 0))
            print(f"{i}. {title}... (score: {score:.3f})")
    else:
        print("⚠️ No results returned")

if __name__ == "__main__":
    asyncio.run(main())
