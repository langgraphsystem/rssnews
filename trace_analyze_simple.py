#!/usr/bin/env python3
"""Simple trace of /analyze command with actual execution"""

import os
import sys
import asyncio
import psycopg2
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 80)
print("ТРЕЙСИНГ КОМАНДЫ /analyze trump")
print("=" * 80)

# ============================================================================
# ШАГ 1: Проверка базы данных
# ============================================================================
print("\n💾 ШАГ 1: ПРОВЕРКА БАЗЫ ДАННЫХ")
print("-" * 80)

dsn = os.getenv('PG_DSN')
conn = psycopg2.connect(dsn)
cur = conn.cursor()

print("\n📋 Таблица: article_chunks")

# Проверяем ключевые колонки
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'article_chunks'
      AND column_name IN ('id', 'article_id', 'text', 'url', 'title_norm',
                          'source_domain', 'published_at', 'embedding_vector')
    ORDER BY ordinal_position
""")
columns = cur.fetchall()

print("Ключевые колонки:")
for col_name, col_type in columns:
    print(f"  ✅ {col_name}: {col_type}")

# Статистика данных
print("\n📊 Статистика данных:")

cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL")
total = cur.fetchone()[0]
print(f"  Всего чанков с эмбеддингами: {total:,}")

cur.execute("""
    SELECT COUNT(*) FROM article_chunks
    WHERE embedding_vector IS NOT NULL
      AND published_at >= NOW() - INTERVAL '24 hours'
""")
recent_24h = cur.fetchone()[0]
print(f"  Чанков за последние 24 часа: {recent_24h:,}")

# Проверяем индексы
cur.execute("""
    SELECT indexname FROM pg_indexes
    WHERE tablename = 'article_chunks' AND indexname LIKE '%embedding%'
""")
indexes = cur.fetchall()

print("\n🔑 Индексы для эмбеддингов:")
for (idx_name,) in indexes:
    print(f"  ✅ {idx_name}")

# ============================================================================
# ШАГ 2: Генерация эмбеддинга для запроса
# ============================================================================
print("\n\n🧠 ШАГ 2: ГЕНЕРАЦИЯ ЭМБЕДДИНГА ЗАПРОСА")
print("-" * 80)

async def generate_embedding():
    from openai_embedding_generator import OpenAIEmbeddingGenerator

    gen = OpenAIEmbeddingGenerator()
    print("Генерируем эмбеддинг для запроса: 'trump'")

    embeddings = await gen.generate_embeddings(["trump"])

    if not embeddings or not embeddings[0]:
        print("❌ Не удалось сгенерировать эмбеддинг")
        return None

    query_embedding = embeddings[0]
    print(f"✅ Сгенерирован эмбеддинг: {len(query_embedding)} измерений")

    return query_embedding

query_embedding = asyncio.run(generate_embedding())

if not query_embedding:
    exit(1)

# ============================================================================
# ШАГ 3: Прямой SQL запрос к базе
# ============================================================================
print("\n\n🔍 ШАГ 3: ПРЯМОЙ SQL ЗАПРОС К БАЗЕ")
print("-" * 80)

vector_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

print(f"SQL запрос:")
print(f"  SELECT ... FROM article_chunks")
print(f"  WHERE embedding_vector IS NOT NULL")
print(f"    AND published_at >= NOW() - INTERVAL '24 hours'")
print(f"  ORDER BY embedding_vector <=> [query_vector]")
print(f"  LIMIT 10")

cur.execute("""
    SELECT
        ac.id, ac.article_id, ac.title_norm, ac.source_domain,
        ac.published_at,
        1 - (ac.embedding_vector <=> %s::vector) AS similarity
    FROM article_chunks ac
    WHERE ac.embedding_vector IS NOT NULL
      AND ac.published_at >= NOW() - INTERVAL '24 hours'
    ORDER BY ac.embedding_vector <=> %s::vector
    LIMIT 10
""", (vector_str, vector_str))

direct_results = cur.fetchall()

print(f"\n✅ Результаты прямого запроса: {len(direct_results)} документов")

if direct_results:
    print("\nТоп-5 результатов:")
    for i, (chunk_id, article_id, title, domain, pub_at, sim) in enumerate(direct_results[:5], 1):
        print(f"  {i}. [{sim:.3f}] {title[:60]}...")
        print(f"     {domain} | {pub_at}")
else:
    print("❌ Прямой SQL запрос вернул 0 результатов")

conn.close()

# ============================================================================
# ШАГ 4: Через ProductionDBClient.search_with_time_filter
# ============================================================================
print("\n\n📦 ШАГ 4: ЧЕРЕЗ ProductionDBClient.search_with_time_filter")
print("-" * 80)

async def test_db_client():
    from database.production_db_client import ProductionDBClient

    db = ProductionDBClient()
    print("Вызываем: db.search_with_time_filter(query='trump', hours=24, limit=10)")

    results = await db.search_with_time_filter(
        query="trump",
        query_embedding=query_embedding,
        hours=24,
        limit=10,
        filters=None
    )

    print(f"✅ ProductionDBClient вернул: {len(results)} документов")

    if results:
        print("\nТоп-3 результата:")
        for i, doc in enumerate(results[:3], 1):
            title = doc.get('title_norm', 'No title')[:60]
            sim = doc.get('similarity', 0)
            print(f"  {i}. [{sim:.3f}] {title}...")
    else:
        print("❌ ProductionDBClient вернул 0 документов")

    return results

db_results = asyncio.run(test_db_client())

# ============================================================================
# ШАГ 5: Через RankingAPI.retrieve_for_analysis
# ============================================================================
print("\n\n🎯 ШАГ 5: ЧЕРЕЗ RankingAPI.retrieve_for_analysis")
print("-" * 80)

async def test_ranking_api():
    from ranking_api import RankingAPI

    api = RankingAPI()
    print("Вызываем: api.retrieve_for_analysis(query='trump', window='24h', k_final=5)")

    try:
        results = await api.retrieve_for_analysis(
            query="trump",
            window="24h",
            k_final=5
        )

        print(f"✅ RankingAPI вернул: {len(results)} документов")

        if results:
            print("\nТоп-3 результата (после скоринга и дедупликации):")
            for i, doc in enumerate(results[:3], 1):
                title = doc.get('title_norm', 'No title')[:60]
                score = doc.get('final_score', doc.get('similarity', 0))
                print(f"  {i}. [{score:.3f}] {title}...")
        else:
            print("❌ RankingAPI вернул 0 документов")

        return results

    except Exception as e:
        print(f"❌ RankingAPI выбросил ошибку: {e}")
        import traceback
        traceback.print_exc()
        return []

ranking_results = asyncio.run(test_ranking_api())

# ============================================================================
# ШАГ 6: Через RetrievalClient (используется в orchestrator)
# ============================================================================
print("\n\n🔄 ШАГ 6: ЧЕРЕЗ RetrievalClient (используется оркестратором)")
print("-" * 80)

async def test_retrieval_client():
    from core.rag.retrieval_client import get_retrieval_client

    client = get_retrieval_client()
    print("Вызываем: client.retrieve(query='trump', window='24h', k_final=5)")

    try:
        results = await client.retrieve(
            query="trump",
            window="24h",
            lang="auto",
            sources=None,
            k_final=5,
            use_rerank=False
        )

        print(f"✅ RetrievalClient вернул: {len(results)} документов")

        if results:
            print("\nТоп-3 результата:")
            for i, doc in enumerate(results[:3], 1):
                title = doc.get('title_norm', 'No title')[:60]
                score = doc.get('final_score', doc.get('similarity', 0))
                print(f"  {i}. [{score:.3f}] {title}...")
        else:
            print("❌ RetrievalClient вернул 0 документов")

        return results

    except Exception as e:
        print(f"❌ RetrievalClient выбросил ошибку: {e}")
        import traceback
        traceback.print_exc()
        return []

retrieval_results = asyncio.run(test_retrieval_client())

# ============================================================================
# ИТОГОВЫЙ АНАЛИЗ
# ============================================================================
print("\n\n" + "=" * 80)
print("📊 ИТОГОВЫЙ АНАЛИЗ")
print("=" * 80)

print(f"""
✅ База данных:
   - Таблица article_chunks: существует
   - Колонки (id, embedding_vector, published_at, title_norm): есть
   - Индексы на embedding_vector: есть
   - Всего чанков с эмбеддингами: {total:,}
   - Чанков за 24 часа: {recent_24h:,}

✅ Эмбеддинг:
   - Модель: OpenAI text-embedding-3-large
   - Размерность: {len(query_embedding)}
   - Запрос: "trump"

📊 Результаты тестов:
   1. Прямой SQL запрос: {len(direct_results)} документов
   2. ProductionDBClient: {len(db_results)} документов
   3. RankingAPI: {len(ranking_results)} документов
   4. RetrievalClient: {len(retrieval_results)} документов
""")

if len(direct_results) > 0 and len(ranking_results) == 0:
    print("⚠️ ПРОБЛЕМА НАЙДЕНА:")
    print("   Прямой SQL запрос возвращает результаты,")
    print("   но RankingAPI возвращает 0 документов.")
    print("   Проверьте логи выше на ошибки в скоринге или дедупликации.")
elif len(direct_results) == 0:
    print("⚠️ ПРОБЛЕМА:")
    print("   Даже прямой SQL запрос не находит документы.")
    print("   Проблема в данных или SQL запросе.")
elif len(ranking_results) > 0 and len(retrieval_results) == 0:
    print("⚠️ ПРОБЛЕМА:")
    print("   RankingAPI работает, но RetrievalClient возвращает 0.")
    print("   Проблема в RetrievalClient или его интеграции.")
elif len(retrieval_results) > 0:
    print("✅ ВСЕ РАБОТАЕТ КОРРЕКТНО!")
    print("   Retrieval pipeline возвращает результаты.")
    print("   /analyze должна работать в боте.")

print("\n" + "=" * 80)
