# Phase 3 Implementation — Gap Analysis Report

**Date:** 2025-09-30
**Status:** Partial Implementation
**Version:** Phase 3 Gap Analysis v1.0

---

## 📋 Executive Summary

Phase 3 промт описывает полнофункциональный оркестратор с **Agentic RAG, GraphRAG, Event Linking, Long-term Memory и расширенным Synthesis**. В кодовой базе существует **базовая реализация** ([phase3_orchestrator.py](../core/orchestrator/phase3_orchestrator.py)), которая покрывает **структурные аспекты (схемы, ответы)**, но **отсутствует интеллектуальная логика** (итеративный ретрив, граф знаний, память, причинность).

**Текущая реализация: ~30% от промпта**

---

## ✅ Что РЕАЛИЗОВАНО

### 1. Схемы (100% готовы)

**Файл:** [schemas/analysis_schemas.py](../schemas/analysis_schemas.py)

Все требуемые схемы для Phase 3 **полностью реализованы** и соответствуют промпту:

| Схема | Статус | Комментарий |
|-------|--------|-------------|
| `AgenticResult` | ✅ | `steps`, `answer`, `followups` |
| `AgenticStep` | ✅ | `iteration`, `query`, `n_docs`, `reason` |
| `EventsResult` | ✅ | `events`, `timeline`, `causal_links` |
| `EventRecord` | ✅ | `id`, `title`, `ts_range`, `entities`, `docs` |
| `TimelineRelation` | ✅ | `event_id`, `position`, `ref_event_id` |
| `CausalLink` | ✅ | `cause_event_id`, `effect_event_id`, `confidence`, `evidence_refs` |
| `GraphResult` | ✅ | `subgraph`, `paths`, `answer` |
| `GraphNode` | ✅ | `id`, `label`, `type` |
| `GraphEdge` | ✅ | `src`, `tgt`, `type`, `weight` |
| `GraphPath` | ✅ | `nodes`, `hops`, `score` |
| `MemoryResult` | ✅ | `operation`, `suggestions`, `to_store`, `records` |
| `MemorySuggestion` | ✅ | `type`, `content`, `importance`, `ttl_days` |
| `MemoryStoreItem` | ✅ | `type`, `content`, `refs`, `ttl_days` |
| `MemoryRecord` | ✅ | `id`, `type`, `content`, `ts`, `refs` |
| `SynthesisResult` | ✅ | `summary`, `conflicts`, `actions` (Phase 2) |

**Валидация:**
- ✅ Ограничения длин (`tldr ≤ 220`, `insight ≤ 180`, `snippet ≤ 240`)
- ✅ Evidence-required (`≥1 evidence_ref` для каждого insight)
- ✅ Enum для `type`, `position`, `operation`, etc.
- ✅ Date pattern (`YYYY-MM-DD`)
- ✅ Confidence range (`0.0..1.0`)

---

### 2. Orchestrator Handlers (50% готовы)

**Файл:** [core/orchestrator/phase3_orchestrator.py](../core/orchestrator/phase3_orchestrator.py)

| Команда | Обработчик | Статус | Комментарий |
|---------|-----------|--------|-------------|
| `/ask --depth=deep` | `_handle_agentic()` | 🟡 Частично | Заглушка: создаёт шаги, но **НЕТ итеративного ретрива, self-check, reformulation** |
| `/events link` | `_handle_events()` | 🟡 Частично | Заглушка: строит таймлайн/causal_links, но **НЕТ NER, group by time, causal reasoning** |
| `/graph query` | `_handle_graph()` | 🟡 Частично | Заглушка: строит мини-граф, но **НЕТ on-demand graph construction, hop traversal, NER→relations** |
| `/memory *` | `_handle_memory()` | 🟡 Частично | Заглушка: разбирает operation, но **НЕТ БД для памяти, embeddings, semantic search** |
| `/synthesize` | `_handle_synthesis()` | 🟡 Частично | Базовая логика из Phase 2, но **НЕТ cross-agent merge, конфликт-детекции** |

**Текущая логика:**
- Обработчики генерируют **валидный JSON** с правильной структурой
- Используют `retrieval.docs` (статический список)
- Создают **моковые данные** для `steps`, `events`, `nodes/edges`, `memory records`
- Возвращают `BaseAnalysisResponse` с `result` секцией

**Отсутствует:**
- Интеллектуальная логика (см. раздел "Что НЕ реализовано")
- Интеграция с моделями (GPT-5, Claude 4.5, Gemini 2.5 Pro)
- Fallback/QC chains
- Budget degradation

---

### 3. Базовая интеграция

**Файл:** [services/orchestrator.py](../services/orchestrator.py)

- ✅ Singleton для `Phase3Orchestrator` (`get_phase3_orchestrator()`)
- ✅ Точка входа `execute_phase3_context(context: Dict[str, Any])`
- ⚠️ **НЕТ** bot-level handlers для `/ask`, `/events`, `/graph`, `/memory` (только для Phase 1/2 команд)

---

## ❌ Что НЕ РЕАЛИЗОВАНО

### 1. Agentic RAG (/ask --depth=deep) — 70% отсутствует

**Отсутствует в [`_handle_agentic()`](../core/orchestrator/phase3_orchestrator.py:152):**

| Требование промпта | Текущая реализация | Статус |
|-------------------|-------------------|--------|
| ❌ Итеративная петля (≤3 итерации) | Создаёт 3 моковых шага без реальных итераций | **НЕ РЕАЛИЗОВАНО** |
| ❌ Reformulation (multi-facet queries) | Нет логики разложения на подзапросы | **НЕ РЕАЛИЗОВАНО** |
| ❌ Self-check (проверка выводов на evidence) | Нет проверки согласованности | **НЕ РЕАЛИЗОВАНО** |
| ❌ Повторный ретрив при недостаточности | Использует статический `docs` | **НЕ РЕАЛИЗОВАНО** |
| ❌ Синтез с ссылками на подзапросы | Просто объединяет title из docs | **НЕ РЕАЛИЗОВАНО** |
| ❌ Model routing (GPT-5 → Claude 4.5 → Gemini) | Нет вызовов моделей | **НЕ РЕАЛИЗОВАНО** |

**Нужно реализовать:**
1. **Iterative loop:**
   ```python
   for iteration in range(1, depth+1):
       # 1. Evaluate sufficiency
       # 2. Reformulate query if needed
       # 3. Re-retrieve with new query
       # 4. Self-check: validate claims against evidence
       # 5. Stop if sufficient or budget exhausted
   ```

2. **Model integration:**
   ```python
   async def _call_model(query, docs, model_config):
       # Try primary (GPT-5)
       # Fallback to Claude 4.5
       # QC with Gemini 2.5 Pro
   ```

3. **Budget tracking:**
   - Track tokens/cost per iteration
   - Degrade to 1 iteration if budget low

---

### 2. Event Linking (/events link) — 80% отсутствует

**Отсутствует в [`_handle_events()`](../core/orchestrator/phase3_orchestrator.py:200):**

| Требование промпта | Текущая реализация | Статус |
|-------------------|-------------------|--------|
| ❌ NER (Named Entity Recognition) | Использует `title.split()` вместо NER | **НЕ РЕАЛИЗОВАНО** |
| ❌ Группировка по временным окнам | Создаёт события по 1 на документ | **НЕ РЕАЛИЗОВАНО** |
| ❌ Причинно-следственный reasoning | Линейно связывает события без анализа | **НЕ РЕАЛИЗОВАНО** |
| ❌ Разрывы и альтернативные трактовки | Нет логики gap detection | **НЕ РЕАЛИЗОВАНО** |
| ❌ Model routing (GPT-5 + Gemini + Claude) | Нет вызовов моделей | **НЕ РЕАЛИЗОВАНО** |

**Нужно реализовать:**
1. **NER extraction:**
   ```python
   # Extract entities from docs using NER model
   entities = await extract_entities(docs)
   ```

2. **Time-based clustering:**
   ```python
   # Group events by time windows (6h, 12h, etc.)
   events = cluster_by_time(entities, window="12h")
   ```

3. **Causal reasoning:**
   ```python
   # Detect cause→effect with evidence
   causal_links = await infer_causality(events, docs, model=gpt5)
   ```

4. **Gap detection:**
   ```python
   # Identify missing links or alternative interpretations
   gaps = detect_timeline_gaps(events)
   ```

---

### 3. GraphRAG (/graph query) — 90% отсутствует

**Отсутствует в [`_handle_graph()`](../core/orchestrator/phase3_orchestrator.py:266):**

| Требование промпта | Текущая реализация | Статус |
|-------------------|-------------------|--------|
| ❌ On-demand graph construction | Создаёт моковый граф из docs | **НЕ РЕАЛИЗОВАНО** |
| ❌ NER → relations → nodes/edges | Нет NER, все связи типа `relates_to` | **НЕ РЕАЛИЗОВАНО** |
| ❌ Graph traversal (hop_limit ≤4) | Нет траверса, только линейные пути | **НЕ РЕАЛИЗОВАНО** |
| ❌ Subgraph extraction + supporting passages | Не выделяет подграф под запрос | **НЕ РЕАЛИЗОВАНО** |
| ❌ Конфликты источников | Нет логики conflict detection | **НЕ РЕАЛИЗОВАНО** |
| ❌ Build policy (on_demand / cached_only) | Нет кэша графов | **НЕ РЕАЛИЗОВАНО** |
| ❌ Limits (max_nodes=200, max_edges=600) | Нет ограничений на построение | **НЕ РЕАЛИЗОВАНО** |
| ❌ Model routing (Claude 4.5 → GPT-5 → Gemini) | Нет вызовов моделей | **НЕ РЕАЛИЗОВАНО** |

**Нужно реализовать:**
1. **Graph construction:**
   ```python
   if graph.enabled and build_policy == "on_demand":
       # NER on docs
       entities = extract_entities(docs)
       # Extract relations
       relations = extract_relations(docs, entities)
       # Build graph: nodes = entities, edges = relations
       graph = build_knowledge_graph(entities, relations, max_nodes=200, max_edges=600)
   ```

2. **Query parsing:**
   ```python
   # Parse query → extract entities/constraints/time
   query_entities = parse_query(query)
   ```

3. **Traversal:**
   ```python
   # Traverse graph up to hop_limit
   subgraph = traverse_graph(graph, start_nodes=query_entities, hop_limit=3)
   # Find paths
   paths = find_paths(subgraph, max_paths=10)
   ```

4. **Supporting passages:**
   ```python
   # Link nodes/edges to docs
   supporting_docs = map_nodes_to_docs(subgraph, docs)
   ```

5. **Conflict detection:**
   ```python
   # Detect conflicting edges (e.g., different weights/types for same relation)
   conflicts = detect_graph_conflicts(subgraph, docs)
   ```

---

### 4. Long-term Memory (/memory) — 95% отсутствует

**Отсутствует в [`_handle_memory()`](../core/orchestrator/phase3_orchestrator.py:382):**

| Требование промпта | Текущая реализация | Статус |
|-------------------|-------------------|--------|
| ❌ База данных для памяти | Нет БД/таблиц для хранения | **НЕ РЕАЛИЗОВАНО** |
| ❌ Embeddings для семантической памяти | Нет embeddings | **НЕ РЕАЛИЗОВАНО** |
| ❌ Semantic search (recall) | Возвращает моковые записи из docs | **НЕ РЕАЛИЗОВАНО** |
| ❌ PII filtering на `suggest`/`store` | Нет фильтрации PII | **НЕ РЕАЛИЗОВАНО** |
| ❌ TTL expiration | Нет логики TTL | **НЕ РЕАЛИЗОВАНО** |
| ❌ Importance scoring | Использует `doc.score` вместо важности | **НЕ РЕАЛИЗОВАНО** |
| ❌ Model routing (Gemini → GPT-5) | Нет вызовов моделей | **НЕ РЕАЛИЗОВАНО** |

**Нужно реализовать:**
1. **Database schema:**
   ```sql
   CREATE TABLE memory_records (
       id UUID PRIMARY KEY,
       type VARCHAR(20),  -- episodic | semantic
       content TEXT,
       embedding VECTOR(1536),
       ts TIMESTAMP,
       refs TEXT[],
       ttl_days INT,
       created_at TIMESTAMP
   );
   ```

2. **Suggest operation:**
   ```python
   async def suggest_memory(docs, model):
       # Filter PII
       clean_docs = filter_pii(docs)
       # Score importance
       suggestions = await model.score_importance(clean_docs)
       return suggestions
   ```

3. **Store operation:**
   ```python
   async def store_memory(items, db):
       for item in items:
           embedding = await get_embedding(item.content)
           await db.insert(item, embedding)
   ```

4. **Recall operation:**
   ```python
   async def recall_memory(query, db):
       query_emb = await get_embedding(query)
       records = await db.semantic_search(query_emb, top_k=10)
       # Filter by TTL
       valid_records = filter_by_ttl(records)
       return valid_records
   ```

---

### 5. Retrieval — Hybrid RAG (60% отсутствует)

**Файл:** [core/rag/retrieval_client.py](../core/rag/retrieval_client.py)

**Есть:**
- ✅ Гибридный ретрив (RRF + rerank) через `ranking_api.retrieve_for_analysis()`
- ✅ Кэширование (5 min TTL)
- ✅ Фильтры: `window`, `lang`, `sources`, `k_final`

**Отсутствует:**
- ❌ Интеграция с итеративным ретривом (Agentic RAG)
- ❌ Поддержка reformulation (query expansion)
- ❌ Graph-aware retrieval (для GraphRAG)
- ❌ Memory-aware retrieval (для `/memory recall`)

**Нужно добавить:**
```python
async def retrieve_for_agentic(
    self,
    queries: List[str],  # Multiple queries from reformulation
    iteration: int,
    budget_remaining: int
) -> List[Dict[str, Any]]:
    # Merge results from multiple queries
    # Track budget
    # Deduplicate
    pass
```

---

### 6. Model Integration — 100% отсутствует

**Критическое отсутствие:**
- ❌ Нет вызовов LLM моделей в `phase3_orchestrator.py`
- ❌ Нет routing logic (primary → fallback → QC)
- ❌ Нет budget tracking (tokens/cost per command)
- ❌ Нет timeout handling

**Требования промпта (раздел "РОУТИНГ (Phase 3)"):**

| Команда | Primary | Fallback 1 | Fallback 2 | Timeout |
|---------|---------|------------|------------|---------|
| `/ask` | GPT-5 | Claude 4.5 | Gemini 2.5 Pro (QC) | 15s |
| `/events` | GPT-5 (causal) | Gemini 2.5 Pro (struct) | Claude 4.5 | 18s |
| `/graph` | Claude 4.5 (long ctx) | GPT-5 (reasoning) | Gemini 2.5 Pro (QC) | 20s |
| `/memory` | Gemini 2.5 Pro (struct) | GPT-5 (QC) | - | 12s |
| `/synthesize` | GPT-5 | Claude 4.5 | - | 12s |

**Нужно реализовать:**
```python
class ModelRouter:
    async def call_with_fallback(
        self,
        prompt: str,
        docs: List[Dict],
        primary: str,
        fallback: List[str],
        timeout_s: int,
        budget_cents: int
    ) -> Dict[str, Any]:
        # Try primary
        try:
            result = await self.call_model(prompt, docs, primary, timeout_s)
            return result
        except (TimeoutError, ModelUnavailableError):
            # Try fallback chain
            for fb_model in fallback:
                try:
                    result = await self.call_model(prompt, docs, fb_model, timeout_s)
                    return result
                except:
                    continue
        raise ModelUnavailableError("All models failed")
```

---

### 7. Budget & Degradation — 100% отсутствует

**Требования промпта (раздел "ДЕГРАДАЦИИ/БЮДЖЕТ"):**

При исчерпании `budget_cents`, `max_tokens`, `timeout_s`:
1. Сократить контекст до top `k_final`; отключить rerank
2. Agentic: ≤1 итерация без self-check
3. GraphRAG: `hop_limit=1`; `max_nodes=60/max_edges=180`
4. Events: без альтернативных трактовок; только top-5 событий
5. Memory: только `recall` (без `suggest/store`)
6. Переключиться на fallback
7. При невозможности → `BUDGET_EXCEEDED` error

**Текущая реализация:**
- ❌ Нет budget tracking
- ❌ Нет degradation logic
- ❌ Нет фиксации warnings при деградации

**Нужно реализовать:**
```python
class BudgetManager:
    def __init__(self, max_tokens: int, budget_cents: int, timeout_s: int):
        self.max_tokens = max_tokens
        self.budget_cents = budget_cents
        self.timeout_s = timeout_s
        self.spent_tokens = 0
        self.spent_cents = 0

    def can_afford(self, estimated_tokens: int) -> bool:
        return (self.spent_tokens + estimated_tokens <= self.max_tokens and
                self.spent_cents < self.budget_cents)

    def degrade_params(self, command: str) -> Dict[str, Any]:
        # Return degraded parameters based on command
        if command == "/ask":
            return {"depth": 1, "self_check": False}
        elif command == "/graph":
            return {"hop_limit": 1, "max_nodes": 60, "max_edges": 180}
        # ...
```

---

### 8. A/B Testing — 100% отсутствует

**Требования промпта:**
- Если присутствует `ab_test`, следовать ветке (arms) для выбора модели/порогов
- Заполнить `meta.experiment`, `meta.arm`

**Текущая реализация:**
- ✅ Схема поддерживает `meta.experiment` и `meta.arm`
- ❌ Нет логики routing по A/B arm
- ❌ Нет конфигурации experiments

**Нужно реализовать:**
```python
class ABTestRouter:
    def __init__(self, experiments: Dict[str, Dict]):
        self.experiments = experiments

    def get_config(self, experiment: str, arm: str) -> Dict[str, Any]:
        # Return model/threshold config for arm
        config = self.experiments[experiment][arm]
        return config
```

---

### 9. Policy Validation — 70% отсутствует

**Файл:** [schemas/analysis_schemas.py](../schemas/analysis_schemas.py)

**Есть:**
- ✅ `PolicyValidator.contains_pii()` (регексы для SSN, email, phone)
- ✅ `PolicyValidator.is_safe_domain()` (blacklist)
- ✅ `PolicyValidator.validate_evidence_required()` (проверка evidence_refs)

**Отсутствует:**
- ❌ Не интегрирован в `phase3_orchestrator.py` (не вызывается)
- ❌ Нет whitelist доменов (промпт требует "domain whitelist")
- ❌ Нет автоматической маскировки PII (промпт: "маскируй случайно обнаруженные")
- ❌ Нет понижения confidence для сомнительных доменов

**Нужно реализовать:**
```python
class PolicyValidator:
    DOMAIN_WHITELIST = ["techcrunch.com", "wired.com", ...]

    @staticmethod
    def validate_and_mask_pii(text: str) -> str:
        # Auto-mask PII patterns
        masked = text
        for pattern in PolicyValidator.PII_PATTERNS:
            masked = re.sub(pattern, "[REDACTED]", masked)
        return masked

    @staticmethod
    def validate_domain_trust(url: str) -> float:
        # Return confidence penalty for non-whitelisted domains
        if any(d in url for d in PolicyValidator.DOMAIN_WHITELIST):
            return 1.0
        elif any(d in url for d in PolicyValidator.DOMAIN_BLACKLIST):
            return 0.0
        else:
            return 0.7  # Unknown domain penalty
```

---

### 10. Bot Integration — 80% отсутствует

**Файл:** [services/orchestrator.py](../services/orchestrator.py)

**Есть:**
- ✅ `get_phase3_orchestrator()` singleton
- ✅ `execute_phase3_context(context)` точка входа

**Отсутствует:**
- ❌ Bot handlers для `/ask`, `/events`, `/graph`, `/memory` (аналоги `handle_trends_command()`, `handle_analyze_command()`)
- ❌ Парсинг параметров команд (depth, topic, entity, hops, operation)
- ❌ Telegram formatting для Phase 3 responses
- ❌ Refresh buttons для Phase 3 команд

**Нужно реализовать:**
```python
async def handle_ask_command(
    self,
    *,
    query: str,
    depth: int = 3,
    window: str = "24h",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 5,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Build context for Phase3Orchestrator
    context = {
        "command": "/ask",
        "params": {"query": query, "depth": depth, "lang": lang, ...},
        "retrieval": {"docs": ..., "window": window, ...},
        "models": {"primary": "gpt-5", "fallback": ["claude-4.5", "gemini-2.5-pro"]},
        "limits": {"max_tokens": 8000, "budget_cents": 50, "timeout_s": 15},
        "telemetry": {"correlation_id": correlation_id, "version": "phase3-v1.0"}
    }
    response = await execute_phase3_context(context)
    payload = format_for_telegram(response)
    return self._augment_payload(payload, context={"command": "ask", ...})
```

---

## 📊 Сводная таблица готовности

| Компонент | Готовность | Комментарий |
|-----------|------------|-------------|
| **Схемы (Pydantic)** | 100% | Все схемы реализованы и валидны |
| **Базовый оркестратор** | 30% | Заглушки для всех команд, но без логики |
| **Agentic RAG** | 30% | Только структура, нет итераций/self-check |
| **Event Linking** | 20% | Только структура, нет NER/causality |
| **GraphRAG** | 10% | Только моковый граф, нет construction/traversal |
| **Long-term Memory** | 5% | Только структура, нет БД/embeddings |
| **Model Integration** | 0% | Нет вызовов LLM |
| **Routing & Fallbacks** | 0% | Нет routing logic |
| **Budget & Degradation** | 0% | Нет budget tracking |
| **Policy Validation** | 30% | Есть validators, но не интегрированы |
| **Bot Integration** | 20% | Есть entry point, нет handlers |

---

## 🎯 Приоритизация реализации

### Критическая важность (P0)

1. **Model Integration (routing, fallbacks, timeouts)**
   - Без этого оркестратор не может вызывать LLM
   - Необходим для всех 5 команд

2. **Agentic RAG — iterative retrieval loop**
   - Ключевая фича Phase 3
   - Демонстрирует multi-hop reasoning

3. **Budget tracking & degradation**
   - Защита от превышения лимитов
   - Обязательное требование промпта

### Высокая важность (P1)

4. **GraphRAG — on-demand graph construction**
   - Уникальная фича Phase 3
   - Требует NER + relation extraction

5. **Event Linking — causality reasoning**
   - Уникальная фича Phase 3
   - Требует NER + temporal analysis

6. **Bot Integration — handlers for Phase 3 commands**
   - Необходимо для тестирования через Telegram
   - Parsing params, formatting responses

### Средняя важность (P2)

7. **Long-term Memory — database + embeddings**
   - Долгосрочная фича
   - Требует инфраструктуру (pgvector, embeddings API)

8. **Policy Validation — integration + auto-masking**
   - Улучшение безопасности
   - Whitelist/blacklist доменов

9. **A/B Testing framework**
   - Опциональная фича для экспериментов

### Низкая важность (P3)

10. **Graph caching (build_policy=cached_only)**
    - Оптимизация для GraphRAG

11. **Advanced degradation (hop_limit, max_nodes)**
    - Fine-tuning для production

---

## 🛠️ Рекомендации по реализации

### Этап 1: Foundation (1-2 недели)

1. **Создать `ModelRouter` класс**
   - Интегрировать OpenAI/Anthropic/Google API
   - Routing: primary → fallback → QC
   - Timeout handling
   - Token/cost tracking

2. **Интегрировать `BudgetManager`**
   - Tracking tokens/cost
   - Degradation logic по команде
   - Warnings при деградации

3. **Реализовать Agentic RAG (базовая версия)**
   - 1-3 итерации
   - Reformulation (query expansion)
   - Повторный ретрив
   - Без self-check (оставить на P1)

4. **Bot handlers для `/ask`**
   - Parsing `--depth=deep`
   - Context building
   - Telegram formatting

### Этап 2: Advanced Features (2-3 недели)

5. **GraphRAG implementation**
   - NER integration (spaCy или LLM-based)
   - Relation extraction
   - Graph construction (NetworkX)
   - Traversal (BFS/DFS up to `hop_limit`)
   - Subgraph extraction

6. **Event Linking implementation**
   - NER + temporal extraction
   - Time-based clustering
   - Causal reasoning (LLM-based)
   - Gap detection

7. **Bot handlers для `/graph`, `/events`**

### Этап 3: Memory & Optimization (2-3 недели)

8. **Long-term Memory implementation**
   - Database schema (PostgreSQL + pgvector)
   - Embeddings (OpenAI/Cohere)
   - Semantic search
   - TTL expiration
   - PII filtering

9. **Policy Validation integration**
   - Auto-masking PII
   - Domain whitelist/blacklist
   - Confidence penalties

10. **Bot handlers для `/memory`**

### Этап 4: Production Readiness (1 неделя)

11. **A/B Testing framework**
12. **Graph caching**
13. **Monitoring & metrics**
14. **End-to-end tests**

---

## 📁 Файлы для изменения/создания

### Изменить

1. [core/orchestrator/phase3_orchestrator.py](../core/orchestrator/phase3_orchestrator.py)
   - Заменить заглушки на реальную логику

2. [services/orchestrator.py](../services/orchestrator.py)
   - Добавить bot handlers для Phase 3

3. [core/rag/retrieval_client.py](../core/rag/retrieval_client.py)
   - Добавить `retrieve_for_agentic()`

4. [schemas/analysis_schemas.py](../schemas/analysis_schemas.py)
   - Расширить `PolicyValidator`

### Создать новые

5. `core/models/model_router.py`
   - Routing, fallbacks, timeouts

6. `core/models/budget_manager.py`
   - Budget tracking, degradation

7. `core/graph/graph_builder.py`
   - NER, relations, graph construction

8. `core/graph/graph_traversal.py`
   - Traversal, subgraph extraction

9. `core/events/event_extractor.py`
   - NER, temporal extraction, clustering

10. `core/events/causality_reasoner.py`
    - Causal link inference

11. `core/memory/memory_store.py`
    - Database interface, embeddings, TTL

12. `core/memory/semantic_search.py`
    - Vector search

13. `core/policies/pii_masker.py`
    - Auto-masking PII

14. `core/ab_testing/experiment_router.py`
    - A/B test config

---

## ✅ Следующие шаги

1. **Приоритизация:** Согласовать приоритеты (P0 → P1 → P2)
2. **Design review:** Согласовать архитектуру `ModelRouter`, `BudgetManager`, `GraphBuilder`
3. **Sprint planning:** Разбить на спринты (этапы 1-4)
4. **Implementation:** Начать с P0 (Model Integration + Agentic RAG)
5. **Testing:** E2E тесты для каждой команды
6. **Documentation:** Обновить README, API docs

---

**Вывод:**
Phase 3 промпт описывает **амбициозную систему** с 5 новыми командами и сложной логикой (итеративный RAG, граф знаний, события, память). Текущая реализация — это **структурный каркас (30%)** с валидными схемами, но **без интеллектуальной логики**. Для production-ready системы требуется **6-8 недель разработки** (этапы 1-4).
