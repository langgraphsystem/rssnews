"""
Test TikTok article retrieval to diagnose /ask command issue
"""
import asyncio
import sys
from pg_client_new import PgClient
from ranking_api import RankingAPI

async def test_tiktok_retrieval():
    """Test retrieval for TikTok articles"""

    print("=" * 70)
    print("Testing TikTok Article Retrieval")
    print("=" * 70)

    db = PgClient()

    # Test 1: Check if TikTok articles exist in database
    print("\n1. Checking TikTok articles in database...")
    with db._cursor() as cur:
        # Check articles_index table
        cur.execute("""
            SELECT COUNT(*)
            FROM articles_index
            WHERE
                LOWER(title_norm) LIKE '%tiktok%'
                OR LOWER(clean_text) LIKE '%tiktok%'
        """)
        tiktok_count = cur.fetchone()[0]
        print(f"   Articles mentioning TikTok: {tiktok_count:,}")

        if tiktok_count > 0:
            cur.execute("""
                SELECT
                    title_norm,
                    published_at,
                    source
                FROM articles_index
                WHERE LOWER(title_norm) LIKE '%tiktok%'
                ORDER BY published_at DESC
                LIMIT 5
            """)

            print("\n   Sample TikTok articles:")
            for i, (title, pub, source) in enumerate(cur.fetchall(), 1):
                print(f"   {i}. {title[:70]}")
                print(f"      {pub} | {source}")

    # Test 2: Check embeddings for TikTok content
    print("\n2. Checking embeddings...")
    with db._cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT ac.article_id)
            FROM article_chunks ac
            WHERE
                LOWER(ac.text) LIKE '%tiktok%'
                AND ac.embedding_vector IS NOT NULL
        """)
        emb_count = cur.fetchone()[0]
        print(f"   TikTok chunks with embeddings: {emb_count:,}")

        # Check total embeddings
        cur.execute("""
            SELECT
                COUNT(*) as total_chunks,
                COUNT(embedding_vector) as with_embeddings,
                ROUND(100.0 * COUNT(embedding_vector) / COUNT(*), 2) as pct
            FROM article_chunks
        """)
        total, with_emb, pct = cur.fetchone()
        print(f"   Total chunks: {total:,}")
        print(f"   With embeddings: {with_emb:,} ({pct}%)")

    # Test 3: Test RankingAPI.retrieve_for_analysis()
    print("\n3. Testing RankingAPI.retrieve_for_analysis()...")
    api = RankingAPI()

    try:
        results = await api.retrieve_for_analysis(
            query="TikTok",
            window="3m",  # 3 months
            lang="auto",
            k_final=5
        )

        print(f"   Results found: {len(results)}")

        if results:
            print("\n   Retrieved articles:")
            for i, doc in enumerate(results, 1):
                title = doc.get('title', 'N/A')
                date = doc.get('date', 'N/A')
                score = doc.get('score', 0)
                print(f"   {i}. {title[:60]}")
                print(f"      Date: {date} | Score: {score:.3f}")
        else:
            print("   ❌ No results returned!")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 4: Test with "TikTok divestiture"
    print("\n4. Testing with query 'TikTok divestiture'...")

    try:
        results2 = await api.retrieve_for_analysis(
            query="TikTok divestiture",
            window="3m",
            lang="auto",
            k_final=5
        )

        print(f"   Results found: {len(results2)}")

        if results2:
            print("\n   Retrieved articles:")
            for i, doc in enumerate(results2, 1):
                title = doc.get('title', 'N/A')
                date = doc.get('date', 'N/A')
                score = doc.get('score', 0)
                print(f"   {i}. {title[:60]}")
                print(f"      Date: {date} | Score: {score:.3f}")
        else:
            print("   ❌ No results for 'TikTok divestiture'!")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 5: Test embedding generation
    print("\n5. Testing query embedding generation...")
    from local_embedding_generator import LocalEmbeddingGenerator

    try:
        emb_gen = LocalEmbeddingGenerator()
        embeddings = await emb_gen.generate_embeddings(["TikTok divestiture"])

        if embeddings and embeddings[0]:
            print(f"   ✅ Embedding generated: {len(embeddings[0])} dimensions")
        else:
            print("   ❌ Failed to generate embedding!")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n" + "=" * 70)
    print("Test complete")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_tiktok_retrieval())
