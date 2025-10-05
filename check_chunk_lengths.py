#!/usr/bin/env python3
"""Проверка длины чанков в БД"""
from database.production_db_client import ProductionDBClient

db = ProductionDBClient()

with db._cursor() as cur:
    # Статистика длины чанков
    cur.execute('''
        SELECT
          COUNT(*) as total,
          ROUND(AVG(LENGTH(text))) as avg_length,
          MAX(LENGTH(text)) as max_length,
          MIN(LENGTH(text)) as min_length,
          COUNT(*) FILTER (WHERE LENGTH(text) > 7000) as over_7000,
          COUNT(*) FILTER (WHERE LENGTH(text) > 8000) as over_8000,
          COUNT(*) FILTER (WHERE LENGTH(text) = 8000) as exactly_8000
        FROM article_chunks
    ''')
    stats = cur.fetchone()

    print('='*80)
    print('СТАТИСТИКА ДЛИНЫ ЧАНКОВ')
    print('='*80)
    print(f'\n📊 Общая статистика:')
    print(f'  Всего чанков: {stats[0]:,}')
    print(f'  Средняя длина: {stats[1]:,} символов')
    print(f'  Максимум: {stats[2]:,} символов')
    print(f'  Минимум: {stats[3]:,} символов')

    print(f'\n⚠️  Проблемные чанки:')
    print(f'  > 7000 символов: {stats[4]:,} ({stats[4]/stats[0]*100:.2f}%)')
    print(f'  > 8000 символов: {stats[5]:,} ({stats[5]/stats[0]*100:.2f}%)')
    print(f'  = 8000 символов (обрезаны): {stats[6]:,} ({stats[6]/stats[0]*100:.2f}%)')

    # Топ-10 самых длинных
    cur.execute('''
        SELECT id, LENGTH(text) as len, title_norm
        FROM article_chunks
        WHERE LENGTH(text) > 7000
        ORDER BY LENGTH(text) DESC
        LIMIT 10
    ''')

    long_chunks = cur.fetchall()
    if long_chunks:
        print(f'\n📝 Топ-10 самых длинных чанков:')
        for i, (id, length, title) in enumerate(long_chunks, 1):
            print(f'  {i}. ID {id}: {length:,} символов - {title[:60]}...')
