#!/usr/bin/env python3
"""
Trace /analyze command execution path
Shows: Bot → Orchestrator → Retrieval → Database → Scoring → Response
"""

import os
import sys
import asyncio
import psycopg2
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 80)
print("TRACING /analyze COMMAND EXECUTION PATH")
print("=" * 80)

# ============================================================================
# STEP 1: Check bot handler
# ============================================================================
print("\n📱 STEP 1: BOT HANDLER")
print("-" * 80)

from bot_service.advanced_bot import AdvancedBot
import inspect

bot_handler = AdvancedBot.handle_analyze_command
source = inspect.getsource(bot_handler)
lines = source.split('\n')[:30]  # First 30 lines
print("Bot handler: AdvancedBot.handle_analyze_command")
print("Location: bot_service/advanced_bot.py")
print("\nKey code:")
for line in lines:
    if 'orchestrator' in line.lower() or 'analyze' in line.lower():
        print(f"  {line.strip()}")

# ============================================================================
# STEP 2: Check orchestrator service
# ============================================================================
print("\n\n🎯 STEP 2: ORCHESTRATOR SERVICE")
print("-" * 80)

try:
    from services.orchestrator import OrchestratorService

    orch_source = inspect.getsource(OrchestratorService.execute_analyze)
    orch_lines = orch_source.split('\n')[:20]
    print("Orchestrator: OrchestratorService.execute_analyze")
    print("Location: services/orchestrator.py")
    print("\nKey code:")
    for line in orch_lines:
        if 'keywords' in line.lower() or 'semantic' in line.lower() or 'orchestrator' in line.lower():
            print(f"  {line.strip()}")
except ImportError as e:
    print(f"⚠️ Could not import OrchestratorService: {e}")

# ============================================================================
# STEP 3: Check core orchestrator
# ============================================================================
print("\n\n🔄 STEP 3: CORE PHASE 4 ORCHESTRATOR")
print("-" * 80)

try:
    from core.orchestrator.phase4_orchestrator import create_phase4_orchestrator
    print("Core orchestrator: create_phase4_orchestrator")
    print("Location: core/orchestrator/phase4_orchestrator.py")
    print("Nodes: retrieval_node → analysis_node → formatting_node → validation_node")
except ImportError as e:
    print(f"⚠️ Could not import orchestrator: {e}")

# ============================================================================
# STEP 4: Check retrieval client
# ============================================================================
print("\n\n🔍 STEP 4: RETRIEVAL CLIENT")
print("-" * 80)

from core.rag.retrieval_client import RetrievalClient
print("Retrieval: RetrievalClient.retrieve")
print("Location: core/rag/retrieval_client.py")
print("Calls: ranking_api.retrieve_for_analysis()")

# ============================================================================
# STEP 5: Check RankingAPI
# ============================================================================
print("\n\n📊 STEP 5: RANKING API")
print("-" * 80)

from ranking_api import RankingAPI
print("RankingAPI: retrieve_for_analysis method")
print("Location: ranking_api.py")

ranking_source = inspect.getsource(RankingAPI.retrieve_for_analysis)
ranking_lines = [line for line in ranking_source.split('\n') if 'search_with_time_filter' in line or 'get_recent_articles' in line]
print("\nKey methods called:")
for line in ranking_lines:
    print(f"  {line.strip()}")

# ============================================================================
# STEP 6: Check database client
# ============================================================================
print("\n\n💾 STEP 6: DATABASE CLIENT")
print("-" * 80)

from database.production_db_client import ProductionDBClient
print("Database: ProductionDBClient")
print("Location: database/production_db_client.py")
print("\nMethods:")
print("  - search_with_time_filter(query_embedding, hours, filters)")
print("  - get_recent_articles(hours, filters)")

# ============================================================================
# STEP 7: Verify database schema
# ============================================================================
print("\n\n🗄️  STEP 7: DATABASE SCHEMA VERIFICATION")
print("-" * 80)

dsn = os.getenv('PG_DSN')
if not dsn:
    print("❌ PG_DSN not set")
else:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    # Check article_chunks table
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'article_chunks'
        ORDER BY ordinal_position
    """)
    columns = cur.fetchall()

    print("\n📋 article_chunks table columns:")
    key_columns = ['id', 'article_id', 'text', 'url', 'title_norm', 'source_domain',
                   'published_at', 'embedding_vector']
    for col_name, col_type in columns:
        if col_name in key_columns:
            print(f"  ✅ {col_name}: {col_type}")

    # Check data counts
    print("\n📊 Data statistics:")

    cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL")
    total = cur.fetchone()[0]
    print(f"  Total chunks with embeddings: {total:,}")

    cur.execute("""
        SELECT COUNT(*) FROM article_chunks
        WHERE embedding_vector IS NOT NULL
          AND published_at >= NOW() - INTERVAL '24 hours'
    """)
    recent = cur.fetchone()[0]
    print(f"  Recent chunks (24h): {recent:,}")

    # Check indexes
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'article_chunks'
    """)
    indexes = cur.fetchall()

    print("\n🔑 Indexes on article_chunks:")
    for idx_name, idx_def in indexes:
        if 'embedding' in idx_name:
            print(f"  ✅ {idx_name}")
            print(f"     {idx_def[:100]}...")

    conn.close()

# ============================================================================
# STEP 8: Test actual query execution
# ============================================================================
print("\n\n🧪 STEP 8: TEST ACTUAL QUERY EXECUTION")
print("-" * 80)

async def test_query():
    from openai_embedding_generator import OpenAIEmbeddingGenerator

    # Generate embedding for "trump"
    gen = OpenAIEmbeddingGenerator()
    embeddings = await gen.generate_embeddings(["trump"])

    if not embeddings or not embeddings[0]:
        print("❌ Failed to generate embedding")
        return

    query_embedding = embeddings[0]
    print(f"✅ Generated {len(query_embedding)}-dim embedding for 'trump'")

    # Call database directly
    conn = psycopg2.connect(os.getenv('PG_DSN'))
    cur = conn.cursor()

    vector_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

    cur.execute("""
        SELECT COUNT(*)
        FROM article_chunks ac
        WHERE ac.embedding_vector IS NOT NULL
          AND ac.published_at >= NOW() - INTERVAL '24 hours'
    """)
    count_24h = cur.fetchone()[0]
    print(f"✅ Chunks in last 24h: {count_24h:,}")

    # Test semantic search
    cur.execute("""
        SELECT ac.id, ac.title_norm,
               1 - (ac.embedding_vector <=> %s::vector) AS similarity
        FROM article_chunks ac
        WHERE ac.embedding_vector IS NOT NULL
          AND ac.published_at >= NOW() - INTERVAL '24 hours'
        ORDER BY ac.embedding_vector <=> %s::vector
        LIMIT 5
    """, (vector_str, vector_str))

    results = cur.fetchall()
    print(f"✅ Semantic search results: {len(results)}")

    if results:
        print("\nTop 3 Trump-related articles:")
        for i, (chunk_id, title, sim) in enumerate(results[:3], 1):
            print(f"  {i}. {title[:70]}... (sim: {sim:.3f})")

    conn.close()

    # Now test through RankingAPI
    print("\n" + "-" * 80)
    print("Testing through RankingAPI.retrieve_for_analysis:")

    api = RankingAPI()
    docs = await api.retrieve_for_analysis(
        query="trump",
        window="24h",
        k_final=5
    )

    print(f"✅ RankingAPI returned: {len(docs)} documents")

    if docs:
        print("\nTop 3 from RankingAPI:")
        for i, doc in enumerate(docs[:3], 1):
            title = doc.get('title_norm', 'No title')[:70]
            score = doc.get('final_score', doc.get('similarity', 0))
            print(f"  {i}. {title}... (score: {score:.3f})")
    else:
        print("❌ RankingAPI returned 0 documents - investigating...")

        # Debug: check if error was logged
        import logging
        logger = logging.getLogger('ranking_api')
        if logger.handlers:
            print("Logger is configured, check logs above for errors")

asyncio.run(test_query())

# ============================================================================
# SUMMARY
# ============================================================================
print("\n\n" + "=" * 80)
print("📋 EXECUTION PATH SUMMARY")
print("=" * 80)
print("""
1. Telegram message → bot_service/advanced_bot.py::handle_analyze_command
2. Extract query, window → services/orchestrator.py::execute_analyze
3. Orchestrator → core/orchestrator/phase4_orchestrator.py (LangGraph)
4. Retrieval node → core/rag/retrieval_client.py::retrieve
5. Retrieval client → ranking_api.py::retrieve_for_analysis
6. RankingAPI:
   - Generates embedding (OpenAI text-embedding-3-large, 3072-dim)
   - Calls database/production_db_client.py::search_with_time_filter
7. Database query:
   - Table: article_chunks
   - Filter: embedding_vector IS NOT NULL AND published_at >= NOW() - '24 hours'
   - Search: pgvector <=> operator (cosine distance)
   - Index: HNSW index on embedding_vector
8. Scoring → ranking_service/scorer.py::score_and_rank
9. Deduplication → ranking_service/deduplication.py::canonicalize_articles
10. Return to orchestrator → Claude Sonnet 4 analysis → Format → Validate → Send to user
""")

print("\n✅ Trace complete!")
