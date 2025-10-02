#!/usr/bin/env python3
"""Calculate cost of migrating remaining embeddings"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient


def calculate_cost():
    client = PgClient()

    with client._cursor() as cur:
        # Check embedding dimension
        cur.execute('SELECT embedding FROM article_chunks WHERE embedding IS NOT NULL LIMIT 1')
        row = cur.fetchone()

        if not row:
            print("No embeddings found")
            return

        emb = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        dim = len(emb)

        print(f"Размерность эмбеддинга: {dim}")

        if dim == 768:
            model = "embeddinggemma (Ollama - локальная)"
            cost_per_1k = 0.0
            is_free = True
        elif dim == 1536:
            model = "text-embedding-ada-002 (OpenAI)"
            cost_per_1k = 0.0001
            is_free = False
        elif dim == 3072:
            model = "text-embedding-3-large (OpenAI)"
            cost_per_1k = 0.00013
            is_free = False
        else:
            model = f"Unknown ({dim} dimensions)"
            cost_per_1k = 0.0
            is_free = True

        print(f"Модель: {model}")
        if not is_free:
            print(f"Цена: ${cost_per_1k} за 1K токенов")

        # Statistics
        cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL')
        total = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL')
        migrated = cur.fetchone()[0]

        remaining = total - migrated

        print(f"\n=== Статистика ===")
        print(f"Всего эмбеддингов: {total:,}")
        print(f"Мигрировано в pgvector: {migrated:,} ({100*migrated//total if total > 0 else 0}%)")
        print(f"Осталось мигрировать: {remaining:,}")

        # Average chunk size
        cur.execute('''
            SELECT AVG(LENGTH(text))
            FROM article_chunks
            WHERE embedding IS NOT NULL
            LIMIT 10000
        ''')
        avg_chars = cur.fetchone()[0] or 0
        avg_tokens = int(avg_chars / 4)

        print(f"\n=== Средний размер chunk ===")
        print(f"Символов: {int(avg_chars):,}")
        print(f"Токенов (примерно): {avg_tokens:,}")

        if is_free:
            print(f"\n=== Миграция БЕСПЛАТНА ===")
            print(f"Используется локальная модель - только время процессора")
            print(f"Примерное время: {remaining // 100 * 8} секунд (~{remaining // 100 * 8 // 3600} часов)")
        else:
            print(f"\n=== Стоимость миграции НЕ НУЖНА ===")
            print(f"⚠️ ВАЖНО: Миграция = просто копирование существующих эмбеддингов")
            print(f"Эмбеддинги уже сгенерированы и хранятся в БД как TEXT.")
            print(f"Батч-скрипт просто копирует их в pgvector формат.")
            print(f"Стоимость: $0.00 (нет API запросов)")

            print(f"\n=== Стоимость если бы генерировали заново ===")
            print(f"(Это НЕ наш случай, только для справки)")
            total_tokens = remaining * avg_tokens
            total_cost = (total_tokens / 1000) * cost_per_1k

            print(f"Всего токенов: {total_tokens:,}")
            print(f"Полная стоимость: ${total_cost:.2f}")

            print(f"\nПо батчам:")
            for batch_size in [1000, 5000, 10000, 50000]:
                if batch_size > remaining:
                    continue
                batch_tokens = batch_size * avg_tokens
                batch_cost = (batch_tokens / 1000) * cost_per_1k
                print(f"  {batch_size:,} chunks = ${batch_cost:.2f}")

            print(f"  {remaining:,} chunks (все) = ${total_cost:.2f}")


if __name__ == '__main__':
    calculate_cost()
