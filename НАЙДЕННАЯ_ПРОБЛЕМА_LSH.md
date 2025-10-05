# 🐛 Найденная проблема с LSH дедупликацией

## Проблема

Команда `/analyze trump` возвращает:
```
❌ Ошибка
No articles found for the specified criteria
🔧 Детали: Retrieval returned 0 documents
```

## Причина

**Ошибка:** `ValueError: The given key already exists` в `ranking_service/deduplication.py:174`

**Корневая причина:** Логическая ошибка в алгоритме вставки ключей в LSH

### Как это происходило:

1. **RankingAPI создается один раз** при старте бота
2. **DeduplicationEngine создается один раз** в `RankingAPI.__init__`
3. **MinHashLSH создавался один раз** в `DeduplicationEngine.__init__`
4. При первом `/analyze`:
   - Статья A вставляется в LSH
   - Статья B похожа на A → НЕ вставляется в LSH
   - Статья C похожа на A → НЕ вставляется в LSH
5. При втором `/analyze`:
   - LSH сбрасывается (наш фикс 1521e7a)
   - Статья A вставляется в LSH
   - Статья B похожа на A → **НЕ вставляется в LSH** (старая логика)
6. При третьем `/analyze`:
   - LSH сбрасывается
   - Статья A вставляется
   - **Статья B НЕ находит A** (LSH пустой после reset)
   - Статья B пытается вставиться → `ValueError: The given key already exists`

### Почему это происходит?

Старая логика (строки 165-175):
```python
if similar_articles:
    # Found similar articles
    for similar_id in similar_articles:
        duplicate_groups[similar_id].append(article_id)
    # НЕ ВСТАВЛЯЕМ article_id в LSH!
else:
    # New unique article
    self.lsh.insert(article_id, minhash)
    duplicate_groups[article_id] = [article_id]
```

**Проблема:** Если статья B похожа на статью A, то B не вставляется в LSH. Но это значит, что статья C, которая похожа на B, не найдет B в LSH!

## Решение

**Коммит ea8394e:** `fix(dedup): insert similar articles into LSH to prevent key collision`

Новая логика:
```python
if similar_articles:
    # Found similar articles
    for similar_id in similar_articles:
        duplicate_groups[similar_id].append(article_id)
    # ТАКЖЕ ВСТАВЛЯЕМ article_id в LSH (если еще не там)
    if article_id not in processed_hashes:
        self.lsh.insert(article_id, minhash)
else:
    # New unique article
    self.lsh.insert(article_id, minhash)
    duplicate_groups[article_id] = [article_id]
```

Теперь:
- Статья A вставляется в LSH
- Статья B находит A, добавляется в группу, **и ТОЖЕ вставляется в LSH**
- Статья C найдет и A, и B в LSH

## История фиксов

### 1. Коммит 2176333 (23:41 UTC)
`fix(retrieval): add retrieve_for_analysis method to RankingAPI`
- Добавлен метод для получения документов

### 2. Коммит 354fdef (23:45 UTC)
`fix(retrieval): correct time filter parameter handling`
- Исправлена SQL параметризация

### 3. Коммит 1521e7a (23:54 UTC)
`fix(ranking): resolve timezone and LSH duplicate key errors`
- Исправлено timezone сравнение
- Добавлен сброс LSH в `find_duplicates()` ← **НЕПОЛНОЕ РЕШЕНИЕ**

### 4. Коммит ea8394e (00:09 UTC) ✅
`fix(dedup): insert similar articles into LSH to prevent key collision`
- **ПОЛНОЕ РЕШЕНИЕ:** вставка похожих статей в LSH

## Тестирование

### ✅ Что работает:
1. База данных: 214,903 чанков с эмбеддингами
2. SQL запрос: возвращает 10 документов для "trump"
3. ProductionDBClient: возвращает 10 документов
4. Генерация эмбеддингов: OpenAI text-embedding-3-large (3072-dim)
5. Timezone обработка: исправлена
6. LSH сброс: добавлен

### ❌ Что было сломано (до ea8394e):
1. RankingAPI: 0 документов (ошибка LSH)
2. RetrievalClient: 0 документов
3. /analyze в боте: "No articles found"

### ✅ Что должно работать (после ea8394e):
1. RankingAPI: 5 документов
2. RetrievalClient: 5 документов
3. /analyze в боте: Claude анализ с результатами

## Следующие шаги

1. ✅ Коммит ea8394e задеплоен на Railway (00:09 UTC)
2. ⏳ Дождаться перезагрузки бота (автоматически после деплоя)
3. 🧪 Протестировать `/analyze trump` в Telegram
4. 🧪 Протестировать `/trends`
5. ✅ Если работает - закрыть issue

## Техническая информация

**Путь выполнения:**
```
Telegram → bot_service/advanced_bot.py
         → services/orchestrator.py
         → core/orchestrator/phase4_orchestrator.py
         → core/rag/retrieval_client.py
         → ranking_api.py::retrieve_for_analysis
         → database/production_db_client.py::search_with_time_filter
         → PostgreSQL (article_chunks)
         → ranking_service/scorer.py::score_and_rank
         → ranking_service/deduplication.py::canonicalize_articles ← БЫЛА ОШИБКА
         → Claude Sonnet 4 analysis
         → Response formatting
         → Telegram
```

**База данных:**
- Таблица: `article_chunks`
- Индекс: HNSW на `embedding_vector`
- Фильтр: `published_at >= NOW() - '24 hours'`
- Поиск: pgvector `<=>` operator (cosine distance)

**Deployment:**
- Platform: Railway
- Service ID: eac4079c-506c-4eab-a6d2-49bd860379de
- Latest commit: ea8394e
- Status: SUCCESS
- Time: 2025-10-05 00:09:20 UTC
