# OpenAI GPT Actions - Пошаговая Инструкция

**API Endpoint:** `https://rssnews-production-eaa2.up.railway.app/retrieve`

**Note:** Используйте ваш OpenAI admin ключ для входа в платформу.

---

## Шаг 1: Открыть OpenAI Platform

Перейдите на: **https://platform.openai.com/playground/assistants**

Войдите с вашим API ключом (или обычный логин если у вас есть аккаунт).

---

## Шаг 2: Создать Custom GPT

1. Нажмите кнопку **"Create"** (или **"+ New Assistant"**)
2. Выберите **"Custom GPT"** или **"Assistants API"**

---

## Шаг 3: Заполнить Basic Information

**Name:**
```
SearchAgent
```

**Description:**
```
News search agent with access to RSS news database via /retrieve API
```

**Model:** (выберите доступную модель, например `gpt-4` или `gpt-4-turbo`)

---

## Шаг 4: Добавить Instructions (System Prompt)

В поле **"Instructions"** вставьте:

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

## Шаг 5: Добавить Action (GPT Action)

### 5.1 Найти секцию Actions

Прокрутите вниз до секции **"Actions"** или **"Tools"**.

### 5.2 Нажать "Create new action"

Или **"Add Action"** / **"+ Action"**.

### 5.3 Выбрать метод импорта

**Опция A: Import from URL** (если есть)
- Укажите URL: `https://raw.githubusercontent.com/langgraphsystem/rssnews/main/api/search_openapi.yaml`

**Опция B: Import from file**
- Нажмите **"Import from file"**
- Загрузите файл: `D:\Программы\rss\rssnews\api\search_openapi.yaml`

**Опция C: Paste schema** (самый надёжный)
- Нажмите **"Schema"** или **"OpenAPI Schema"**
- Скопируйте содержимое файла `api/search_openapi.yaml` полностью
- Вставьте в редактор

### 5.4 OpenAPI Schema (если копируете вручную)

Откройте файл `D:\Программы\rss\rssnews\api\search_openapi.yaml` и скопируйте **весь** его содержимое.

**Важные поля для проверки после импорта:**

```yaml
servers:
  - url: https://rssnews-production-eaa2.up.railway.app
    description: Production (Railway Bot Service)

paths:
  /retrieve:
    post:
      operationId: retrieve
```

---

## Шаг 6: Authentication Settings

### 6.1 В секции Authentication выберите:

**"None"** (No Authentication)

*Примечание: Ваш API сейчас публичный, аутентификация не требуется.*

### 6.2 (Опционально) Если хотите добавить API Key позже:

- Выберите **"API Key"**
- Header name: `X-API-Key`
- Значение: (ваш секретный ключ)

Но пока оставьте **None**.

---

## Шаг 7: Проверить Privacy Settings

- **Privacy**: Можете выбрать "Only me" или "Anyone with the link"
- **Capabilities**: Убедитесь что Actions/Tools включены

---

## Шаг 8: Save Assistant

Нажмите **"Save"** или **"Create"** в верхнем правом углу.

---

## Шаг 9: Test в Playground

### 9.1 В OpenAI Playground (справа от редактора)

Введите тестовый запрос:

```
Find me news about artificial intelligence from last 24 hours
```

### 9.2 Ожидаемое поведение:

1. SearchAgent должен вызвать action `retrieve`
2. Передать параметры: `{"query": "artificial intelligence", "hours": 24, "k": 10}`
3. Получить ответ с articles
4. Отформатировать и показать вам результаты

### 9.3 Проверить в логах:

Вы должны увидеть:
- **Tool calls:** `retrieve`
- **Request:** JSON с query
- **Response:** JSON с items

---

## Шаг 10: Test Auto-Retry Logic

Попробуйте очень специфичный запрос:

```
Find me news about "quantum blockchain AI metaverse" from last 24 hours
```

**Ожидаемое поведение:**
1. Первый вызов: `hours=24` → вероятно пусто
2. Второй вызов: `hours=48` → может быть пусто
3. Третий вызов: `hours=72` → может быть результаты или пусто
4. Сообщение: "No results found" если всё пусто

---

## Шаг 11: Test Pagination

```
Find me 3 news articles about "news", then show me more
```

**Ожидаемое поведение:**
1. Первый вызов: `k=3` → возвращает 3 статьи + `next_cursor`
2. Вы говорите "show me more"
3. Второй вызов: тот же query + `cursor` из предыдущего ответа
4. Возвращает следующие 3 статьи

---

## Шаг 12: Publish (опционально)

Если хотите поделиться:

1. Нажмите **"Publish"** или **"Share"**
2. Выберите:
   - **"Only me"** - только вы
   - **"Anyone with link"** - все у кого есть ссылка
   - **"Public"** - публично в GPT Store

3. Скопируйте ссылку и поделитесь

---

## Troubleshooting

### Problem: "Action failed to execute"

**Решение:**
1. Проверьте что API работает: `curl https://rssnews-production-eaa2.up.railway.app/health`
2. Проверьте Railway logs: `railway logs`
3. Убедитесь что OpenAPI schema корректна

### Problem: "Invalid schema"

**Решение:**
1. Проверьте что скопировали **весь** файл `search_openapi.yaml`
2. Убедитесь что формат YAML корректен (без лишних символов)
3. Попробуйте валидатор: https://editor.swagger.io/

### Problem: GPT не вызывает action

**Решение:**
1. Проверьте что `operationId: retrieve` указан в schema
2. Проверьте Instructions - убедитесь что упоминается "call retrieve action"
3. Попробуйте явно попросить: "Use the retrieve action to find..."

### Problem: Empty results

**Решение:**
1. Проверьте что в базе данных есть статьи: `SELECT COUNT(*) FROM articles`
2. Попробуйте расширить окно: `hours=72`
3. Попробуйте более общий query: "news" вместо конкретной темы

---

## Проверка Что Всё Работает

### ✅ Checklist:

- [ ] Assistant создан с именем "SearchAgent"
- [ ] Instructions скопированы полностью
- [ ] Action добавлен с OpenAPI schema
- [ ] Authentication = None
- [ ] Test в Playground прошёл успешно
- [ ] Action вызывается и возвращает результаты
- [ ] Auto-retry работает (тест с редким query)
- [ ] Pagination работает (тест с next_cursor)

---

## Полезные Ссылки

- **OpenAI Assistants API Docs:** https://platform.openai.com/docs/assistants
- **GPT Actions Guide:** https://platform.openai.com/docs/actions
- **Swagger Editor (OpenAPI validator):** https://editor.swagger.io/

- **API Endpoint:** https://rssnews-production-eaa2.up.railway.app/retrieve
- **Health Check:** https://rssnews-production-eaa2.up.railway.app/health
- **OpenAPI Schema:** `D:\Программы\rss\rssnews\api\search_openapi.yaml`

---

## После Настройки

Вы можете использовать SearchAgent через:

1. **OpenAI Playground** - для тестирования
2. **ChatGPT** - если published
3. **API calls** - через Assistants API

**Примеры запросов:**

```
Find me latest AI news
Show me technology news from BBC and Reuters
Search for climate change articles from last week
Find news about Tesla
```

---

## Следующие Шаги (опционально)

1. **Добавить аутентификацию** - API Key для защиты
2. **Rate limiting** - ограничить количество запросов
3. **Мониторинг** - логировать все queries
4. **Analytics** - отслеживать популярные темы

---

**Status:** ✅ Ready to configure

**API Endpoint:** https://rssnews-production-eaa2.up.railway.app/retrieve

**Good luck!** 🚀
