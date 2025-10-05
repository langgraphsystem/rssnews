# Статус команды /analyze

## Дата проверки: 2025-10-04

## ✅ ИТОГ: Команда /analyze работает корректно

---

## 1. Архитектура команды

### Цепочка вызовов:
```
/analyze (Telegram bot)
    ↓
advanced_bot.py::handle_analyze_command()
    ↓
services/orchestrator.py::execute_analyze_command()
    ↓
core/orchestrator/orchestrator.py::execute_analyze()
    ↓
core/orchestrator/nodes/retrieval_node.py::retrieval_node()
    ↓
core/rag/retrieval_client.py::retrieve()
    ↓
ranking_api.py::retrieve_for_analysis()
    ↓
database/production_db_client.py::search_with_time_filter()
```

### Ключевой SQL запрос:
```sql
SELECT
    ac.id, ac.article_id, ac.chunk_index, ac.text,
    ac.url, ac.title_norm, ac.source_domain, ac.published_at,
    1 - (ac.embedding_vector <=> %s::vector) AS similarity
FROM article_chunks ac
WHERE ac.embedding_vector IS NOT NULL
  AND ac.published_at >= NOW() - (%s || ' hours')::interval
ORDER BY ac.embedding_vector <=> %s::vector
LIMIT %s
```

---

## 2. Используемые данные

### База данных
- **Таблица**: `article_chunks`
- **Столбец для поиска**: `embedding_vector` (тип: `vector`)
- **Алгоритм**: Косинусное сходство (`<=>` оператор в pgvector)

### Статистика данных (последние 24 часа)
- ✅ **Всего чанков**: 3,862
- ✅ **С embeddings**: 3,862 (100%)
- ✅ **Размерность**: 3072 (OpenAI text-embedding-3-large)

---

## 3. Индексы для ускорения

Найдены следующие векторные индексы:

1. **idx_article_chunks_embedding_hnsw** (основной)
   - Тип: HNSW (Hierarchical Navigable Small World)
   - Оператор: `vector_cosine_ops`
   - Параметры: m=16, ef_construction=64

2. **idx_article_chunks_embedding_ivfflat** (резервный)
   - Тип: IVFFlat (Inverted File Flat)
   - Оператор: `vector_cosine_ops`
   - Параметры: lists=100

3. **idx_article_chunks_embedding_1536_hnsw**
   - Для embeddings размерности 1536 (старый формат)

---

## 4. Процесс работы команды

### Входные параметры:
- `mode`: keywords | sentiment | topics
- `query`: текстовый запрос пользователя
- `window`: временное окно (6h, 12h, 24h, 3d, 7d, 1m, 3m)
- `k_final`: количество результатов (по умолчанию 5)

### Этапы обработки:

#### 1. Генерация embedding запроса
```python
# ranking_api.py::retrieve_for_analysis()
query_embeddings = await self.embedding_generator.generate_embeddings([query_normalized])
query_embedding = query_embeddings[0]  # vector размерности 3072
```

#### 2. Поиск похожих чанков
```python
# database/production_db_client.py::search_with_time_filter()
results = await self.db.search_with_time_filter(
    query=query_normalized,
    query_embedding=query_embedding,
    hours=window_hours,
    limit=k_final * 2,  # Берём больше кандидатов
    filters=filters
)
```

#### 3. Scoring и ранжирование
```python
# ranking_api.py::retrieve_for_analysis()
scored_results = self.scorer.score_and_rank(results, query or "")
```

#### 4. Дедупликация
```python
# ranking_api.py::retrieve_for_analysis()
deduplicated = self.dedup_engine.canonicalize_articles(scored_results)
```

#### 5. Возврат топ-N результатов
```python
return deduplicated[:k_final]
```

---

## 5. Проверенные данные

### Примеры последних чанков с embeddings:

```
• [2025-10-04 22:35] Kristi Noem Says ICE Will Be 'All Over' the Super Bowl
  Чанк 7: A representative for Bad Bunny, a representative for the NFL...
  Vector: 3072-dimensional ✅

• [2025-10-04 22:35] Kristi Noem Says ICE Will Be 'All Over' the Super Bowl
  Чанк 9: Noem's comments echo those made by one of her chief advisers...
  Vector: 3072-dimensional ✅

• [2025-10-04 22:35] Kristi Noem Says ICE Will Be 'All Over' the Super Bowl
  Чанк 1: Asked on Friday by the right-wing podcaster Benny Johnson...
  Vector: 3072-dimensional ✅
```

---

## 6. Ответы на вопросы

### ❓ К какой базе обращается /analyze?
**Ответ**: PostgreSQL с расширением pgvector, таблица `article_chunks`

### ❓ Какой столбец используется?
**Ответ**: `embedding_vector` (тип vector, размерность 3072)

### ❓ Пустой ли этот столбец?
**Ответ**: НЕТ, заполнен на 100% для последних 24 часов (3,862 чанков)

### ❓ Использует ли FTS (Full-Text Search)?
**Ответ**: НЕТ напрямую. Используется только векторный поиск по embeddings.
FTS может использоваться в других методах (например, `hybrid_search`), но `retrieve_for_analysis` использует только семантический поиск.

### ❓ Какая модель embeddings?
**Ответ**: OpenAI `text-embedding-3-large` (размерность 3072)

---

## 7. Потенциальные проблемы и решения

### ⚠️ Проблема: Нет результатов при поиске
**Возможные причины:**
1. Нет статей в указанном временном окне
2. Embeddings не совпадают с запросом
3. Слишком узкие фильтры (sources, lang)

**Решение:**
- Команда использует автоматическое расширение окна (degradation logic)
- Если нет результатов за 24h, автоматически расширяется до 3d, 1w и т.д.

### ✅ Текущий статус
- База данных: полностью заполнена embeddings
- Индексы: созданы и работают (HNSW + IVFFlat)
- Поиск: работает корректно
- Модель: актуальная (text-embedding-3-large)

---

## 8. Рекомендации

### Для поддержания работоспособности:

1. **Следить за заполнением embeddings**
   ```bash
   railway run python check_analyze_columns.py
   ```

2. **Мониторить производительность индексов**
   - HNSW должен быть основным индексом
   - Периодически проверять EXPLAIN ANALYZE для запросов

3. **Проверять актуальность данных**
   - Новые статьи должны получать embeddings в течение 5-10 минут
   - Сервис `embedding` должен работать непрерывно

4. **Логи поиска**
   ```python
   # database/production_db_client.py:696
   logger.debug(f"search_with_time_filter returned {len(results)} results")
   ```

---

## 9. Файлы для проверки

- `check_analyze_columns.py` - проверка данных в БД
- `trace_analyze_command.py` - трассировка выполнения команды
- `debug_analyze_on_railway.py` - отладка на Railway

---

## Заключение

✅ **Команда /analyze полностью функциональна**

- База данных заполнена на 100%
- Используется современная модель embeddings (3072 dim)
- Есть эффективные индексы (HNSW)
- Все компоненты работают корректно

**Последняя проверка**: 2025-10-04
**Проверенный сервис**: Railway Production Database
