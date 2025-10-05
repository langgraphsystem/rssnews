# Почему FTS сервис НЕ нуждается в OPENAI_API_KEY

**Service ID:** `ffe65f79-4dc5-4757-b772-5a99c7ea624f`

**Вопрос:** Зачем нужна `OPENAI_EMBEDDING_MODEL=text-embedding-3-large` в FTS обработке?

**Ответ:** **НЕ нужна!** FTS сервис работает НЕЗАВИСИМО от OpenAI.

---

## Проблема (до исправления)

### Старая команда в launcher.py:
```bash
python main.py services start --services fts --fts-interval 60
```

### Что происходило:
```
launcher.py
    ↓
main.py services start
    ↓
ServiceManager.__init__()
    ├─ ChunkingService() ✅
    ├─ FTSService() ✅
    └─ EmbeddingService() ❌ <- Требует OPENAI_API_KEY!
```

### Результат:
```python
# services/service_manager.py:43
self.embedding_service = EmbeddingService(self.db)

# EmbeddingService пытается загрузить:
from openai_embedding_generator import OpenAIEmbeddingGenerator
# ↓
# openai_embedding_generator.py:24
if not self.api_key:
    raise ValueError("OPENAI_API_KEY environment variable is required")

# ❌ ОШИБКА! Даже если FTS сервису OpenAI не нужен
```

---

## Решение (после исправления)

### Новая команда в launcher.py:
```bash
python services/fts_service.py service --interval 60 --batch-size 100000
```

### Что происходит теперь:
```
launcher.py
    ↓
services/fts_service.py (ПРЯМОЙ запуск)
    ↓
FTSService.__init__()
    └─ PgClient() только! ✅

БЕЗ ServiceManager
БЕЗ EmbeddingService
БЕЗ OpenAI зависимостей
```

### Результат:
```python
# services/fts_service.py:24-25
def __init__(self, db_client: Optional[PgClient] = None):
    self.db = db_client or PgClient()
    # ВСЁ! Никаких OpenAI импортов

# ✅ FTS работает только с PostgreSQL tsvector
```

---

## Что делает FTS сервис?

### Full-Text Search через PostgreSQL

```sql
-- Создаёт tsvector индексы для быстрого поиска по ключевым словам
UPDATE article_chunks
SET fts_vector = to_tsvector('russian', text)
WHERE fts_vector IS NULL;

-- Поиск работает через PostgreSQL:
SELECT * FROM article_chunks
WHERE fts_vector @@ to_tsquery('russian', 'технологии & искусственный')
ORDER BY ts_rank(fts_vector, query) DESC;
```

### НЕ использует:
- ❌ OpenAI API
- ❌ text-embedding-3-large
- ❌ Векторные embeddings (3072-dim)
- ❌ Cosine similarity

### Использует:
- ✅ PostgreSQL tsvector/tsquery
- ✅ GIN индексы
- ✅ ts_rank для ранжирования
- ✅ Морфологический анализ (russian/english text search config)

---

## Сравнение: FTS vs OpenAI Embeddings

| Аспект | FTS Service (ffe65f79) | OpenAI Embedding Service (c015bdb5) |
|--------|------------------------|--------------------------------------|
| **Технология** | PostgreSQL tsvector | OpenAI text-embedding-3-large |
| **API Key** | ❌ НЕ требуется | ✅ Требуется OPENAI_API_KEY |
| **Размерность** | N/A (текстовые индексы) | 3072-dim векторы |
| **Поиск** | Ключевые слова (точное совпадение) | Семантическое сходство |
| **Скорость** | Очень быстро (ms) | Быстро (ms в БД, но генерация медленная) |
| **Стоимость** | Бесплатно (только БД) | $0.13 / 1M токенов |
| **Язык** | Поддержка морфологии (russian, english) | 100+ языков, понимание смысла |
| **Примеры** | "технология" → "технологии", "технологий" | "AI" ≈ "искусственный интеллект" |

---

## Hybrid Search: Как они работают вместе

```
Запрос пользователя: "новости о нейросетях"
    │
    ├─────────────────────────┬─────────────────────────┐
    ↓                         ↓                         ↓
FTS Search               Semantic Search          (Опционально)
(PostgreSQL tsvector)    (OpenAI 3072-dim)
    │                         │
    │ Находит:                │ Находит:
    │ - "нейросеть"           │ - "машинное обучение"
    │ - "нейросети"           │ - "глубокие сети"
    │ - "нейросетями"         │ - "deep learning"
    │                         │ - "artificial intelligence"
    ↓                         ↓
    └─────────────────────────┴─────────────────────────┐
                              ↓
                   Reciprocal Rank Fusion (RRF)
                   Объединяет результаты с весами
                              ↓
                   Итоговый рейтинг статей
```

**Преимущество:** Точные совпадения (FTS) + понимание смысла (Embeddings) = лучшие результаты!

---

## Конфигурация Railway сервиса ffe65f79

### Минимально необходимые переменные:
```bash
SERVICE_MODE=fts-continuous
FTS_CONTINUOUS_INTERVAL=60
FTS_BATCH=100000
PG_DSN=postgresql://user:pass@host:port/db
```

### НЕ требуется:
```bash
# ❌ Эти переменные НЕ нужны для FTS:
OPENAI_API_KEY=...
OPENAI_EMBEDDING_MODEL=...
OPENAI_EMBEDDING_BATCH_SIZE=...
EMBEDDING_TIMEOUT=...
```

---

## Проверка работы FTS без OpenAI

```bash
# Тест 1: Проверить импорт
python -c "from services.fts_service import FTSService; print('✅ FTS OK')"

# Тест 2: Запустить без OPENAI_API_KEY
unset OPENAI_API_KEY
export SERVICE_MODE=fts-continuous
python launcher.py
# Должно работать! ✅

# Тест 3: Полный тест
python test_fts_no_openai.py
# Все тесты должны пройти ✅
```

---

## Заключение

**FTS сервис (ffe65f79):**
- ✅ Работает БЕЗ `OPENAI_API_KEY`
- ✅ Использует только PostgreSQL
- ✅ Запускается напрямую через `services/fts_service.py`
- ✅ Независим от EmbeddingService и ServiceManager
- ✅ Быстрый, бесплатный, эффективный keyword-поиск

**OpenAI Embedding сервис (c015bdb5):**
- ✅ Требует `OPENAI_API_KEY`
- ✅ Генерирует 3072-dim векторы
- ✅ Обеспечивает семантический поиск
- ✅ Работает в ПАРАЛЛЕЛЬ с FTS (не заменяет его!)

**Оба сервиса важны для Hybrid Search, но работают НЕЗАВИСИМО друг от друга!** 🎯

---

## Дополнительная информация

- [RAILWAY_SERVICES_CONFIG.md](RAILWAY_SERVICES_CONFIG.md) - Полная конфигурация всех сервисов
- [SERVICE_ffe65f79_FTS_INFO.md](SERVICE_ffe65f79_FTS_INFO.md) - Детальная документация FTS сервиса
- [SERVICE_c015bdb5_INFO.md](SERVICE_c015bdb5_INFO.md) - Документация OpenAI Embedding сервиса
- [services/fts_service.py](services/fts_service.py) - Исходный код FTS сервиса
- [launcher.py](launcher.py) - Универсальный лаунчер для Railway

**Последнее обновление:** 2025-10-05
