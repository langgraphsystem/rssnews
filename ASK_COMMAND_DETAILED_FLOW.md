# Команда /ask - Подробное описание работы

**Дата:** 2025-10-05
**Версия:** Phase 3 Agentic RAG
**Архитектура:** Multi-agent iterative retrieval with self-correction

---

## 📋 Содержание

1. [Общий обзор](#общий-обзор)
2. [Пошаговый процесс](#пошаговый-процесс)
3. [Архитектура компонентов](#архитектура-компонентов)
4. [Детальный поток данных](#детальный-поток-данных)
5. [Примеры работы](#примеры-работы)
6. [Обработка ошибок](#обработка-ошибок)

---

## Общий обзор

### Что делает /ask?

Команда `/ask` - это **Agentic RAG** (Retrieval-Augmented Generation) система, которая:

- 📚 **Ищет** релевантные статьи в базе данных (semantic + keyword search)
- 🤖 **Анализирует** найденные документы с помощью LLM
- 🔄 **Итеративно улучшает** ответ через несколько раундов (depth=1/2/3)
- ✅ **Проверяет себя** (self-correction на depth=3)
- 📊 **Форматирует** ответ с источниками и датами

### Пример использования:

```
Пользователь → Telegram:
/ask What are the key arguments for and against TikTok divestiture?

Бот → Ответ:
🧠 Agentic RAG (depth=3): What are the key arguments...

**Arguments For Divestiture:**
• National security concerns...
• Bipartisan support...

**Arguments Against:**
• First Amendment concerns...
• Economic impact...

📊 Sources:
1. Trump's TikTok Deal... (Today, Oct 5)
2. Democrats' shutdown... (BBC, Oct 2)
```

---

## Пошаговый процесс

### Шаг 1: Получение запроса от пользователя (Telegram)

**Файл:** [bot_service/advanced_bot.py:1268](bot_service/advanced_bot.py#L1268)

```python
# Пользователь отправляет:
/ask What are the key arguments for TikTok divestiture? --depth=3

# Telegram bot получает команду
async def handle_ask_deep_command(self, chat_id: str, user_id: str, args: List[str]):
    # 1. Парсинг аргументов
    depth = 3  # из --depth=3
    query = "What are the key arguments for TikTok divestiture?"

    # 2. Отправка уведомления пользователю
    await self._send_message(chat_id, "🧠 Agentic RAG (depth=3): What are...")

    # 3. Вызов Phase3 Handler
    from services.phase3_handlers import execute_ask_command

    payload = await execute_ask_command(
        query=query,
        depth=depth,
        window="24h",
        lang="auto",
        k_final=5,
        correlation_id=f"ask-{user_id}"
    )
```

**Результат Шага 1:**
- ✅ Запрос распарсен
- ✅ Пользователь получил уведомление
- ⏭️  Переход к Phase3Handlers

---

### Шаг 2: Phase3 Handler подготовка контекста

**Файл:** [services/phase3_handlers.py:28](services/phase3_handlers.py#L28)

```python
class Phase3HandlerService:
    async def handle_ask_command(self, *, query: str, depth: int = 3, ...):
        # 1. Логирование запроса
        logger.info(f"[Phase3] /ask | query='{query[:50]}...' depth={depth}")

        # 2. Подготовка аргументов для Context Builder
        args_tokens = [
            'query="What are the key arguments..."',
            'window=24h',
            'lang=auto',
            'k=5',
            'depth=3'
        ]

        # 3. Вызов Context Builder
        context, error_payload = await self._build_context(
            raw_command="/ask",
            args_tokens=args_tokens,
            correlation_id=correlation_id,
            lang="auto",
            window="24h",
            k_final=5,
            max_tokens=8000,
            budget_cents=50,
            timeout_s=30
        )

        if error_payload:
            return error_payload  # Ошибка построения контекста

        # 4. Добавление depth в контекст
        context["params"]["depth"] = depth

        # 5. Выполнение через Orchestrator
        response_dict = await self.orchestrator.execute(context)

        # 6. Форматирование для Telegram
        payload = format_for_telegram(response_dict)

        return payload
```

**Результат Шага 2:**
- ✅ Аргументы подготовлены
- ⏭️  Вызов Context Builder

---

### Шаг 3: Context Builder - построение контекста

**Файл:** [core/context/phase3_context_builder.py:40](core/context/phase3_context_builder.py#L40)

```python
class Phase3ContextBuilder:
    async def build_context(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Валидация входа
        if not raw_input.get("raw_command"):
            return self._error_response("VALIDATION_FAILED", ...)

        # 2. Парсинг команды и аргументов
        command = self._normalize_command("/ask")  # → "ask"
        parsed_args = self._parse_args(args, command)

        # 3. Построение params
        params = self._build_params(parsed_args, defaults, user_lang)
        # params = {
        #     "query": "What are the key arguments...",
        #     "window": "24h",
        #     "lang": "auto",
        #     "k_final": 5,
        #     "sources": None,
        #     "flags": {"rerank_enabled": True}
        # }

        # 4. Построение models (маршрутизация к нужным LLM)
        models = self._build_models(command)
        # models = {
        #     "primary": "gpt-5",
        #     "fallback": ["gpt-5-mini", "gpt-3.5-turbo"]
        # }

        # 5. Построение limits (бюджет и таймауты)
        limits = self._build_limits(defaults)
        # limits = {
        #     "max_tokens": 8000,
        #     "budget_cents": 50,
        #     "timeout_s": 30
        # }

        # 6. КРИТИЧНО: Retrieval с auto-recovery
        retrieval, recovery_warnings = await self._perform_retrieval_with_recovery(
            params, feature_flags, correlation_id
        )

        if not retrieval["docs"]:
            return self._error_response(
                "NO_DATA",
                "No documents found for query",
                f"Retrieval returned 0 documents after auto-recovery attempts."
            )

        # 7. Корректировка k_final под реальное количество документов
        params["k_final"] = len(retrieval["docs"])

        # 8. Построение telemetry
        telemetry = {
            "correlation_id": correlation_id,
            "version": "phase3-orchestrator"
        }

        # 9. Итоговый контекст
        context = {
            "command": "ask",
            "params": params,
            "retrieval": retrieval,
            "graph": None,
            "memory": None,
            "models": models,
            "limits": limits,
            "telemetry": telemetry
        }

        return context
```

**Результат Шага 3:**
- ✅ Контекст построен
- ✅ 3-5 документов найдено (или ошибка NO_DATA)
- ⏭️  Передача в Orchestrator

---

### Шаг 3.1: Retrieval с Auto-Recovery (Критический подпроцесс)

**Файл:** [core/context/phase3_context_builder.py:348](core/context/phase3_context_builder.py#L348)

Это **самая важная часть** - поиск документов с автоматическим восстановлением.

```python
async def _perform_retrieval_with_recovery(self, params, feature_flags, correlation_id):
    warnings = []
    window = params["window"]  # "24h"
    lang = params["lang"]      # "auto"
    sources = params["sources"]  # None
    k_final = params["k_final"]  # 5
    rerank_enabled = params["flags"]["rerank_enabled"]  # True

    # Построение query
    query = self._build_retrieval_query(params)
    # query = "What are the key arguments for TikTok divestiture?"

    # === ATTEMPT 1: Normal retrieval ===
    docs = await self._retrieve_docs(
        query, window, lang, sources, k_final, rerank_enabled
    )

    if docs:
        return self._build_retrieval_dict(docs, ...), warnings

    # === AUTO-RECOVERY STARTS ===

    # STEP 1: Expand window (24h → 3d → 1w → 2w → 1m → 3m)
    if feature_flags.get("auto_expand_window", True):
        max_attempts = 5
        attempts = 0
        while not docs and attempts < max_attempts:
            new_window = WINDOW_EXPANSION.get(window, window)
            if new_window == window:
                break  # Cannot expand further

            window = new_window
            attempts += 1
            warnings.append(f"expanded window to {window}")

            docs = await self._retrieve_docs(query, window, ...)

            if docs:
                return self._build_retrieval_dict(docs, ...), warnings

    # STEP 2: Relax filters (lang → auto, sources → None)
    if feature_flags.get("relax_filters_on_empty", True):
        lang = "auto"
        sources = None
        warnings.append("relaxed lang to auto, removed source filters")

        docs = await self._retrieve_docs(query, window, ...)

        if docs:
            return self._build_retrieval_dict(docs, ...), warnings

    # STEP 3: Disable rerank and increase k_final
    if feature_flags.get("fallback_rerank_false_on_empty", True):
        rerank_enabled = False
        k_final = 10
        warnings.append("disabled rerank, increased k_final to 10")

        docs = await self._retrieve_docs(query, window, ...)

        if docs:
            return self._build_retrieval_dict(docs, ...), warnings

    # === ALL RECOVERY ATTEMPTS FAILED ===
    return self._build_retrieval_dict([], ...), warnings
```

**Результат Auto-Recovery:**
- ✅ Попытка 1: Обычный поиск (24h window)
- ⏭️  Попытка 2-6: Расширение окна (3d, 1w, 2w, 1m, 3m)
- ⏭️  Попытка 7: Релаксация фильтров
- ⏭️  Попытка 8: Отключение rerank
- ❌ Если все failed → возврат пустого списка

---

### Шаг 3.2: _retrieve_docs - Фактический поиск в БД

**Файл:** [core/context/phase3_context_builder.py:455](core/context/phase3_context_builder.py#L455)

```python
async def _retrieve_docs(self, query: str, window: str, lang: str, ...):
    try:
        # 1. Вызов RetrievalClient
        docs = await self.retrieval_client.retrieve(
            query=query,
            window=window,
            lang=lang,
            sources=sources,
            k_final=k_final,
            use_rerank=rerank_enabled
        )

        # 2. Очистка и валидация документов
        cleaned_docs = []
        for doc in docs:
            # Проверка required fields
            if not doc.get("title"):
                continue

            # Нормализация date
            date = doc.get("date")
            if not date or not self._is_valid_date(date):
                date = datetime.utcnow().strftime("%Y-%m-%d")

            # Trim snippet
            snippet = doc.get("snippet", "")[:240]

            cleaned_docs.append({
                "article_id": doc.get("article_id"),
                "title": doc.get("title", ""),
                "url": doc.get("url"),
                "date": date,
                "lang": doc_lang,
                "score": doc.get("score", 0.0),
                "snippet": snippet
            })

        return cleaned_docs

    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return []
```

**Внутри retrieval_client.retrieve():**

**Файл:** [core/rag/retrieval_client.py:76](core/rag/retrieval_client.py#L76)

```python
async def retrieve(self, query, window, lang, sources, k_final, use_rerank):
    # 1. Проверка кэша
    cache_key = self._build_cache_key(query, window, ...)
    cached = self._get_from_cache(cache_key)
    if cached:
        return cached

    # 2. Получение RankingAPI
    api = self._get_ranking_api()

    # 3. Вызов ranking_api.retrieve_for_analysis()
    results = await api.retrieve_for_analysis(
        query=query,
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        use_rerank=use_rerank
    )

    # 4. Кэширование
    if results:
        self._set_cache(cache_key, results)

    return results
```

**Внутри ranking_api.retrieve_for_analysis():**

**Файл:** [ranking_api.py:367](ranking_api.py#L367)

```python
async def retrieve_for_analysis(self, query, window, lang, sources, k_final, use_rerank):
    # 1. Парсинг time window
    window_hours = {"24h": 24, "3d": 72, "1w": 168, ...}.get(window, 24)

    # 2. Построение filters
    filters = {}
    if sources:
        filters['sources'] = sources
    if lang and lang != 'auto':
        filters['lang'] = lang

    # 3. Генерация query embedding
    query_normalized = self._normalize_query(query)
    query_embeddings = await self.embedding_generator.generate_embeddings([query_normalized])

    if not query_embeddings or not query_embeddings[0]:
        logger.warning("Failed to generate query embedding")
        return []

    query_embedding = query_embeddings[0]

    # 4. Hybrid search (semantic + FTS)
    results = await self.db.search_with_time_filter(
        query=query_normalized,
        query_embedding=query_embedding,
        hours=window_hours,
        limit=k_final * 2,  # Get more candidates
        filters=filters
    )

    # 5. Scoring
    if results:
        scored_results = self.scorer.score_and_rank(results, query)

        # 6. Deduplication (FIXED LSH)
        if len(scored_results) > 1:
            deduplicated = self.dedup_engine.canonicalize_articles(scored_results)
        else:
            deduplicated = scored_results

        # 7. Return top k_final
        return deduplicated[:k_final]

    return []
```

**Внутри db.search_with_time_filter():**

**Файл:** [database/production_db_client.py:622](database/production_db_client.py#L622)

```python
async def search_with_time_filter(self, query, query_embedding, hours, limit, filters):
    # 1. Конвертация embedding в pgvector формат
    vector_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

    # 2. Построение WHERE clauses
    where_clauses = ["ac.embedding_vector IS NOT NULL"]
    where_clauses.append("ac.published_at >= NOW() - (%s || ' hours')::interval")
    params = [vector_str, hours]

    # Добавление source filter
    if filters and filters.get('sources'):
        placeholders = ','.join(['%s'] * len(filters['sources']))
        where_clauses.append(f"ac.source_domain IN ({placeholders})")
        params.extend(filters['sources'])

    where_sql = " AND ".join(where_clauses)

    # 3. SQL запрос с pgvector косинусным расстоянием
    query_sql = f"""
        SELECT
            ac.id, ac.article_id, ac.chunk_index, ac.text,
            ac.url, ac.title_norm, ac.source_domain, ac.published_at,
            1 - (ac.embedding_vector <=> %s::vector) AS similarity
        FROM article_chunks ac
        WHERE {where_sql}
        ORDER BY ac.embedding_vector <=> %s::vector
        LIMIT %s
    """

    params.extend([vector_str, limit])

    # 4. Выполнение запроса
    cur.execute(query_sql, params)

    # 5. Формирование результатов
    results = []
    for row in cur.fetchall():
        results.append({
            'id': row[0],
            'article_id': row[1],
            'text': row[3],
            'url': row[4],
            'title_norm': row[5],
            'source_domain': row[6],
            'published_at': str(row[7]),
            'similarity': float(row[8]),
            'semantic_score': float(row[8]),
            'fts_score': 0.5
        })

    return results
```

**Результат поиска в БД:**
```python
[
    {
        'article_id': 32807,
        'title_norm': "Government Shutdown Enters 5th Day...",
        'text': "Trump's TikTok Deal Gives Control of Platform...",
        'url': "https://www.today.com/video/...",
        'published_at': "2025-10-05 12:42:36+00:00",
        'similarity': 0.581,
        'semantic_score': 0.581,
        'fts_score': 0.5
    },
    {
        'article_id': 32717,
        'title_norm': "Americast - Will the Democrats' shutdown gamble...",
        'text': "Donald Trump has reached a deal to transfer TikTok...",
        'url': "https://www.bbc.co.uk/sounds/play/...",
        'published_at': "2025-10-02 18:15:00+00:00",
        'similarity': 0.603,
        ...
    },
    {
        'article_id': 30440,
        'title_norm': "Is TikTok about to go full Maga? – podcast...",
        'text': "Emily Baker-White on the deal to transfer TikTok's US operations...",
        'url': "https://www.theguardian.com/news/audio/...",
        'published_at': "2025-10-03 02:00:21+00:00",
        'similarity': 0.569,
        ...
    }
]
```

---

### Шаг 4: Phase3 Orchestrator - Выполнение команды

**Файл:** [core/orchestrator/phase3_orchestrator_new.py:70](core/orchestrator/phase3_orchestrator_new.py#L70)

```python
class Phase3Orchestrator:
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        command = context.get("command", "")
        correlation_id = context.get("telemetry", {}).get("correlation_id")

        logger.info(f"[{correlation_id}] Executing Phase 3 command: {command}")

        try:
            # 1. Маршрутизация команды
            if command.startswith("/ask"):
                response = await self._handle_agentic(context)
            elif command.startswith("/events"):
                response = await self._handle_events(context)
            elif command.startswith("/graph"):
                response = await self._handle_graph(context)
            ...

            # 2. Санитизация evidence (PII masking, domain checks)
            if hasattr(response, 'evidence'):
                response.evidence = PIIMasker.sanitize_evidence(response.evidence)

            # 3. Валидация через policy layer
            self.validator.validate_response(response)

            logger.info(f"[{correlation_id}] Command completed successfully")
            return response.model_dump()

        except Exception as e:
            logger.error(f"[{correlation_id}] Command failed: {e}")
            return self._build_error_response(str(e), context)
```

---

### Шаг 4.1: Agentic RAG Agent - Итеративный анализ

**Файл:** [core/orchestrator/phase3_orchestrator_new.py:120](core/orchestrator/phase3_orchestrator_new.py#L120)

```python
async def _handle_agentic(self, context: Dict[str, Any]):
    # 1. Извлечение данных из контекста
    docs = context.get("retrieval", {}).get("docs", [])
    params = context.get("params", {})
    query = params.get("query") or "primary question"
    lang = params.get("lang", "en")
    window = context.get("retrieval", {}).get("window", "24h")

    # 2. Создание budget manager
    limits = context.get("limits", {})
    budget = create_budget_manager(
        max_tokens=limits.get("max_tokens", 8000),
        budget_cents=limits.get("budget_cents", 50),
        timeout_s=limits.get("timeout_s", 30)
    )

    # 3. Degradation если бюджет превышен
    depth = params.get("depth", 3)
    if budget.should_degrade():
        degraded = budget.get_degraded_params("/ask", {"depth": depth})
        depth = degraded.get("depth", 1)

    # 4. Выполнение Agentic RAG
    agentic_result, all_docs = await self.agentic_rag_agent.execute(
        query=query,
        initial_docs=docs,
        depth=depth,
        retrieval_fn=self._create_retrieval_fn(window, lang),
        budget_manager=budget,
        lang=lang,
        window=window
    )

    # 5. Форматирование ответа
    insights = [
        Insight(
            text=agentic_result.answer,
            confidence=agentic_result.confidence,
            rationale=agentic_result.reasoning,
            strength="high" if agentic_result.confidence > 0.8 else "medium"
        )
    ]

    # 6. Построение evidence из документов
    evidence = self._build_evidence_from_docs(all_docs)

    # 7. Построение итогового response
    return build_base_response(
        command="ask",
        insights=insights,
        evidence=evidence,
        lang=lang,
        meta=Meta(
            query=query,
            window=window,
            total_docs=len(all_docs),
            retrieval_depth=depth,
            model_used=agentic_result.model_used,
            correlation_id=context.get("telemetry", {}).get("correlation_id")
        )
    )
```

**Внутри agentic_rag_agent.execute():**

**Файл:** [core/agents/agentic_rag.py](core/agents/agentic_rag.py)

```python
async def execute(self, query, initial_docs, depth, retrieval_fn, budget_manager, lang, window):
    iterations = []
    current_docs = initial_docs
    all_docs = list(initial_docs)

    # === ITERATION 1 ===
    answer_1, reasoning_1, needs_more_1 = await self._analyze_and_answer(
        query=query,
        docs=current_docs,
        iteration=1,
        budget_manager=budget_manager,
        lang=lang
    )

    iterations.append({
        "iteration": 1,
        "answer": answer_1,
        "reasoning": reasoning_1,
        "needs_more_info": needs_more_1,
        "docs_used": len(current_docs)
    })

    if depth == 1:
        # Quick answer mode
        return self._build_result(answer_1, reasoning_1, iterations, all_docs)

    # === ITERATION 2 ===
    if needs_more_1:
        # Запросить дополнительные документы
        refined_query = await self._refine_query(query, answer_1, reasoning_1)
        new_docs = await retrieval_fn(refined_query, k=3)

        # Объединить с предыдущими
        current_docs = self._merge_docs(current_docs, new_docs)
        all_docs.extend(new_docs)

    answer_2, reasoning_2, needs_more_2 = await self._analyze_and_answer(
        query=query,
        docs=current_docs,
        iteration=2,
        budget_manager=budget_manager,
        lang=lang
    )

    iterations.append({
        "iteration": 2,
        "answer": answer_2,
        "reasoning": reasoning_2,
        "needs_more_info": needs_more_2,
        "docs_used": len(current_docs)
    })

    if depth == 2:
        # Standard mode
        return self._build_result(answer_2, reasoning_2, iterations, all_docs)

    # === ITERATION 3 (Self-correction) ===
    if needs_more_2:
        refined_query = await self._refine_query(query, answer_2, reasoning_2)
        new_docs = await retrieval_fn(refined_query, k=2)
        current_docs = self._merge_docs(current_docs, new_docs)
        all_docs.extend(new_docs)

    # Self-check: Compare iterations 1 and 2
    consistency_check = await self._check_consistency(answer_1, answer_2)

    if not consistency_check.is_consistent:
        # Re-analyze with all accumulated evidence
        answer_3, reasoning_3, _ = await self._analyze_and_answer(
            query=query,
            docs=current_docs,
            iteration=3,
            budget_manager=budget_manager,
            lang=lang,
            previous_answers=[answer_1, answer_2],
            consistency_issues=consistency_check.issues
        )
    else:
        answer_3 = answer_2
        reasoning_3 = reasoning_2 + " (Consistent with previous iteration)"

    iterations.append({
        "iteration": 3,
        "answer": answer_3,
        "reasoning": reasoning_3,
        "self_corrected": not consistency_check.is_consistent,
        "docs_used": len(current_docs)
    })

    # Deep mode - final answer
    return self._build_result(answer_3, reasoning_3, iterations, all_docs)
```

**Результат Agentic RAG:**
```python
{
    "answer": "**Arguments For TikTok Divestiture:**\n• National security concerns...\n\n**Arguments Against:**\n• First Amendment concerns...",
    "reasoning": "Based on analysis of 5 recent articles...",
    "confidence": 0.85,
    "iterations": [
        {"iteration": 1, "answer": "...", "docs_used": 3},
        {"iteration": 2, "answer": "...", "docs_used": 5},
        {"iteration": 3, "answer": "...", "docs_used": 5, "self_corrected": False}
    ],
    "model_used": "gpt-5",
    "all_docs": [...]
}
```

---

### Шаг 5: Форматирование для Telegram

**Файл:** [core/ux/formatter.py](core/ux/formatter.py)

```python
def format_for_telegram(response_dict: Dict[str, Any]) -> Dict[str, Any]:
    # 1. Извлечение данных
    command = response_dict.get("command", "")
    insights = response_dict.get("insights", [])
    evidence = response_dict.get("evidence", [])
    meta = response_dict.get("meta", {})

    # 2. Построение текста
    if command == "ask":
        text = "🧠 **Agentic RAG Result**\n\n"

        # Main answer
        if insights:
            text += insights[0].get("text", "")
            text += "\n\n"

        # Sources
        if evidence:
            text += "📊 **Sources:**\n"
            for i, ev in enumerate(evidence[:5], 1):
                title = ev.get("title", "")[:70]
                date = ev.get("date", "")
                url = ev.get("url", "")
                text += f"{i}. [{title}]({url})\n"
                text += f"   {date}\n"

        # Meta info
        if meta:
            text += f"\n🔍 Window: {meta.get('window', 'N/A')} | "
            text += f"Docs: {meta.get('total_docs', 0)} | "
            text += f"Depth: {meta.get('retrieval_depth', 1)}"

    return {
        "text": text,
        "buttons": None,
        "parse_mode": "Markdown"
    }
```

---

### Шаг 6: Отправка пользователю

**Файл:** [bot_service/advanced_bot.py:1315](bot_service/advanced_bot.py#L1315)

```python
# После получения payload
return await self._send_orchestrator_payload(chat_id, payload)

# _send_orchestrator_payload:
async def _send_orchestrator_payload(self, chat_id: str, payload: Dict[str, Any]):
    text = payload.get("text", "No response")
    buttons = payload.get("buttons")
    parse_mode = payload.get("parse_mode", "Markdown")

    # Отправка в Telegram
    if buttons:
        await self._send_message_with_buttons(chat_id, text, buttons, parse_mode)
    else:
        await self._send_message(chat_id, text, parse_mode=parse_mode)

    return True
```

**Пользователь получает:**

```
🧠 Agentic RAG Result

**Arguments For TikTok Divestiture:**
• National security concerns about Chinese government access to US user data
• Bipartisan Congressional support for restrictions
• Trump administration deal to transfer control to US media moguls

**Arguments Against:**
• First Amendment concerns about government ban on social media platform
• Economic impact on millions of content creators and businesses
• Questions about effectiveness if Chinese algorithm remains

📊 Sources:
1. [Trump's TikTok Deal Gives Control of Platform to Media Moguls](https://www.today.com/video/...)
   2025-10-05
2. [Americast - Will the Democrats' shutdown gamble pay off?](https://www.bbc.co.uk/sounds/...)
   2025-10-02
3. [Is TikTok about to go full Maga? – podcast](https://www.theguardian.com/news/audio/...)
   2025-10-03

🔍 Window: 24h | Docs: 5 | Depth: 3
```

---

## Архитектура компонентов

### Визуальная схема:

```
┌────────────────────────────────────────────────────────────────┐
│                          TELEGRAM                               │
│                     User: /ask TikTok?                          │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                    AdvancedRSSBot                               │
│           [bot_service/advanced_bot.py]                         │
│                                                                  │
│  • Parse command and arguments                                  │
│  • Send "🧠 Processing..." notification                         │
│  • Call Phase3Handlers                                          │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                  Phase3HandlerService                           │
│           [services/phase3_handlers.py]                         │
│                                                                  │
│  • Prepare args tokens                                          │
│  • Call Phase3ContextBuilder                                    │
│  • Add depth parameter                                          │
│  • Execute via Orchestrator                                     │
│  • Format response for Telegram                                 │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                Phase3ContextBuilder                             │
│      [core/context/phase3_context_builder.py]                  │
│                                                                  │
│  Step 1: Validate & parse command                               │
│  Step 2: Build params (query, window, lang, k_final)            │
│  Step 3: Build models routing (gpt-5, fallbacks)               │
│  Step 4: Build limits (tokens, budget, timeout)                 │
│  Step 5: *** RETRIEVAL WITH AUTO-RECOVERY ***                   │
│     ├─ Normal retrieval (24h)                                   │
│     ├─ Expand window (3d, 1w, 2w, 1m, 3m)                       │
│     ├─ Relax filters (lang=auto, sources=None)                  │
│     └─ Disable rerank, increase k                               │
│  Step 6: Validate docs found                                    │
│  Step 7: Build final context                                    │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                    RetrievalClient                              │
│            [core/rag/retrieval_client.py]                      │
│                                                                  │
│  • Check cache                                                  │
│  • Call RankingAPI.retrieve_for_analysis()                      │
│  • Cache results                                                │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                      RankingAPI                                 │
│                 [ranking_api.py]                                │
│                                                                  │
│  Step 1: Parse time window (24h → 24 hours)                     │
│  Step 2: Build filters (sources, lang)                          │
│  Step 3: Generate query embedding (OpenAI/Local)                │
│  Step 4: Search with time filter (hybrid search)                │
│  Step 5: Score and rank results                                 │
│  Step 6: *** DEDUPLICATION (LSH) ***                            │
│  Step 7: Return top k_final                                     │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                ProductionDBClient                               │
│        [database/production_db_client.py]                      │
│                                                                  │
│  *** POSTGRESQL QUERY ***                                       │
│  SELECT ... FROM article_chunks                                 │
│  WHERE embedding_vector IS NOT NULL                             │
│    AND published_at >= NOW() - '24 hours'::interval             │
│  ORDER BY embedding_vector <=> query_vector                     │
│  LIMIT 10                                                       │
│                                                                  │
│  Returns: 3-5 chunks with similarity scores                     │
└────────────────────┬───────────────────────────────────────────┘
                     │
      ┌──────────────┴──────────────┐
      │                             │
      ↓                             ↓
┌─────────────┐            ┌──────────────┐
│  pgvector   │            │ embeddings   │
│   Index     │            │  (3072-dim)  │
│   (HNSW)    │            │   OpenAI     │
└─────────────┘            └──────────────┘

Results: [
  {article_id: 32807, similarity: 0.581, text: "Trump's TikTok..."},
  {article_id: 32717, similarity: 0.603, text: "Donald Trump..."},
  {article_id: 30440, similarity: 0.569, text: "Emily Baker..."}
]
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                 Phase3Orchestrator                              │
│      [core/orchestrator/phase3_orchestrator_new.py]            │
│                                                                  │
│  • Route to _handle_agentic()                                   │
│  • Create budget manager                                        │
│  • Execute Agentic RAG Agent                                    │
│  • Sanitize evidence (PII masking)                              │
│  • Validate response                                            │
│  • Return formatted response                                    │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                  AgenticRAGAgent                                │
│              [core/agents/agentic_rag.py]                      │
│                                                                  │
│  ITERATION 1 (depth >= 1):                                      │
│    ├─ Analyze initial docs (3-5 chunks)                         │
│    ├─ Generate answer_1 + reasoning_1                           │
│    └─ Check if needs_more_info                                  │
│                                                                  │
│  ITERATION 2 (depth >= 2):                                      │
│    ├─ Refine query if needed                                    │
│    ├─ Retrieve additional docs (2-3 more)                       │
│    ├─ Analyze all docs (5-8 chunks total)                       │
│    ├─ Generate answer_2 + reasoning_2                           │
│    └─ Check if needs_more_info                                  │
│                                                                  │
│  ITERATION 3 (depth = 3):                                       │
│    ├─ Refine query if needed                                    │
│    ├─ Retrieve final docs if needed                             │
│    ├─ *** SELF-CORRECTION ***                                   │
│    │   └─ Check consistency(answer_1, answer_2)                 │
│    ├─ Re-analyze if inconsistent                                │
│    └─ Generate final answer_3 + reasoning_3                     │
│                                                                  │
│  Return:                                                        │
│    • Final answer (markdown formatted)                          │
│    • Reasoning chain                                            │
│    • Confidence score (0.0-1.0)                                 │
│    • All documents used (5-10 chunks)                           │
│    • Model used (gpt-5)                                        │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                      Formatter                                  │
│              [core/ux/formatter.py]                            │
│                                                                  │
│  • Format insights (answer text)                                │
│  • Format evidence (sources with dates)                         │
│  • Add metadata (window, docs count, depth)                     │
│  • Build Telegram payload (text + markdown)                     │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────────┐
│                       TELEGRAM                                  │
│                    User receives:                               │
│                                                                  │
│  🧠 Agentic RAG Result                                          │
│                                                                  │
│  **Arguments For TikTok Divestiture:**                          │
│  • National security concerns...                                │
│  • Bipartisan support...                                        │
│                                                                  │
│  **Arguments Against:**                                         │
│  • First Amendment concerns...                                  │
│  • Economic impact...                                           │
│                                                                  │
│  📊 Sources:                                                    │
│  1. Trump's TikTok Deal... (Oct 5)                              │
│  2. Democrats' shutdown... (Oct 2)                              │
│  3. TikTok full Maga?... (Oct 3)                                │
│                                                                  │
│  🔍 Window: 24h | Docs: 5 | Depth: 3                            │
└────────────────────────────────────────────────────────────────┘
```

---

## Обработка ошибок

### Ошибка 1: No documents found

**Когда:** Retrieval не находит документов даже после auto-recovery

**Сообщение:**
```
❌ Phase 3 context builder error

No documents found for query
Retrieval returned 0 documents after auto-recovery attempts.
Window=3m, lang=auto, sources=None.
Steps: expanded window to 3d, expanded window to 1w, ..., increased k_final to 10
```

**Причины:**
- Нет статей по теме в базе данных
- Слишком узкий временной интервал
- Проблемы с embeddings (не сгенерированы)
- LSH deduplication ошибка (FIXED)

**Решение:**
- Auto-recovery расширяет окно до 3 месяцев
- Релаксирует фильтры (lang, sources)
- Отключает rerank
- Если все равно пусто → возвращает error

---

### Ошибка 2: LSH duplicate key (FIXED)

**Было:**
```
ValueError: The given key already exists
```

**Причина:** Article ID вставлялся в LSH дважды

**Исправлено:** [ASK_COMMAND_LSH_FIX.md](ASK_COMMAND_LSH_FIX.md)

---

### Ошибка 3: Budget exceeded

**Когда:** LLM запросы превышают бюджет (50 центов)

**Действие:**
- Budget manager деградирует параметры
- depth 3 → 2 → 1
- Продолжает работу с упрощенным режимом

---

### Ошибка 4: Timeout

**Когда:** Операция превышает таймаут (30 секунд)

**Действие:**
- Возвращает partial результат если есть
- Или error message

---

## Связанные файлы

### Core Files:
1. [bot_service/advanced_bot.py:1268](bot_service/advanced_bot.py#L1268) - Telegram handler
2. [services/phase3_handlers.py:28](services/phase3_handlers.py#L28) - Phase3 handler
3. [core/context/phase3_context_builder.py:40](core/context/phase3_context_builder.py#L40) - Context builder
4. [core/rag/retrieval_client.py:76](core/rag/retrieval_client.py#L76) - Retrieval client
5. [ranking_api.py:367](ranking_api.py#L367) - Ranking API
6. [database/production_db_client.py:622](database/production_db_client.py#L622) - Database client
7. [core/orchestrator/phase3_orchestrator_new.py:70](core/orchestrator/phase3_orchestrator_new.py#L70) - Orchestrator
8. [core/agents/agentic_rag.py](core/agents/agentic_rag.py) - Agentic RAG agent
9. [core/ux/formatter.py](core/ux/formatter.py) - Formatter

### Supporting Files:
10. [ranking_service/deduplication.py](ranking_service/deduplication.py) - LSH deduplication
11. [core/models/model_router.py](core/models/model_router.py) - Model routing
12. [core/models/budget_manager.py](core/models/budget_manager.py) - Budget management

---

**Последнее обновление:** 2025-10-05
**Автор:** Claude Code Agent
**Статус:** ✅ Production Ready
