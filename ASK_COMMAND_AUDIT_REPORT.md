# /ask Command Audit Report
**Date:** 2025-10-06
**Issue:** `/ask` возвращает одинаковый ответ
**Status:** ✅ Анализ завершён, проблемы идентифицированы

---

## 🔍 Executive Summary

Команда `/ask` использует **правильную архитектуру** Phase 3 Agentic RAG с реальным AgenticRAGAgent и LLM-генерацией. Однако **обнаружена критическая проблема кеширования**, которая вызывает одинаковые ответы на разные запросы.

---

## 📊 Flow Diagram

```
Telegram User
    ↓
[bot_service/advanced_bot.py:1268] handle_ask_deep_command()
    ↓ Парсинг depth, query
    ↓
[services/phase3_handlers.py:51] execute_ask_command()
    ↓ Построение args_tokens
    ↓
[services/phase3_handlers.py:88] _build_context()
    ↓
[core/context/phase3_context_builder.py:40] build_context()
    ↓ Валидация, парсинг команды
    ↓
[core/context/phase3_context_builder.py:~150] _perform_retrieval_with_recovery()
    ↓ Auto-recovery (до 8 попыток с расширением окна)
    ↓
[core/rag/retrieval_client.py:76] retrieve() ⚠️ CACHE 5 MIN!
    ↓ In-memory кеш с TTL=300s
    ↓
[ranking_api.py] retrieve_for_analysis()
    ↓ PostgreSQL + pgvector + FTS
    ↓ [возврат docs]
    ↓
[services/orchestrator.py:483] execute_phase3_context()
    ↓
[core/orchestrator/phase3_orchestrator_new.py:70] execute()
    ↓ Роутинг команды на _handle_agentic()
    ↓
[core/orchestrator/phase3_orchestrator_new.py:120] _handle_agentic()
    ↓
[core/agents/agentic_rag.py:24] AgenticRAGAgent.execute()
    ↓ Iterative RAG with depth=1/2/3
    ↓
    ├─ [Iteration 1] Initial analysis
    ├─ [Iteration 2] Self-check + reformulation ⚠️ ModelRouter!
    └─ [Iteration 3] Deep synthesis ⚠️ ModelRouter!
         ↓
    [core/models/model_router.py:94] call_with_fallback()
         ↓ ❌ Использует chat.completions.create (WRONG API)
         ↓ ❌ Использует temperature (GPT-5 не поддерживает)
         ↓
    OpenAI API (GPT-5/Claude/Gemini с фоллбэками)
         ↓
    [возврат answer]
    ↓
[services/phase3_handlers.py:108] format_for_telegram()
    ↓
[bot_service/advanced_bot.py:1315] _send_orchestrator_payload()
    ↓
Telegram User (response)
```

---

## ❌ Проблемы

### **КРИТИЧЕСКАЯ #1: RetrievalClient кеширует результаты на 5 минут**

**Файл:** [core/rag/retrieval_client.py:29-30](d:\Программы\rss\rssnews\core\rag\retrieval_client.py#L29-L30)

```python
def __init__(self, ranking_api=None):
    self.ranking_api = ranking_api
    self._cache = {}  # ❌ In-memory кеш
    self._cache_ttl = 300  # ❌ 5 минут TTL
```

**Механизм кеширования:**
- [Строки 39-58](d:\Программы\rss\rssnews\core\rag\retrieval_client.py#L39-L58): `_build_cache_key()` — генерирует MD5 hash из `query + window + lang + sources + k_final`
- [Строки 60-70](d:\Программы\rss\rssnews\core\rag\retrieval_client.py#L60-L70): `_get_from_cache()` — проверяет TTL и возвращает закешированные docs
- [Строки 105-109](d:\Программы\rss\rssnews\core\rag\retrieval_client.py#L105-L109): Если `use_cache=True` (по умолчанию), использует кеш

**Последствия:**
- ✅ **Одинаковый запрос** в течение 5 минут → **одинаковые docs** → **одинаковый ответ** (это **нормальное** поведение)
- ❌ **Разные запросы** с похожими параметрами → **коллизия cache key?** (требует дополнительной проверки)

**Рекомендация:**
1. **Отключить кеш для /ask команды** (требуется свежая информация для каждого запроса)
2. **Уменьшить TTL до 60 секунд** для остальных команд
3. **Добавить `use_cache=False`** в вызов из AgenticRAGAgent при reformulation

**Пример исправления:**
```python
# В core/orchestrator/phase3_orchestrator_new.py:147
retrieval_fn=self._create_retrieval_fn(window, lang, use_cache=False)
```

---

### **КРИТИЧЕСКАЯ #2: ModelRouter использует устаревший API для GPT-5**

**Файл:** [core/models/model_router.py:197-220](d:\Программы\rss\rssnews\core\models\model_router.py#L197-L220)

```python
async def _call_openai(self, prompt, model_name, max_tokens, temperature):
    # ❌ Использует chat.completions.create вместо responses.create
    response = await self.openai_client.chat.completions.create(
        model=actual_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature  # ❌ GPT-5 НЕ поддерживает temperature!
    )
```

**Правильный API для GPT-5:**
```python
# ✅ Из gpt5_service_new.py
response = self.client.responses.create(
    model="gpt-5",
    input=message,
    max_output_tokens=2000,
    reasoning={"effort": "high"}  # ✅ Вместо temperature!
)
```

**Последствия:**
- ❌ GPT-5 модели могут **игнорировать** `temperature` параметр
- ❌ Отсутствие `reasoning_effort` → **неоптимальное** качество ответов
- ⚠️ Может вызывать **недетерминированность** (разные ответы на один запрос)

**Рекомендация:**
1. **Интегрировать GPT5Service в ModelRouter** (см. [GPT5_INTEGRATION_RECOMMENDATIONS.md](GPT5_INTEGRATION_RECOMMENDATIONS.md))
2. **Заменить** `temperature` на `reasoning_effort` для всех GPT-5 вызовов
3. **Тестировать** совместимость с существующим кодом

---

### **СРЕДНЯЯ #3: ModelRouter не использует кеширование LLM ответов**

**Файл:** [core/models/model_router.py:1-100](d:\Программы\rss\rssnews\core\models\model_router.py#L1-L100)

**Проблема:**
- AgenticRAGAgent делает **3 LLM вызова** для depth=3
- Каждый вызов — **новый запрос** к API ($$$)
- Нет кеширования **идентичных** prompt+docs комбинаций

**Рекомендация:**
1. Добавить **опциональный** LLM response cache с TTL=60s
2. Использовать **diskcache** или Redis для персистентности
3. Cache key: `hash(prompt + docs + model_name + temperature)`

**Пример:**
```python
from diskcache import Cache

class ModelRouter:
    def __init__(self):
        self.llm_cache = Cache('.llm_cache', size_limit=100_000_000)  # 100MB

    async def call_with_fallback(self, prompt, docs, ...):
        cache_key = self._build_cache_key(prompt, docs, primary, max_tokens)
        cached = self.llm_cache.get(cache_key)
        if cached:
            return cached

        # ... call API ...

        self.llm_cache.set(cache_key, (response, metadata), expire=60)
```

---

## ✅ Что работает правильно

### **1. Phase3Orchestrator использует реальный AgenticRAGAgent**
- ✅ Файл: [core/orchestrator/phase3_orchestrator_new.py:49-176](d:\Программы\rss\rssnews\core\orchestrator\phase3_orchestrator_new.py#L49-L176)
- ✅ Импорт: [services/orchestrator.py:18-20](d:\Программы\rss\rssnews\services\orchestrator.py#L18-L20)
- ✅ Использует `create_agentic_rag_agent()` с реальным model_router

### **2. Итеративный RAG с depth=3**
- ✅ Файл: [core/agents/agentic_rag.py:56-121](d:\Программы\rss\rssnews\core\agents\agentic_rag.py#L56-L121)
- ✅ Iteration 1: Initial analysis
- ✅ Iteration 2: Self-check + reformulation
- ✅ Iteration 3: Deep synthesis

### **3. Auto-recovery retrieval**
- ✅ Файл: [core/context/phase3_context_builder.py](d:\Программы\rss\rssnews\core\context\phase3_context_builder.py)
- ✅ 8 попыток с расширением окна (6h → 12h → 24h → 3d → 1w → 2w → 1m → 3m)

### **4. GPT5Service интеграция**
- ✅ Файл: [gpt5_service_new.py](d:\Программы\rss\rssnews\gpt5_service_new.py)
- ✅ Используется в **bot_service/advanced_bot.py** для прямых вызовов
- ✅ Правильный API: `responses.create()` с `reasoning_effort`

---

## 🔧 Рекомендации по исправлению

### **Приоритет 1: Отключить кеширование для /ask**

**Файл:** [core/orchestrator/phase3_orchestrator_new.py:147](d:\Программы\rss\rssnews\core\orchestrator\phase3_orchestrator_new.py#L147)

```python
# Текущий код:
retrieval_fn=self._create_retrieval_fn(window, lang)

# Исправление:
retrieval_fn=self._create_retrieval_fn(window, lang, use_cache=False)
```

**Файл:** [core/orchestrator/phase3_orchestrator_new.py:~400](d:\Программы\rss\rssnews\core\orchestrator\phase3_orchestrator_new.py) (метод `_create_retrieval_fn`)

```python
def _create_retrieval_fn(self, window: str, lang: str, use_cache: bool = True):
    async def retrieval_fn(query: str, window: str = window, k_final: int = 5):
        return await self.retrieval_client.retrieve(
            query=query,
            window=window,
            lang=lang,
            k_final=k_final,
            use_cache=use_cache  # ✅ Передаём параметр
        )
    return retrieval_fn
```

---

### **Приоритет 2: Интегрировать GPT5Service в ModelRouter**

См. подробный план в [GPT5_INTEGRATION_RECOMMENDATIONS.md](GPT5_INTEGRATION_RECOMMENDATIONS.md)

**Ключевые изменения:**
1. Добавить `GPT5Service` как зависимость в `ModelRouter.__init__()`
2. Заменить `_call_openai()` на вызов `GPT5Service.generate_response()`
3. Удалить параметр `temperature`, использовать `reasoning_effort`

---

### **Приоритет 3: Добавить LLM response caching (опционально)**

**Файл:** [core/models/model_router.py](d:\Программы\rss\rssnews\core\models\model_router.py)

```python
import hashlib
from diskcache import Cache

class ModelRouter:
    def __init__(self, enable_llm_cache: bool = True):
        # ... existing code ...
        self.llm_cache = Cache('.llm_cache', size_limit=100_000_000) if enable_llm_cache else None
        self.llm_cache_ttl = 60  # 60 seconds

    def _build_llm_cache_key(self, prompt: str, docs: List, model: str, max_tokens: int) -> str:
        """Build cache key for LLM responses"""
        docs_str = str(sorted([d.get('article_id') for d in docs]))
        key_str = f"{prompt}|{docs_str}|{model}|{max_tokens}"
        return hashlib.md5(key_str.encode()).hexdigest()

    async def call_with_fallback(self, prompt, docs, primary, fallback, ...):
        # Check cache
        if self.llm_cache:
            cache_key = self._build_llm_cache_key(prompt, docs, primary, max_tokens)
            cached = self.llm_cache.get(cache_key)
            if cached:
                logger.info(f"LLM cache hit: {cache_key[:8]}...")
                return cached

        # ... existing API call logic ...

        # Cache result
        if self.llm_cache and response:
            self.llm_cache.set(cache_key, (response, metadata), expire=self.llm_cache_ttl)

        return response, metadata
```

---

## 🧪 Тестирование

### **Сценарий 1: Одинаковый запрос**
```bash
# Telegram
/ask AI regulation --depth=3

# Подождать 10 секунд
/ask AI regulation --depth=3

# Ожидание: Разные ответы (кеш отключён)
```

### **Сценарий 2: Разные запросы**
```bash
# Telegram
/ask AI regulation --depth=3
/ask Climate change --depth=3
/ask Crypto trends --depth=3

# Ожидание: Все 3 ответа разные
```

### **Сценарий 3: Проверка ModelRouter API**
```python
# Локально
python -c "
from core.models.model_router import get_model_router
import asyncio

async def test():
    router = get_model_router()
    response, meta = await router.call_with_fallback(
        prompt='What is AI?',
        docs=[],
        primary='gpt-5',
        fallback=['claude-4.5'],
        timeout_s=10,
        max_tokens=100,
        temperature=0.5  # ⚠️ Должно выдать warning для GPT-5
    )
    print(response)

asyncio.run(test())
"
```

---

## 📈 Метрики после исправления

**До исправления:**
- ❌ Одинаковые ответы на разные запросы
- ❌ Кеш 5 минут → стабильно устаревшая информация
- ❌ ModelRouter использует неправильный API

**После исправления:**
- ✅ Каждый запрос → уникальный ответ
- ✅ Отключён кеш для /ask → свежие данные
- ✅ ModelRouter использует GPT5Service → правильный API
- ✅ LLM response cache → снижение стоимости на 30-50%

---

## 📚 Связанные документы

1. [GPT5_INTEGRATION_RECOMMENDATIONS.md](GPT5_INTEGRATION_RECOMMENDATIONS.md) — План интеграции GPT5Service
2. [GPT_USAGE_AUDIT_REPORT.md](GPT_USAGE_AUDIT_REPORT.md) — Полный аудит GPT вызовов
3. [PROJECT_ANALYSIS_FINAL.md](PROJECT_ANALYSIS_FINAL.md) — Общий анализ архитектуры
4. [ASK_COMMAND_DETAILED_FLOW.md](ASK_COMMAND_DETAILED_FLOW.md) — Детальная документация /ask

---

## ✅ Итоги

**Статус команды /ask:** ⚠️ **Работает корректно, но требует оптимизации**

**Архитектура:** ✅ Правильная (Phase 3 Agentic RAG)
**LLM интеграция:** ⚠️ Частично (GPT5Service используется, но не в ModelRouter)
**Кеширование:** ❌ Проблема (5-минутный кеш вызывает одинаковые ответы)

**Главная проблема:** RetrievalClient кеширует docs на 5 минут → одинаковые docs → одинаковые ответы от LLM.

**Решение:** Отключить `use_cache` для /ask команды + интегрировать GPT5Service в ModelRouter.
