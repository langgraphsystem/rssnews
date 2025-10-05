#!/usr/bin/env python3
"""Debug /analyze on Railway - check if LSH fix is applied"""

import os
import sys
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 80)
print("🔍 DEBUGGING /analyze ON RAILWAY")
print("=" * 80)

# Check if LSH fix is in the code
print("\n1️⃣ Checking if LSH fix is in deduplication.py...")

with open('ranking_service/deduplication.py', 'r', encoding='utf-8') as f:
    content = f.read()
    if 'Reset LSH for each deduplication session' in content:
        print("✅ LSH fix IS present in code")
    else:
        print("❌ LSH fix NOT present in code")

# Check Git commit
print("\n2️⃣ Checking Git commit...")
import subprocess
result = subprocess.run(['git', 'log', '--oneline', '-1'], capture_output=True, text=True)
print(f"Latest commit: {result.stdout.strip()}")

# Test RankingAPI directly
print("\n3️⃣ Testing RankingAPI.retrieve_for_analysis...")

async def test_ranking_api():
    from ranking_api import RankingAPI

    api = RankingAPI()

    try:
        results = await api.retrieve_for_analysis(
            query="trump",
            window="24h",
            k_final=5
        )

        print(f"✅ RankingAPI returned: {len(results)} documents")

        if results:
            print("\nTop 3 results:")
            for i, doc in enumerate(results[:3], 1):
                title = doc.get('title_norm', 'No title')[:60]
                score = doc.get('final_score', doc.get('similarity', 0))
                print(f"  {i}. [{score:.3f}] {title}...")
        else:
            print("❌ RankingAPI returned 0 documents")

        return results

    except Exception as e:
        print(f"❌ ERROR in RankingAPI: {e}")
        import traceback
        traceback.print_exc()
        return []

results = asyncio.run(test_ranking_api())

# Test RetrievalClient (used by orchestrator)
print("\n4️⃣ Testing RetrievalClient (used by orchestrator)...")

async def test_retrieval_client():
    from core.rag.retrieval_client import get_retrieval_client

    client = get_retrieval_client()

    try:
        results = await client.retrieve(
            query="trump",
            window="24h",
            k_final=5
        )

        print(f"✅ RetrievalClient returned: {len(results)} documents")

        if results:
            print("\nTop 3 results:")
            for i, doc in enumerate(results[:3], 1):
                title = doc.get('title_norm', 'No title')[:60]
                score = doc.get('final_score', doc.get('similarity', 0))
                print(f"  {i}. [{score:.3f}] {title}...")
        else:
            print("❌ RetrievalClient returned 0 documents")

        return results

    except Exception as e:
        print(f"❌ ERROR in RetrievalClient: {e}")
        import traceback
        traceback.print_exc()
        return []

retrieval_results = asyncio.run(test_retrieval_client())

# Summary
print("\n" + "=" * 80)
print("📊 SUMMARY")
print("=" * 80)

if len(results) > 0:
    print("✅ RankingAPI works correctly")
else:
    print("❌ RankingAPI still fails")

if len(retrieval_results) > 0:
    print("✅ RetrievalClient works correctly")
    print("\n🎉 /analyze should work in bot now!")
else:
    print("❌ RetrievalClient still fails")
    print("\n⚠️ /analyze will still fail in bot")

print("\n" + "=" * 80)
