# Как обрабатываются новые эмбеддинги

## 📋 Обзор pipeline

Новые статьи проходят через следующий процесс:

```
RSS Feed → Poll → Parse → Chunk → Embedding → Storage (TEXT + pgvector)
```

---

## 🔄 Пошаговый процесс

### 1. Сбор статей (RSS Polling)

**Команда:** `python main.py poll`

**Файл:** `rss/poller.py` → `RSSPoller`

**Что происходит:**
- Опрашивает активные RSS feeds
- Сохраняет новые статьи в таблицу `raw` со статусом `pending`
- Использует etag/last-modified для кэширования

**Результат:**
```
Feeds processed: 112
New articles: 45
Status: pending → waiting for processing
```

---

### 2. Парсинг и чанкинг (Article Processing)

**Команда:** `python main.py work`

**Файл:** `worker.py` → `ArticleWorker.process_pending_articles()`

**Что происходит:**

1. **Получает pending статьи:**
   ```python
   articles = db.get_pending_articles(batch_size=50)
   ```

2. **Парсит контент:**
   - Скачивает HTML
   - Извлекает текст (parser/extract.py)
   - Создает chunks (semantic segmentation)

3. **Сохраняет chunks в БД:**
   ```python
   db.insert_article_chunks(chunks)
   # Chunks сохраняются БЕЗ эмбеддингов
   # embedding = NULL
   # embedding_vector = NULL
   ```

**Результат:**
```
Articles processed: 45
Successful: 42
Chunks created: 210 (average 5 per article)
```

---

### 3. Генерация эмбеддингов (Embedding Processing)

**Команда:** `python main.py work` (включает embeddings)

**Файл:** `services/embedding_service.py` → `EmbeddingService.process_embeddings()`

**Что происходит:**

#### 3.1. Получение chunks без эмбеддингов

```python
# pg_client_new.py
def get_chunks_needing_embeddings(batch_size):
    SELECT id, text FROM article_chunks
    WHERE embedding IS NULL  # <-- chunks без эмбеддингов
    LIMIT batch_size
```

#### 3.2. Генерация эмбеддингов через API

```python
# services/embedding_service.py
texts = [chunk['text'] for chunk in chunks]

# Вызывает OpenAI API
embeddings = await generator.generate_embeddings(texts)
# → text-embedding-3-large
# → 3072 dimensions
```

#### 3.3. Сохранение в БД (КЛЮЧЕВОЙ МОМЕНТ!)

```python
# services/embedding_service.py:71
for chunk, embedding in zip(chunks, embeddings):
    success = db.update_chunk_embedding(chunk_id, embedding)
```

**Внутри `update_chunk_embedding()` (pg_client_new.py:819):**

```python
def update_chunk_embedding(self, chunk_id, embedding):
    vec_str = '[' + ','.join(str(float(x)) for x in embedding) + ']'

    # 1. Сохраняем в TEXT колонку (всегда)
    cur.execute(
        "UPDATE article_chunks SET embedding = %s WHERE id = %s",
        (vec_str, chunk_id)
    )

    # 2. Пытаемся сохранить в pgvector (если доступен)
    try:
        cur.execute(
            "UPDATE article_chunks SET embedding_vector = %s::vector WHERE id = %s",
            (vec_str, chunk_id)
        )
        logger.debug("Updated both TEXT and pgvector columns")
    except Exception as e_pg:
        # pgvector недоступен - не критично, используем TEXT
        logger.debug(f"pgvector update skipped: {e_pg}")
```

**Результат:**
```
Embeddings processed: 210
Successful: 210
Saved to:
  - embedding (TEXT): ✅ Всегда
  - embedding_vector (pgvector): ✅ Если колонка существует
```

---

## ✅ Текущее состояние (после вашей миграции pgvector)

### Новые статьи с 02.10.2025:

| Шаг | Колонка | Значение |
|-----|---------|----------|
| После чанкинга | `embedding` | NULL |
| | `embedding_vector` | NULL |
| После генерации | `embedding` | JSON текст (3072 float) |
| | `embedding_vector` | vector(3072) ✅ |

**Итог:** Новые эмбеддинги автоматически попадают в **оба формата**!

---

### Старые статьи (до миграции):

| Колонка | Значение |
|---------|----------|
| `embedding` | JSON текст (3072 float) ✅ |
| `embedding_vector` | NULL (пока не мигрировано) |

**Итог:** Работает через Python fallback, медленнее.

---

## 🔍 Как работает поиск

### Поиск с pgvector (новые статьи):

```python
# pg_client_new.py:1159
cur.execute("""
    SELECT id, text, 1 - (embedding_vector <=> %s::vector) AS similarity
    FROM article_chunks
    WHERE embedding_vector IS NOT NULL
    ORDER BY embedding_vector <=> %s::vector
    LIMIT 10
""")
# Результат: 10-50ms ⚡
```

### Fallback для старых статей:

```python
# pg_client_new.py:1196 (_search_chunks_python_fallback)
# Загружает ВСЕ эмбеддинги в память
cur.execute("SELECT * FROM article_chunks WHERE embedding IS NOT NULL")

for row in cur.fetchall():
    # Считает косинусную близость в Python
    similarity = dot(query, stored) / (norm_a * norm_b)

# Результат: ~300ms 🐢
```

---

## 📊 Статистика обработки

### Типичный цикл (каждые 5-10 минут):

```bash
# 1. Сбор статей
python main.py poll
# → 5-10 новых статей

# 2. Обработка
python main.py work
# → Парсинг + чанкинг → 25-50 chunks
# → Генерация embeddings → 25-50 API calls к OpenAI
# → Сохранение в БД → embedding + embedding_vector

# 3. Автоматический результат:
# ✅ Новые chunks доступны для pgvector поиска
# ✅ Быстрый поиск (10-50ms)
# ✅ Никаких дополнительных действий не требуется
```

---

## 💰 Стоимость новых эмбеддингов

**Модель:** text-embedding-3-large
**Цена:** $0.00013 за 1K токенов

**Пример:**
- 10 статей
- 5 chunks каждая = 50 chunks
- 750 токенов на chunk в среднем
- **Стоимость:** 50 × 750 / 1000 × $0.00013 = **$0.0049** (~0.5 цента)

**Месячная оценка:**
- ~1000 новых статей/месяц
- ~5000 chunks
- **~$0.50/месяц** на эмбеддинги

---

## 🎯 Выводы

### ✅ Что работает ОТЛИЧНО:

1. **Новые статьи** автоматически получают pgvector эмбеддинги
2. **Поиск** автоматически использует pgvector где доступен
3. **Fallback** работает для старых статей (пока не мигрированы)
4. **Никаких изменений кода не требуется!**

### 📈 После завершения миграции:

1. Все 203,727 статей будут в pgvector формате
2. Python fallback больше не нужен
3. Все запросы станут быстрыми (10-50ms)
4. Код останется тем же - просто работает быстрее

### 🚀 Рекомендации:

**Ничего менять не нужно!** Система уже оптимально настроена:
- Новые эмбеддинги → pgvector автоматически
- Старые эмбеддинги → мигрируются батчами в фоне
- Поиск → использует pgvector где доступен

**Просто дождитесь завершения миграции (~6 часов) и получите полное ускорение!**

---

## 🔧 Проверка статуса

```bash
# Сколько эмбеддингов в pgvector
python scripts/calculate_migration_cost.py

# Тест производительности
python scripts/test_pgvector_search.py
```
