#!/usr/bin/env python3
"""
Проверка данных для команды /analyze
Проверяет:
1. Какие столбцы используются в search_with_time_filter
2. Есть ли данные в этих столбцах
3. Какой индекс используется для поиска
"""
import asyncio
import os
from datetime import datetime, timezone
from pg_client_new import PgClient

async def main():
    print("=" * 80)
    print("ПРОВЕРКА ДАННЫХ ДЛЯ КОМАНДЫ /ANALYZE")
    print("=" * 80)

    # Подключение к БД
    pg_dsn = os.getenv("PG_DSN")
    if not pg_dsn:
        print("❌ PG_DSN не установлен")
        return

    client = PgClient(pg_dsn)
    await client.initialize()

    print(f"\n📊 База данных: {pg_dsn.split('@')[1] if '@' in pg_dsn else 'unknown'}")

    # 1. Проверяем структуру таблицы articles
    print("\n" + "=" * 80)
    print("1. СТРУКТУРА ТАБЛИЦЫ articles")
    print("=" * 80)

    async with client._cursor() as cur:
        # Получаем информацию о столбцах
        await cur.execute("""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable
            FROM information_schema.columns
            WHERE table_name = 'articles'
            AND column_name IN ('embedding', 'embedding_vector', 'embedding_3072', 'text_search_vector')
            ORDER BY ordinal_position
        """)

        columns = await cur.fetchall()
        if columns:
            print("\n📋 Найденные столбцы для поиска:")
            for col in columns:
                print(f"  - {col[0]:<25} | Тип: {col[1]:<20} | NULL: {col[3]}")
        else:
            print("⚠️  Столбцы embedding/text_search_vector не найдены")

    # 2. Проверяем индексы
    print("\n" + "=" * 80)
    print("2. ИНДЕКСЫ НА ТАБЛИЦЕ articles")
    print("=" * 80)

    async with client._cursor() as cur:
        await cur.execute("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = 'articles'
            AND (
                indexdef ILIKE '%embedding%'
                OR indexdef ILIKE '%text_search%'
                OR indexdef ILIKE '%tsvector%'
            )
            ORDER BY indexname
        """)

        indexes = await cur.fetchall()
        if indexes:
            print("\n🔍 Найденные индексы для поиска:")
            for idx in indexes:
                print(f"\n  📌 {idx[0]}")
                print(f"     {idx[1][:100]}...")
        else:
            print("⚠️  Индексы для поиска не найдены")

    # 3. Проверяем наличие данных в столбцах
    print("\n" + "=" * 80)
    print("3. ДАННЫЕ В СТОЛБЦАХ (последние 24 часа)")
    print("=" * 80)

    async with client._cursor() as cur:
        # Проверяем каждый столбец
        columns_to_check = [
            ('embedding', 'Embeddings (текст)'),
            ('embedding_vector', 'Embeddings (vector)'),
            ('embedding_3072', 'Embeddings 3072'),
            ('text_search_vector', 'Full-text search (tsvector)')
        ]

        for col_name, description in columns_to_check:
            try:
                # Проверяем существование столбца
                await cur.execute(f"""
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'articles'
                    AND column_name = %s
                """, (col_name,))

                if not await cur.fetchone():
                    print(f"\n  ❌ {description}")
                    print(f"     Столбец '{col_name}' не существует")
                    continue

                # Подсчитываем записи с данными за 24 часа
                await cur.execute(f"""
                    SELECT COUNT(*)
                    FROM articles
                    WHERE published_at >= NOW() - INTERVAL '24 hours'
                    AND {col_name} IS NOT NULL
                """)

                count_with_data = (await cur.fetchone())[0]

                # Общее количество за 24 часа
                await cur.execute("""
                    SELECT COUNT(*)
                    FROM articles
                    WHERE published_at >= NOW() - INTERVAL '24 hours'
                """)

                total_count = (await cur.fetchone())[0]

                if total_count > 0:
                    percentage = (count_with_data / total_count) * 100
                    status = "✅" if percentage > 80 else "⚠️" if percentage > 20 else "❌"
                    print(f"\n  {status} {description}")
                    print(f"     Заполнено: {count_with_data}/{total_count} ({percentage:.1f}%)")

                    if count_with_data > 0:
                        # Показываем примеры
                        await cur.execute(f"""
                            SELECT id, title_norm, published_at
                            FROM articles
                            WHERE published_at >= NOW() - INTERVAL '24 hours'
                            AND {col_name} IS NOT NULL
                            ORDER BY published_at DESC
                            LIMIT 3
                        """)

                        examples = await cur.fetchall()
                        if examples:
                            print(f"     Примеры статей с данными:")
                            for ex in examples:
                                pub_time = ex[2].strftime('%Y-%m-%d %H:%M') if ex[2] else 'unknown'
                                print(f"       • [{pub_time}] {ex[1][:60]}...")
                else:
                    print(f"\n  ⚠️  {description}")
                    print(f"     Нет статей за последние 24 часа")

            except Exception as e:
                print(f"\n  ❌ {description}")
                print(f"     Ошибка проверки: {e}")

    # 4. Проверяем метод search_with_time_filter
    print("\n" + "=" * 80)
    print("4. ТЕСТОВЫЙ ЗАПРОС search_with_time_filter")
    print("=" * 80)

    try:
        # Создаем тестовый эмбеддинг
        test_embedding = [0.1] * 1536  # Fake embedding

        print("\n🔍 Выполняем тестовый поиск по запросу 'AI'...")
        results = await client.search_with_time_filter(
            query="AI",
            query_embedding=test_embedding,
            hours=24,
            limit=5,
            filters={}
        )

        if results:
            print(f"\n✅ Найдено результатов: {len(results)}")
            print("\nПервые результаты:")
            for i, result in enumerate(results[:3], 1):
                print(f"\n  {i}. {result.get('title_norm', 'No title')[:60]}...")
                print(f"     URL: {result.get('url', 'N/A')}")
                print(f"     Опубликовано: {result.get('published_at', 'N/A')}")
                scores = result.get('scores', {})
                if scores:
                    print(f"     Scores: {scores}")
        else:
            print("\n❌ Результаты не найдены")
            print("\nВозможные причины:")
            print("  1. Нет статей за последние 24 часа")
            print("  2. Отсутствуют embeddings в базе")
            print("  3. Не работает индекс поиска")

    except Exception as e:
        print(f"\n❌ Ошибка при выполнении поиска: {e}")
        import traceback
        traceback.print_exc()

    # 5. Проверяем конкретный SQL запрос, который используется
    print("\n" + "=" * 80)
    print("5. АНАЛИЗ SQL ЗАПРОСА")
    print("=" * 80)

    print("\n📝 Код метода search_with_time_filter находится в файле:")
    print("   pg_client_new.py")

    # Читаем исходный код метода
    try:
        import inspect
        source = inspect.getsource(client.search_with_time_filter)

        # Ищем SQL запросы в коде
        import re
        sql_queries = re.findall(r'(SELECT.*?FROM.*?)(?:\"\"\"|\'\'\')', source, re.DOTALL | re.IGNORECASE)

        if sql_queries:
            print("\n🔍 SQL запросы в методе:")
            for i, sql in enumerate(sql_queries[:2], 1):  # Показываем первые 2
                print(f"\n  Запрос {i}:")
                # Форматируем для читаемости
                sql_clean = ' '.join(sql.split())[:200]
                print(f"  {sql_clean}...")
    except Exception as e:
        print(f"\n⚠️  Не удалось извлечь SQL: {e}")

    print("\n" + "=" * 80)
    print("ИТОГОВЫЕ РЕКОМЕНДАЦИИ")
    print("=" * 80)

    async with client._cursor() as cur:
        # Проверяем, какие столбцы заполнены
        await cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) as emb_text,
                COUNT(*) FILTER (WHERE embedding_vector IS NOT NULL) as emb_vector,
                COUNT(*) FILTER (WHERE text_search_vector IS NOT NULL) as fts
            FROM articles
            WHERE published_at >= NOW() - INTERVAL '24 hours'
        """)

        stats = await cur.fetchone()

        print("\nДля команды /analyze используется:")
        print("  1. Гибридный поиск (semantic + FTS)")
        print("  2. Временной фильтр (hours)")

        if stats:
            print(f"\nТекущее состояние данных (24ч):")
            print(f"  - embedding (текст):     {stats[0]} записей")
            print(f"  - embedding_vector:      {stats[1]} записей")
            print(f"  - text_search_vector:    {stats[2]} записей")

            if stats[1] > 0:
                print("\n✅ Рекомендация: Использовать embedding_vector (pgvector)")
            elif stats[0] > 0:
                print("\n⚠️  Рекомендация: Мигрировать на embedding_vector")
            else:
                print("\n❌ ПРОБЛЕМА: Нет embeddings в базе!")
                print("   Необходимо запустить сервис генерации embeddings")

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
