#!/usr/bin/env python3
"""
Анализ логов OpenAI Embedding Service
Проверяет проблемы с truncation и производительность
"""
import re
from datetime import datetime
from collections import defaultdict

# Логи из сервиса
logs = """
__main__ - INFO - Migrating embeddings for 12 chunks
2025-10-05 12:47:40,607 - openai_embedding_generator - WARNING - Truncated text from 8003 to 8000 characters
2025-10-05 12:47:41,441 - httpx - INFO - HTTP Request: POST https://api.openai.com/v1/embeddings "HTTP/1.1 200 OK"
2025-10-05 12:47:41,449 - openai_embedding_generator - INFO - Embedding generation complete: 12 successful / 12 total
2025-10-05 12:47:41,590 - __main__ - INFO - Migration progress: 12/12 successful (0 errors)
2025-10-05 12:47:41,590 - __main__ - INFO - Migration complete: 12 successful, 0 errors
"""

print("="*100)
print("АНАЛИЗ ЛОГОВ OpenAI EMBEDDING SERVICE")
print("="*100)

# Парсим логи
lines = [l.strip() for l in logs.strip().split('\n') if l.strip()]

print(f"\n📊 Общая информация:")
print(f"   Всего записей: {len(lines)}")

# Извлекаем ключевые данные
batch_size = None
truncations = []
success_count = None
error_count = None
timing = []

for line in lines:
    # Batch size
    if 'Migrating embeddings for' in line:
        match = re.search(r'for (\d+) chunks', line)
        if match:
            batch_size = int(match.group(1))

    # Truncation warnings
    if 'Truncated text from' in line:
        match = re.search(r'from (\d+) to (\d+)', line)
        if match:
            truncations.append({
                'from': int(match.group(1)),
                'to': int(match.group(2)),
                'lost': int(match.group(1)) - int(match.group(2))
            })

    # Success/error counts
    if 'successful / ' in line:
        match = re.search(r'(\d+) successful / (\d+) total', line)
        if match:
            success_count = int(match.group(1))
            total_count = int(match.group(2))

    # Timing
    if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line):
        timestamp = line.split(' - ')[0]
        timing.append(timestamp)

# Анализ батча
print(f"\n📦 БАТЧ ОБРАБОТКИ:")
print(f"   Размер батча: {batch_size} chunks")
print(f"   Успешно обработано: {success_count}/{batch_size}")
print(f"   Ошибок: 0")
print(f"   Успешность: {success_count/batch_size*100:.1f}%")

# Анализ truncation
print(f"\n⚠️  ПРОБЛЕМА: TRUNCATION (Обрезка текста)")
print(f"   Найдено truncation: {len(truncations)}")

if truncations:
    for i, trunc in enumerate(truncations, 1):
        print(f"\n   Truncation #{i}:")
        print(f"      Исходная длина: {trunc['from']:,} символов")
        print(f"      Обрезано до:    {trunc['to']:,} символов")
        print(f"      Потеряно:       {trunc['lost']:,} символов ({trunc['lost']/trunc['from']*100:.1f}%)")

    print(f"\n   ❌ КРИТИЧЕСКАЯ ПРОБЛЕМА:")
    print(f"      OpenAI API имеет лимит 8191 токенов на запрос")
    print(f"      Текущий лимит в коде: 8000 символов (очень приблизительно)")
    print(f"      Статья содержала 8003 символа - была обрезана")

# Анализ производительности
if len(timing) >= 2:
    try:
        start_time = datetime.strptime(timing[0], '%Y-%m-%d %H:%M:%S,%f')
        end_time = datetime.strptime(timing[-1], '%Y-%m-%d %H:%M:%S,%f')
        duration = (end_time - start_time).total_seconds()

        print(f"\n⏱️  ПРОИЗВОДИТЕЛЬНОСТЬ:")
        print(f"   Время обработки: {duration:.2f} секунд")
        print(f"   Скорость: {batch_size/duration:.1f} chunks/sec")
        print(f"   Время на 1 chunk: {duration/batch_size:.2f} sec")
    except:
        pass

# Рекомендации
print(f"\n{'='*100}")
print("РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ")
print(f"{'='*100}")

print(f"\n1️⃣  ПРОБЛЕМА TRUNCATION")
print(f"   Файл: services/openai_embedding_generator.py")
print(f"   Текущий код:")
print(f"   ```python")
print(f"   MAX_CHARS = 8000  # Слишком грубое ограничение")
print(f"   if len(text) > MAX_CHARS:")
print(f"       text = text[:MAX_CHARS]")
print(f"   ```")

print(f"\n   ✅ РЕШЕНИЕ 1: Использовать tiktoken для точного подсчета токенов")
print(f"   ```python")
print(f"   import tiktoken")
print(f"   ")
print(f"   encoding = tiktoken.encoding_for_model('text-embedding-3-large')")
print(f"   tokens = encoding.encode(text)")
print(f"   ")
print(f"   MAX_TOKENS = 8191  # OpenAI limit")
print(f"   if len(tokens) > MAX_TOKENS:")
print(f"       tokens = tokens[:MAX_TOKENS]")
print(f"       text = encoding.decode(tokens)")
print(f"   ```")

print(f"\n   ✅ РЕШЕНИЕ 2: Разбивать длинные тексты на несколько чанков")
print(f"   - Если текст > 8191 токенов, создать 2+ embedding")
print(f"   - Усреднить embeddings или хранить отдельно")

print(f"\n2️⃣  ПРОБЛЕМА: Почему чанк 8003 символа?")
print(f"   Файл: services/chunking_service.py")
print(f"   ")
print(f"   Возможная причина:")
print(f"   - CHUNK_SIZE слишком большой")
print(f"   - Нет валидации длины при создании чанка")
print(f"   ")
print(f"   ✅ РЕШЕНИЕ:")
print(f"   - Установить CHUNK_SIZE=6000 символов")
print(f"   - Добавить проверку перед созданием чанка")
print(f"   - Разбивать длинные параграфы")

print(f"\n3️⃣  МОНИТОРИНГ")
print(f"   Добавить метрики:")
print(f"   - Количество truncation за день")
print(f"   - Средняя длина обрезанного текста")
print(f"   - Процент потерянной информации")

print(f"\n4️⃣  ПРОВЕРКА ДАННЫХ")
print(f"   Найти все чанки с проблемной длиной:")

print(f"\n{'='*100}")
print("SQL ЗАПРОСЫ ДЛЯ ПРОВЕРКИ")
print(f"{'='*100}")

print(f"\n-- Найти все длинные чанки")
print(f"SELECT id, LENGTH(text) as text_length, title_norm")
print(f"FROM article_chunks")
print(f"WHERE LENGTH(text) > 7000")
print(f"ORDER BY LENGTH(text) DESC")
print(f"LIMIT 20;")

print(f"\n-- Статистика длины чанков")
print(f"SELECT")
print(f"  COUNT(*) as total,")
print(f"  AVG(LENGTH(text)) as avg_length,")
print(f"  MAX(LENGTH(text)) as max_length,")
print(f"  MIN(LENGTH(text)) as min_length,")
print(f"  COUNT(*) FILTER (WHERE LENGTH(text) > 7000) as over_7000,")
print(f"  COUNT(*) FILTER (WHERE LENGTH(text) > 8000) as over_8000")
print(f"FROM article_chunks;")

print(f"\n-- Найти чанки, которые были обрезаны (если есть метаданные)")
print(f"SELECT id, title_norm, LENGTH(text)")
print(f"FROM article_chunks")
print(f"WHERE metadata->>'truncated' = 'true'")
print(f"   OR LENGTH(text) = 8000  -- Ровно 8000 = вероятно обрезано")
print(f"LIMIT 10;")

print(f"\n{'='*100}")
print("ИТОГ")
print(f"{'='*100}")

print(f"\n✅ Сервис работает:")
print(f"   - 12/12 chunks успешно обработаны")
print(f"   - Embeddings сохранены")
print(f"   - Нет критических ошибок")

print(f"\n⚠️  Есть предупреждение:")
print(f"   - 1 текст обрезан с 8003 до 8000 символов")
print(f"   - Потеряно 3 символа (0.04%)")
print(f"   - Не критично для одного случая")

print(f"\n❌ Потенциальные проблемы:")
print(f"   - Если много текстов > 8000 символов, будет много truncation")
print(f"   - Теряется информация из конца текста")
print(f"   - Embeddings могут быть неполными")

print(f"\n🔧 Нужно исправить:")
print(f"   1. Использовать tiktoken вместо простого подсчета символов")
print(f"   2. Уменьшить CHUNK_SIZE до 6000-7000 символов")
print(f"   3. Добавить валидацию при чанкинге")
print(f"   4. Мониторить truncation метрики")
