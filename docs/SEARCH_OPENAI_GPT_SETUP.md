# OpenAI GPT Actions Setup для /search

## Обзор

Этот документ описывает настройку OpenAI GPT Custom Agent (SearchAgent) для интеграции с вашим `/retrieve` API endpoint.

## Архитектура

```
Пользователь → ChatGPT → SearchAgent (GPT) → GPT Action (retrieve) → Railway Bot API → PostgreSQL
```

**Что реализовано:**

✅ HTTP endpoint: `https://rssnews-production-eaa2.up.railway.app/retrieve`
✅ OpenAPI спецификация: `api/search_openapi.yaml`
✅ Интеграция с существующим RankingAPI
✅ Cursor-based pagination
✅ Coverage и freshness метрики
✅ Auto-retry support (24h → 48h → 72h)

---

## Шаг 1: Тестирование API

Перед настройкой GPT убедитесь, что API работает:

```bash
curl -X POST https://rssnews-production-eaa2.up.railway.app/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "artificial intelligence",
    "hours": 24,
    "k": 5
  }'
```

**Ожидаемый результат:**
```json
{
  "items": [...],
  "next_cursor": null,
  "total_available": 5,
  "coverage": 1.0,
  "freshness_stats": {
    "median_age_seconds": 15228.5,
    "window_hours": 24
  }
}
```

---

## Шаг 2: Создание Custom GPT в OpenAI

1. Перейдите на https://platform.openai.com/playground/assistants
2. Нажмите **"Create"** → **"Custom GPT"**
3. Заполните:
   - **Name**: `SearchAgent` или `RSS News Search`
   - **Description**: `News search agent with access to RSS news database via /retrieve API`

---

## Шаг 3: System Prompt

Вставьте следующий system prompt:

```
You are SearchAgent for the /search command in RSS News system.

Your tool: retrieve — GPT Action (REST API via OpenAPI)

Algorithm:
1. Parse user query and determine parameters:
   - query: user's search keywords
   - hours: time window (default: 24, can expand to 48, 72)
   - k: number of results (default: 10)
   - filters: optional {sources: [...], lang: "en"}
   - cursor: for pagination (null initially)

2. Call retrieve action with parameters

3. Auto-retry on empty results (max 3 attempts total):
   - If items array is empty and hours=24 → retry with hours=48
   - If still empty and hours=48 → retry with hours=72
   - If still empty → inform user "no results found"

4. Present results to user:
   - Show article titles with URLs
   - Show source domains and published dates
   - Show relevance scores if available
   - Highlight coverage and freshness metrics
   - If next_cursor exists → offer pagination

5. Return structured response:
   - Summary of findings
   - List of articles with snippets
   - Metadata (total found, coverage, freshness)
   - Next steps (pagination, refine query, etc.)

Guidelines:
- Be concise but informative
- Always show relevance_score to help user assess quality
- If coverage < 0.5, suggest expanding time window
- For pagination: use next_cursor to get more results
- Respect diagnostics.correlation_id for tracking

Example interaction:
User: "Find me news about AI regulation in EU"
SearchAgent:
1. Call retrieve(query="AI regulation EU", hours=24, k=10)
2. If empty → retry with hours=48
3. Present results with metadata
4. Suggest: "Want more results? I can search 72h or paginate."
```

---

## Шаг 4: Добавление GPT Action

### 4.1 В секции "Actions" нажмите "Create new action"

### 4.2 Импорт OpenAPI Schema

**Опция A: Импорт из URL (если у вас публичный доступ к файлу)**
- Укажите URL к `search_openapi.yaml` (если хостите на GitHub Pages/CDN)

**Опция B: Импорт из файла**
- Загрузите `api/search_openapi.yaml` напрямую

**Опция C: Скопировать схему вручную**

Скопируйте содержимое `api/search_openapi.yaml` и вставьте в редактор OpenAPI Schema.

**Ключевые поля для проверки:**

```yaml
servers:
  - url: https://rssnews-production-eaa2.up.railway.app
    description: Production (Railway Bot Service)

paths:
  /retrieve:
    post:
      operationId: retrieve
      summary: Retrieve news articles
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - query
              properties:
                query:
                  type: string
                hours:
                  type: integer
                  default: 24
                k:
                  type: integer
                  default: 10
                filters:
                  type: object
                cursor:
                  type: string
```

### 4.3 Authentication

На данный момент API **не требует аутентификации**.

Если хотите добавить аутентификацию в будущем:
- **Option 1**: API Key в header (`X-API-Key`)
- **Option 2**: Railway environment variable для проверки токена
- **Option 3**: Cloudflare Access (если перейдёте на CF Tunnel)

Пока выберите **"None"** в Authentication settings.

---

## Шаг 5: Тестирование GPT Action

### 5.1 Test в OpenAI Playground

В редакторе GPT Actions есть кнопка **"Test"**. Попробуйте:

**Test Request:**
```json
{
  "query": "climate change",
  "hours": 24,
  "k": 5
}
```

**Ожидаемый ответ:** JSON с массивом items.

### 5.2 Test с ChatGPT

После сохранения Custom GPT, протестируйте через ChatGPT:

```
User: Find me latest news about artificial intelligence
SearchAgent: [calls retrieve action] → shows results
```

---

## Шаг 6: Auto-Retry Logic

SearchAgent должен автоматически расширять окно поиска если нет результатов:

**Пример:**

1. Запрос: `hours=24` → пусто
2. Retry: `hours=48` → пусто
3. Retry: `hours=72` → нашлось 3 статьи
4. Возврат результатов пользователю

**Как это реализовать в System Prompt:**

Уже включено в промпт выше (см. пункт 3).

---

## Шаг 7: Pagination Support

Если `next_cursor` не null, SearchAgent может запросить следующую страницу:

**Пример:**

```
User: Show me more results
SearchAgent: [calls retrieve with cursor from previous response]
```

**Request:**
```json
{
  "query": "artificial intelligence",
  "hours": 24,
  "k": 10,
  "cursor": "eyJvZmZzZXQiOiAxMH0="
}
```

---

## Примеры использования

### Пример 1: Простой поиск

**User:** "Find news about Tesla"

**SearchAgent:**
1. Calls `retrieve(query="Tesla", hours=24, k=10)`
2. Returns:
   ```
   Found 10 articles about Tesla in the last 24 hours:

   1. Tesla Model Y refresh spotted... (theverge.com, 2h ago, score: 0.92)
   2. Elon Musk announces new factory... (reuters.com, 5h ago, score: 0.88)
   ...

   Coverage: 100%
   Median freshness: 4.2 hours

   Want more results or search further back?
   ```

### Пример 2: Auto-retry

**User:** "Find news about quantum computing in Chinese"

**SearchAgent:**
1. Calls `retrieve(query="quantum computing", hours=24, k=10, filters={lang: "zh"})`
2. Empty → retry `hours=48`
3. Empty → retry `hours=72`
4. Found 2 results → return

### Пример 3: Filtered search

**User:** "Show me AI news from BBC and Reuters only"

**SearchAgent:**
1. Calls `retrieve(query="AI", hours=24, k=10, filters={sources: ["bbc.com", "reuters.com"]})`
2. Returns filtered results

---

## Troubleshooting

### Problem: "Action failed to execute"

**Причина:** Railway service не отвечает или ошибка в API

**Решение:**
1. Проверьте Railway logs: `railway logs`
2. Проверьте health endpoint: `curl https://rssnews-production-eaa2.up.railway.app/health`
3. Проверьте PG_DSN в Railway variables

### Problem: Empty results always

**Причина:** База данных пустая или нет статей в указанном окне

**Решение:**
1. Проверьте наличие данных: `SELECT COUNT(*) FROM articles WHERE published_at > NOW() - INTERVAL '24 hours'`
2. Убедитесь что RSS polling работает (SERVICE_MODE=poll)
3. Увеличьте `hours` до 72

### Problem: Slow responses

**Причина:** Embedding generation или большой k

**Решение:**
1. Уменьшите `k` (default 10 → 5)
2. Добавьте Redis caching (если ещё не включен)
3. Оптимизируйте индексы в PostgreSQL

---

## Мониторинг

### Railway Logs

```bash
railway logs
```

Смотрите на:
- `/retrieve` requests
- Execution time
- Error messages

### Metrics

Из response можно отслеживать:
- **coverage**: % от запрошенного k (1.0 = все найдено)
- **freshness_stats.median_age_seconds**: насколько свежие статьи
- **diagnostics.total_results**: сколько всего найдено

---

## Next Steps

1. **Добавить аутентификацию**: API Key или Bearer token
2. **Rate limiting**: Ограничить запросы по IP/user
3. **Caching**: Кешировать популярные запросы
4. **Analytics**: Логировать популярные queries для улучшения

---

## Полезные ссылки

- **OpenAI GPT Actions Docs**: https://platform.openai.com/docs/actions
- **Railway Docs**: https://docs.railway.app
- **OpenAPI 3.1 Spec**: https://spec.openapis.org/oas/v3.1.0

---

## Поддержка

Если возникли проблемы:
1. Проверьте Railway deployment status
2. Проверьте logs через `railway logs`
3. Протестируйте `/retrieve` endpoint напрямую через curl
4. Проверьте OpenAPI schema в GPT Actions редакторе

**Production URL:**
https://rssnews-production-eaa2.up.railway.app/retrieve

**Status:** ✅ Live and operational

🎉 Готово! Теперь ваш SearchAgent готов к использованию через ChatGPT.
