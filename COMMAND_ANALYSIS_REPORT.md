# Полный анализ команд Telegram бота

**Дата:** 2025-10-05 01:44:04

## Статистика

- Всего команд: 11
- Успешных тестов: 0
- С ошибками: 11

## Детали

### /search

**Тестовый запрос:** AI technology

**Таблицы БД:** article_chunks, articles

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_search_command
- Code location: line 504
- Direct: RankingAPI

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /trends

**Тестовый запрос:** None

**Таблицы БД:** article_chunks, articles

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_trends_command
- Code location: line 660
- Orchestrator: execute_trends_command
- Direct: RankingAPI

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /analyze

**Тестовый запрос:** artificial intelligence

**Таблицы БД:** article_chunks, articles

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_analyze_command
- Code location: line 1224
- Orchestrator: execute_analyze_command

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /ask

**Тестовый запрос:** What is happening with AI?

**Таблицы БД:** article_chunks, articles

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_ask_command
- Code location: line 605
- Direct: RankingAPI

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /summarize

**Тестовый запрос:** latest AI news

**Таблицы БД:** articles, article_chunks

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_summarize_command
- Code location: line 1738

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /aggregate

**Тестовый запрос:** None

**Таблицы БД:** articles

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_aggregate_command
- Code location: line 1842

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /filter

**Тестовый запрос:** None

**Таблицы БД:** articles

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_filter_command
- Code location: line 1934

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /insights

**Тестовый запрос:** AI trends

**Таблицы БД:** articles, article_chunks

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_insights_command
- Code location: line 2009

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /sentiment

**Тестовый запрос:** AI regulation

**Таблицы БД:** articles, article_chunks

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_sentiment_command
- Code location: line 2086

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /topics

**Тестовый запрос:** None

**Таблицы БД:** articles, article_chunks

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_topics_command
- Code location: line 2157

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

### /gpt

**Тестовый запрос:** explain quantum computing

**Таблицы БД:** articles, article_chunks

**Столбцы:** 

**Шаги обработки:**
- Handler: handle_gpt_command
- Code location: line 2234

**Ошибки:**
- ❌ Critical: ProductionDBClient.__init__() takes 1 positional argument but 2 were given

**Статус:** ⚠️ Needs Check

---

