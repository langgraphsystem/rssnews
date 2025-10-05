#!/usr/bin/env python3
"""
Упрощенная проверка данных для /analyze команды
Проверяет таблицу article_chunks и столбец embedding_vector
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 80)
    print("ПРОВЕРКА ДАННЫХ ДЛЯ /ANALYZE")
    print("=" * 80)

    # Подключение
    pg_dsn = os.getenv("PG_DSN")
    if not pg_dsn:
        # Попробуем Railway переменные
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            pg_dsn = db_url
        else:
            print("❌ PG_DSN или DATABASE_URL не установлены")
            print("\nПопробуйте:")
            print("  railway run python check_analyze_columns.py")
            return

    try:
        conn = psycopg2.connect(pg_dsn)
        cur = conn.cursor()

        db_name = pg_dsn.split('/')[-1].split('?')[0] if '/' in pg_dsn else 'unknown'
        print(f"\n📊 База данных: {db_name}")

        # 1. Проверяем существование таблицы и столбцов
        print("\n" + "=" * 80)
        print("1. СТРУКТУРА ТАБЛИЦЫ article_chunks")
        print("=" * 80)

        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'article_chunks'
            AND column_name IN ('embedding', 'embedding_vector', 'text', 'published_at')
            ORDER BY ordinal_position
        """)

        columns = cur.fetchall()
        if columns:
            print("\n📋 Столбцы:")
            for col in columns:
                print(f"  - {col[0]:<25} | Тип: {col[1]:<20} | NULL: {col[2]}")
        else:
            print("❌ Таблица article_chunks не найдена или не имеет нужных столбцов")
            return

        # 2. Проверяем индексы
        print("\n" + "=" * 80)
        print("2. ИНДЕКСЫ")
        print("=" * 80)

        cur.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'article_chunks'
            AND (indexdef ILIKE '%embedding_vector%' OR indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')
            ORDER BY indexname
        """)

        indexes = cur.fetchall()
        if indexes:
            print("\n🔍 Найденные векторные индексы:")
            for idx in indexes:
                print(f"\n  📌 {idx[0]}")
                print(f"     {idx[1][:150]}")
        else:
            print("⚠️  Векторные индексы не найдены (может быть медленный поиск)")

        # 3. Проверяем данные за последние 24 часа
        print("\n" + "=" * 80)
        print("3. ДАННЫЕ ЗА ПОСЛЕДНИЕ 24 ЧАСА")
        print("=" * 80)

        # Общее количество
        cur.execute("""
            SELECT COUNT(*)
            FROM article_chunks
            WHERE published_at >= NOW() - INTERVAL '24 hours'
        """)
        total_24h = cur.fetchone()[0]

        # С embedding_vector
        cur.execute("""
            SELECT COUNT(*)
            FROM article_chunks
            WHERE published_at >= NOW() - INTERVAL '24 hours'
            AND embedding_vector IS NOT NULL
        """)
        with_embedding = cur.fetchone()[0]

        # С embedding (текстовый)
        cur.execute("""
            SELECT COUNT(*)
            FROM article_chunks
            WHERE published_at >= NOW() - INTERVAL '24 hours'
            AND embedding IS NOT NULL
        """)
        with_text_embedding = cur.fetchone()[0]

        print(f"\n📊 Статистика:")
        print(f"  Всего чанков (24ч):          {total_24h}")
        print(f"  С embedding_vector:          {with_embedding} ({with_embedding/total_24h*100 if total_24h else 0:.1f}%)")
        print(f"  С embedding (текст):         {with_text_embedding} ({with_text_embedding/total_24h*100 if total_24h else 0:.1f}%)")

        # Оценка
        if with_embedding == 0:
            print("\n❌ ПРОБЛЕМА: embedding_vector пустой!")
            print("   /analyze НЕ БУДЕТ РАБОТАТЬ")
            print("\n   Возможные решения:")
            print("   1. Запустить миграцию embeddings")
            print("   2. Запустить сервис генерации embeddings")
        elif with_embedding < total_24h * 0.5:
            print(f"\n⚠️  ВНИМАНИЕ: Только {with_embedding/total_24h*100:.1f}% чанков имеют embeddings")
            print("   /analyze будет работать с ограниченными данными")
        else:
            print(f"\n✅ ХОРОШО: {with_embedding/total_24h*100:.1f}% чанков имеют embeddings")

        # 4. Примеры данных
        if with_embedding > 0:
            print("\n" + "=" * 80)
            print("4. ПРИМЕРЫ ЧАНКОВ С EMBEDDINGS")
            print("=" * 80)

            cur.execute("""
                SELECT
                    article_id,
                    chunk_index,
                    title_norm,
                    LEFT(text, 100) as text_preview,
                    published_at,
                    CASE WHEN embedding_vector IS NOT NULL THEN 'YES' ELSE 'NO' END as has_vector
                FROM article_chunks
                WHERE published_at >= NOW() - INTERVAL '24 hours'
                AND embedding_vector IS NOT NULL
                ORDER BY published_at DESC
                LIMIT 5
            """)

            examples = cur.fetchall()
            print(f"\n🔍 Последние {len(examples)} чанков с embeddings:")
            for ex in examples:
                pub_time = ex[4].strftime('%Y-%m-%d %H:%M') if ex[4] else 'unknown'
                print(f"\n  • [{pub_time}] {ex[2]}")
                print(f"    Чанк {ex[1]}: {ex[3]}...")
                print(f"    Vector: {ex[5]}")

        # 5. Проверяем размерность embeddings
        print("\n" + "=" * 80)
        print("5. РАЗМЕРНОСТЬ EMBEDDINGS")
        print("=" * 80)

        if with_embedding > 0:
            # Для pgvector используем специальную функцию vector_dims
            try:
                cur.execute("""
                    SELECT
                        vector_dims(embedding_vector) as dimension,
                        COUNT(*) as count
                    FROM article_chunks
                    WHERE embedding_vector IS NOT NULL
                    AND published_at >= NOW() - INTERVAL '24 hours'
                    GROUP BY dimension
                    ORDER BY count DESC
                """)

                dimensions = cur.fetchall()
                print("\n📏 Найденные размерности:")
                for dim in dimensions:
                    if dim[0]:
                        print(f"  - {dim[0]} измерений: {dim[1]} чанков")
                        if dim[0] == 1536:
                            print("    ✅ OpenAI text-embedding-ada-002 (1536)")
                        elif dim[0] == 3072:
                            print("    ✅ OpenAI text-embedding-3-large (3072)")
                        elif dim[0] == 768:
                            print("    ⚠️  BERT-like model (768)")
            except Exception as e:
                print(f"\n⚠️  Не удалось определить размерность: {e}")
        else:
            print("\n⚠️  Нет данных для проверки размерности")

        # 6. Итоги
        print("\n" + "=" * 80)
        print("ИТОГИ")
        print("=" * 80)

        print("\n📌 Команда /analyze использует:")
        print("   Таблица:  article_chunks")
        print("   Столбец:  embedding_vector (pgvector)")
        print("   Поиск:    Косинусное сходство (<=> оператор)")
        print("   Индекс:   HNSW или IVFFlat (если есть)")

        print(f"\n📊 Текущее состояние:")
        if with_embedding > 0:
            print(f"   ✅ Данные есть: {with_embedding} чанков с embeddings")
            print(f"   ✅ /analyze должна работать")
            if with_embedding < total_24h * 0.8:
                print(f"   ⚠️  Рекомендуется дозаполнить embeddings ({with_embedding/total_24h*100:.1f}% покрытие)")
        else:
            print(f"   ❌ Данных нет!")
            print(f"   ❌ /analyze НЕ РАБОТАЕТ")
            print(f"\n   Необходимые действия:")
            print(f"   1. Проверить сервис генерации embeddings")
            print(f"   2. Запустить миграцию для существующих статей")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"\n❌ Ошибка подключения к БД: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
