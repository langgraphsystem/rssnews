# OpenAI Embedding Migration Guide

## Обзор

Миграция системы эмбеддингов с локального embeddinggemma (768-dim) на OpenAI text-embedding-3-large (3072-dim).

---

## ✅ Что Сделано

### 1. Создан OpenAI Embedding Generator

**Файл:** `openai_embedding_generator.py`

```python
from openai_embedding_generator import OpenAIEmbeddingGenerator

gen = OpenAIEmbeddingGenerator()
embeddings = await gen.generate_embeddings(['text1', 'text2'])
# → Возвращает List[List[float]] размером 3072-dim
```

**Особенности:**
- ✅ Батч-обработка (до 100 текстов за раз)
- ✅ Автоматическая обрезка длинных текстов (8000 символов)
- ✅ Retry логика (через конфигурацию)
- ✅ Валидация размерности (3072-dim)
- ✅ Async API

### 2. Обновлены Поисковые Сервисы

**Обновлённые файлы:**
- `ranking_api.py` - изменён импорт и генератор
- `main.py` - RAG команда использует OpenAI
- `core/memory/embeddings_service.py` - Phase 3 память на text-embedding-3-large

**Было:**
```python
from local_embedding_generator import LocalEmbeddingGenerator
self.embedding_generator = LocalEmbeddingGenerator()  # 768-dim
```

**Стало:**
```python
from openai_embedding_generator import OpenAIEmbeddingGenerator
self.embedding_generator = OpenAIEmbeddingGenerator()  # 3072-dim
```

### 3. Создан Сервис Миграции Backlog

**Файл:** `services/openai_embedding_migration_service.py`

Обрабатывает 3,227 чанков без эмбеддингов.

---

## 🚀 Использование

### 1. Обновить .env

```bash
# OpenAI API
OPENAI_API_KEY=sk-proj-your-actual-key-here
OPENAI_EMBEDDING_MODEL=text-embedding-3-large

# Отключить локальные эмбеддинги в worker.py
ENABLE_LOCAL_EMBEDDINGS=false

# Настройки миграции
OPENAI_EMBEDDING_SERVICE_ENABLED=true
OPENAI_EMBEDDING_BATCH_SIZE=100
OPENAI_EMBEDDING_MAX_RETRIES=3
EMBEDDING_TIMEOUT=30
```

### 2. Проверить статистику

```bash
python services/openai_embedding_migration_service.py stats
```

**Вывод:**
```
📊 Embedding Statistics:
   Total chunks: 206,954
   With TEXT embeddings: 203,727
   With pgvector embeddings: 203,727
   Without embeddings: 3,227
   Completion: 98.4%
```

### 3. Мигрировать backlog

```bash
# Тест на 10 чанках
python services/openai_embedding_migration_service.py migrate --limit 10

# Полная миграция
python services/openai_embedding_migration_service.py migrate
```

**Стоимость:** ~$0.21 одноразово для 3,227 чанков

### 4. Запустить continuous mode (опционально)

```bash
# Фоновый сервис, проверяет новые чанки каждые 60 секунд
python services/openai_embedding_migration_service.py continuous --interval 60
```

### 5. Тестирование поиска

```bash
# Тест через main.py
python main.py rag --query "AI news" --limit 5

# Или через Python
python -c "
import asyncio
from ranking_api import RankingAPI

async def test():
    api = RankingAPI()
    # Поиск будет использовать OpenAI embeddings (3072-dim)
    results = await api.search('AI news', method='semantic', limit=5)
    print(f'Found {len(results)} results')

asyncio.run(test())
"
```

---

## 📊 Текущее Состояние БД

### Эмбеддинги:
- ✅ **203,727 чанков** с эмбеддингами 3072-dim (OpenAI)
- ⚠️ **3,227 чанков** без эмбеддингов (backlog)
- ✅ **100% pgvector migration** завершена

### Таблица article_chunks:
```sql
-- TEXT column (JSON) - для обратной совместимости
embedding TEXT

-- pgvector column - для быстрого поиска
embedding_vector vector(3072)
```

**Hybrid storage:** Новые эмбеддинги сохраняются в оба столбца автоматически через `pg_client_new.update_chunk_embedding()`.

---

## 💰 Стоимость

### Текущая ситуация:
- **Существующие 203,727 эмбеддингов:** Уже оплачены (~$19.86)
- **Backlog 3,227 чанков:** ~$0.21 одноразово
- **Новые статьи:** ~$0.30/месяц (50 чанков/день)
- **Поисковые запросы:** ~$0.01/день (100 запросов)

**ИТОГО: ~$0.60/месяц**

### Сравнение с embeddinggemma:

| Параметр | embeddinggemma | OpenAI 3-large |
|----------|----------------|----------------|
| Размерность | 768 | 3072 |
| Качество | Среднее | Отличное |
| Стоимость | $0/мес | $0.60/мес |
| Зависимости | Ollama (может отказать) | API (стабильно) |
| Совместимость с БД | ❌ Нужна пересоздать | ✅ Совместимо |

---

## 🔧 Архитектура

### Новый пайплайн:

```
RSS Feed → worker.py (чанкинг Qwen2.5-coder)
                ↓
         article_chunks БЕЗ embeddings
                ↓
  services/openai_embedding_migration_service.py
                ↓
         OpenAI API (text-embedding-3-large)
                ↓
    pg_client.update_chunk_embedding()
                ↓
  Сохранение в TEXT + pgvector (3072-dim)
                ↓
         ranking_api.py (поиск)
                ↓
    pgvector search (<=> оператор)
                ↓
            Результаты
```

### Разделение ответственности:

| Компонент | Ответственность |
|-----------|-----------------|
| **worker.py** | Чанкинг (Qwen2.5-coder local) |
| **openai_embedding_migration_service.py** | Генерация эмбеддингов (фон) |
| **ranking_api.py** | Поиск (query embeddings + pgvector) |
| **main.py** | RAG команды |
| **Phase 3 memory** | Долговременная память |

---

## 🧪 Тестирование

### 1. Тест генератора

```bash
python -c "
from openai_embedding_generator import OpenAIEmbeddingGenerator
gen = OpenAIEmbeddingGenerator()
print(f'Model: {gen.model}')
print(f'Dimensions: {gen.dimensions}')
"
```

**Ожидаемый результат:**
```
Model: text-embedding-3-large
Dimensions: 3072
```

### 2. Тест подключения

```bash
python -c "
import asyncio
from openai_embedding_generator import OpenAIEmbeddingGenerator

async def test():
    gen = OpenAIEmbeddingGenerator()
    result = await gen.test_connection()
    print('✅ Connection OK' if result else '❌ Connection failed')

asyncio.run(test())
"
```

### 3. Тест поиска с размерностью

```bash
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient
from openai_embedding_generator import OpenAIEmbeddingGenerator

async def test():
    client = PgClient()
    gen = OpenAIEmbeddingGenerator()

    # Генерируем 3072-dim запрос
    embeddings = await gen.generate_embeddings(['test'])
    query_emb = embeddings[0]

    print(f'Query: {len(query_emb)}-dim')

    # Поиск в БД (3072-dim)
    results = client.search_chunks_by_similarity(
        query_embedding=query_emb,
        limit=5,
        similarity_threshold=0.5
    )

    print(f'✅ Found {len(results)} results')
    print('✅ Dimensions match!')

asyncio.run(test())
"
```

---

## ⚠️ Важные Замечания

### 1. API Key

**КРИТИЧНО:** Обновите `OPENAI_API_KEY` в `.env` с валидным ключом:
```bash
OPENAI_API_KEY=sk-proj-your-actual-key-from-openai
```

Получить ключ: https://platform.openai.com/account/api-keys

### 2. Отключить локальные эмбеддинги

```bash
# В .env
ENABLE_LOCAL_EMBEDDINGS=false
```

Это отключает генерацию эмбеддингов в `worker.py`. Эмбеддинги будут создаваться фоновым сервисом.

### 3. Railway переменные

На Railway нужно установить:
```bash
railway vars set OPENAI_API_KEY=sk-proj-...
railway vars set OPENAI_EMBEDDING_MODEL=text-embedding-3-large
railway vars set ENABLE_LOCAL_EMBEDDINGS=false
```

### 4. Не удалять local_embedding_generator.py

Файл `local_embedding_generator.py` оставляем для обратной совместимости и возможности переключения обратно.

---

## 🔄 Откат (Rollback)

Если нужно вернуться к embeddinggemma:

### 1. Откатить изменения

```bash
git checkout ranking_api.py main.py core/memory/embeddings_service.py
```

### 2. Обновить .env

```bash
ENABLE_LOCAL_EMBEDDINGS=true
EMBEDDING_MODEL=embeddinggemma
```

### 3. Проблема: размерность БД

⚠️ **Данные в БД останутся 3072-dim**, поэтому embeddinggemma (768-dim) НЕ СМОЖЕТ искать.

**Варианты:**
- Пересоздать все эмбеддинги (долго + нужен Ollama)
- Оставить OpenAI (рекомендуется)

---

## 📝 Changelog

### 2025-10-03 - OpenAI Migration Complete

**Created:**
- `openai_embedding_generator.py` - OpenAI embedding generator (3072-dim)
- `services/openai_embedding_migration_service.py` - Backlog migration service
- `docs/OPENAI_EMBEDDING_MIGRATION.md` - Эта документация

**Modified:**
- `ranking_api.py` - Заменён LocalEmbeddingGenerator на OpenAI
- `main.py` - RAG команда использует OpenAI
- `core/memory/embeddings_service.py` - text-embedding-3-large (3072-dim)
- `.env.example` - Добавлены OpenAI настройки

**Database:**
- ✅ 203,727 embeddings (3072-dim) - совместимы
- ✅ pgvector column (3072-dim) - готов к использованию
- ⚠️ 3,227 chunks без эмбеддингов - требуется миграция

---

## 🎯 Следующие Шаги

1. ✅ Обновить `OPENAI_API_KEY` в `.env` и Railway
2. ✅ Запустить миграцию backlog: `python services/openai_embedding_migration_service.py migrate`
3. ✅ Проверить поиск: `python main.py rag --query "test"`
4. ✅ Запустить continuous mode на Railway (опционально)
5. ✅ Мониторинг стоимости через OpenAI dashboard

---

## 🆘 Troubleshooting

### Ошибка: "Incorrect API key provided"

**Решение:** Обновите `OPENAI_API_KEY` в `.env` с валидным ключом.

### Ошибка: "different vector dimensions 768 and 3072"

**Причина:** Используется старый LocalEmbeddingGenerator вместо OpenAI.

**Решение:** Проверьте импорты в `ranking_api.py` и `main.py`.

### Поиск не возвращает результаты

**Возможные причины:**
1. Backlog не обработан (3,227 чанков без эмбеддингов)
2. HNSW индекс не создан

**Решение:**
```bash
# Обработать backlog
python services/openai_embedding_migration_service.py migrate

# Создать HNSW индекс
psql $PG_DSN -f infra/migrations/004_enable_pgvector_step2.sql
```

### Медленный поиск

**Причина:** HNSW индекс не создан, используется sequential scan.

**Решение:** Создать индекс:
```bash
psql $PG_DSN -f infra/migrations/004_enable_pgvector_step2.sql
```

---

## 📚 Дополнительные Ресурсы

- OpenAI Embeddings Pricing: https://openai.com/api/pricing/
- pgvector Documentation: https://github.com/pgvector/pgvector
- Text Embedding 3 Large: https://platform.openai.com/docs/guides/embeddings

---

**Версия:** 1.0
**Дата:** 2025-10-03
**Автор:** Migration Team
