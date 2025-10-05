"""
Debug /ask command to see what data is returned
"""
import asyncio
from ranking_api import RankingAPI

async def debug_ask():
    """Debug /ask command retrieval"""

    api = RankingAPI()

    print("Testing TikTok retrieval with debug info...")
    print("=" * 70)

    results = await api.retrieve_for_analysis(
        query="TikTok divestiture",
        window="1m",
        lang="auto",
        k_final=3
    )

    print(f"\nFound {len(results)} results\n")

    for i, doc in enumerate(results, 1):
        print(f"Document {i}:")
        print(f"  Keys: {list(doc.keys())}")
        print(f"  article_id: {doc.get('article_id', 'N/A')}")
        print(f"  title: {doc.get('title', doc.get('title_norm', 'N/A'))[:70]}")
        print(f"  url: {doc.get('url', 'N/A')[:50]}")
        print(f"  date: {doc.get('date', doc.get('published_at', 'N/A'))}")
        print(f"  score: {doc.get('score', doc.get('similarity', 0))}")
        print(f"  text: {doc.get('text', doc.get('snippet', 'N/A'))[:100]}...")
        print()

if __name__ == "__main__":
    asyncio.run(debug_ask())
