#!/usr/bin/env python3
"""
Test basic bot commands that don't require embeddings
Directly test bot logic without Telegram API
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()


async def test_db_stats():
    """Test database statistics command"""
    print("=" * 80)
    print("🧪 Testing: /db_stats command")
    print("=" * 80)

    from database.production_db_client import ProductionDBClient

    try:
        db = ProductionDBClient()
        print("✅ Database client initialized")

        # Get statistics
        with db._cursor() as cur:
            # Total articles
            cur.execute("SELECT COUNT(*) FROM rss_items")
            total_articles = cur.fetchone()[0]

            # Total chunks
            cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
            total_chunks = cur.fetchone()[0]

            # Embedding dimension
            cur.execute("SELECT array_length(embedding, 1) FROM chunks WHERE embedding IS NOT NULL LIMIT 1")
            embedding_dim = cur.fetchone()[0] if cur.rowcount > 0 else 0

            # Recent articles
            cur.execute("""
                SELECT COUNT(*) FROM rss_items
                WHERE published_date >= NOW() - INTERVAL '7 days'
            """)
            recent_articles = cur.fetchone()[0]

            # Database size
            cur.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """)
            db_size = cur.fetchone()[0]

        print()
        print("📊 Database Statistics:")
        print(f"  Total articles: {total_articles:,}")
        print(f"  Total chunks: {total_chunks:,}")
        print(f"  Embedding dimension: {embedding_dim}")
        print(f"  Recent articles (7d): {recent_articles:,}")
        print(f"  Database size: {db_size}")
        print()
        print("✅ DB Stats command would work correctly")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_db_tables():
    """Test database tables command"""
    print("=" * 80)
    print("🧪 Testing: /db_tables command")
    print("=" * 80)

    from database.production_db_client import ProductionDBClient

    try:
        db = ProductionDBClient()

        with db._cursor() as cur:
            cur.execute("""
                SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 10
            """)

            print()
            print("📋 Top 10 Tables:")
            for table_name, size in cur.fetchall():
                print(f"  {table_name}: {size}")

        print()
        print("✅ DB Tables command would work correctly")
        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_config_table():
    """Test config table access"""
    print("=" * 80)
    print("🧪 Testing: Config table access")
    print("=" * 80)

    from database.production_db_client import ProductionDBClient

    try:
        db = ProductionDBClient()

        with db._cursor() as cur:
            cur.execute("SELECT config_key, config_value, config_type FROM config ORDER BY config_key")
            configs = cur.fetchall()

        print()
        print(f"📋 Config entries: {len(configs)}")
        for key, value, type_ in configs:
            print(f"  {key}: {value} ({type_})")

        print()
        print("✅ Config table working correctly")
        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_recent_articles():
    """Test recent articles retrieval"""
    print("=" * 80)
    print("🧪 Testing: Recent articles retrieval")
    print("=" * 80)

    from database.production_db_client import ProductionDBClient

    try:
        db = ProductionDBClient()

        with db._cursor() as cur:
            cur.execute("""
                SELECT title, source_name, published_date
                FROM rss_items
                ORDER BY published_date DESC
                LIMIT 10
            """)
            articles = cur.fetchall()

        print()
        print(f"📰 Latest 10 articles:")
        for title, source, pub_date in articles:
            title_short = title[:70] + "..." if len(title) > 70 else title
            print(f"  [{pub_date}] {title_short}")
            print(f"     Source: {source}")

        print()
        print("✅ Recent articles retrieval working")
        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all basic tests"""
    print("🤖 RSS News Bot - Basic Command Testing")
    print("(No embeddings required)")
    print()

    tests = [
        ("Database Statistics", test_db_stats),
        ("Database Tables", test_db_tables),
        ("Config Table", test_config_table),
        ("Recent Articles", test_recent_articles),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ Test {name} crashed: {e}")
            results.append((name, False))
        print()

    # Summary
    print("=" * 80)
    print("📊 Test Summary")
    print("=" * 80)
    successful = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")

    print()
    print(f"Success rate: {successful}/{total} ({successful/total*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
