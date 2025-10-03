#!/usr/bin/env python3
"""Check embedding history - which model was used when"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient


def check_history():
    client = PgClient()

    print("=== История эмбеддингов ===\n")

    with client._cursor() as cur:
        # Проверяем самые старые эмбеддинги
        print("📅 САМЫЕ СТАРЫЕ эмбеддинги:")
        cur.execute('''
            SELECT id, embedding, created_at
            FROM article_chunks
            WHERE embedding IS NOT NULL
            ORDER BY id ASC
            LIMIT 3
        ''')

        for row in cur.fetchall():
            chunk_id, emb, created = row
            emb_list = json.loads(emb) if isinstance(emb, str) else emb
            dim = len(emb_list)

            if dim == 768:
                model = "embeddinggemma (Ollama - ЛОКАЛЬНАЯ)"
            elif dim == 1536:
                model = "text-embedding-ada-002 (OpenAI)"
            elif dim == 3072:
                model = "text-embedding-3-large (OpenAI)"
            else:
                model = f"Unknown ({dim} dim)"

            print(f"  ID {chunk_id}: {dim} dim → {model}")
            print(f"    Создан: {created}")

        print()

        # Проверяем самые новые эмбеддинги
        print("🆕 САМЫЕ НОВЫЕ эмбеддинги:")
        cur.execute('''
            SELECT id, embedding, created_at
            FROM article_chunks
            WHERE embedding IS NOT NULL
            ORDER BY id DESC
            LIMIT 3
        ''')

        for row in cur.fetchall():
            chunk_id, emb, created = row
            emb_list = json.loads(emb) if isinstance(emb, str) else emb
            dim = len(emb_list)

            if dim == 768:
                model = "embeddinggemma (Ollama - ЛОКАЛЬНАЯ)"
            elif dim == 1536:
                model = "text-embedding-ada-002 (OpenAI)"
            elif dim == 3072:
                model = "text-embedding-3-large (OpenAI)"
            else:
                model = f"Unknown ({dim} dim)"

            print(f"  ID {chunk_id}: {dim} dim → {model}")
            print(f"    Создан: {created}")

        print()
        print("="*60)
        print()

        # Общая статистика
        print("📊 СТАТИСТИКА ПО МОДЕЛЯМ:")

        # Считаем размерности вручную из первых 1000
        cur.execute('''
            SELECT embedding
            FROM article_chunks
            WHERE embedding IS NOT NULL
            LIMIT 1000
        ''')

        dim_counts = {768: 0, 1536: 0, 3072: 0, 'other': 0}

        for row in cur.fetchall():
            emb = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            dim = len(emb)
            if dim in dim_counts:
                dim_counts[dim] += 1
            else:
                dim_counts['other'] += 1

        total_sample = sum(dim_counts.values())

        if dim_counts[768] > 0:
            print(f"  768-dim (embeddinggemma LOCAL): {dim_counts[768]}/{total_sample} ({100*dim_counts[768]//total_sample}%)")
        if dim_counts[1536] > 0:
            print(f"  1536-dim (ada-002 OpenAI): {dim_counts[1536]}/{total_sample} ({100*dim_counts[1536]//total_sample}%)")
        if dim_counts[3072] > 0:
            print(f"  3072-dim (3-large OpenAI): {dim_counts[3072]}/{total_sample} ({100*dim_counts[3072]//total_sample}%)")
        if dim_counts['other'] > 0:
            print(f"  Other: {dim_counts['other']}/{total_sample}")

        print(f"\n  (Выборка из {total_sample} эмбеддингов)")

        print()
        print("="*60)
        print()

        # ВЫВОД
        print("💡 ВЫВОДЫ:")
        print()

        if dim_counts[3072] > dim_counts[768]:
            print("  ✅ СЕЙЧАС используется: OpenAI text-embedding-3-large (3072-dim)")
            print("  💸 Стоимость: ~$0.00013 за 1K токенов")
            print()
            if dim_counts[768] > 0:
                print("  📜 РАНЬШЕ использовалось: embeddinggemma (768-dim) - локальная")
                print("  💰 Было бесплатно, но медленнее")
                print()
                print("  🔄 Произошёл переход с локальной модели на OpenAI API")
        elif dim_counts[768] > dim_counts[3072]:
            print("  ✅ ОСНОВНАЯ ЧАСТЬ: embeddinggemma (768-dim) - ЛОКАЛЬНАЯ")
            print("  💰 Бесплатно, работает через Ollama")
            print()
            if dim_counts[3072] > 0:
                print("  🆕 НЕДАВНО добавлено: OpenAI text-embedding-3-large (3072-dim)")
                print("  💸 Платно: ~$0.00013 за 1K токенов")

        print()
        print("="*60)
        print()

        # Проверяем какая модель сейчас в конфиге
        print("⚙️  ТЕКУЩАЯ КОНФИГУРАЦИЯ:")
        embedding_model = os.getenv('EMBEDDING_MODEL', 'embeddinggemma')
        ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        openai_key = os.getenv('OPENAI_API_KEY')

        print(f"  EMBEDDING_MODEL: {embedding_model}")
        print(f"  OLLAMA_BASE_URL: {ollama_url}")
        print(f"  OPENAI_API_KEY: {'✅ установлен' if openai_key else '❌ не установлен'}")
        print()

        if dim_counts[3072] > 0 and embedding_model == 'embeddinggemma':
            print("  ⚠️  ВНИМАНИЕ: В БД есть 3072-dim эмбеддинги, но конфиг указывает embeddinggemma!")
            print("  Возможно используется другой код для генерации эмбеддингов.")


if __name__ == '__main__':
    check_history()
