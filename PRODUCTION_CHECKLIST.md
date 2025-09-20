# ✅ Чеклист внедрения LlamaIndex в продакшн

**Печатай и отмечай пункты по мере выполнения!**

---

## 🔧 1. Подготовка окружения

### Базовая установка
- [ ] Установлен LlamaIndex (`pip install -r requirements_llamaindex.txt`)
- [ ] Проверены версии Python ≥3.8, PostgreSQL ≥13, pgvector расширение
- [ ] Создан Pinecone индекс (768 dimensions, cosine metric)

### API ключи и доступы
- [ ] Доступ к API Pinecone подтверждён (`pinecone.list_indexes()`)
- [ ] Доступ к Postgres (Railway) подтверждён (`psql $PG_DSN`)
- [ ] OpenAI API ключ активен (`curl openai.com/v1/models`)
- [ ] Gemini API ключ активен (embeddings + LLM)

### Конфигурация .env
- [ ] `PINECONE_API_KEY=pc-...` ✅
- [ ] `PINECONE_INDEX=rssnews-embeddings` ✅
- [ ] `PINECONE_REGION=us-east-1-aws` ✅
- [ ] `OPENAI_API_KEY=sk-...` ✅
- [ ] `GEMINI_API_KEY=AI...` ✅
- [ ] `PG_DSN=postgresql://...` ✅

---

## 🗄️ 2. База данных и схема

### Схема LlamaIndex
- [ ] Применена схема: `psql $PG_DSN -f llamaindex_schema.sql`
- [ ] Таблица `llamaindex_nodes` создана с индексами
- [ ] Таблица `llamaindex_queries` для аналитики
- [ ] Таблица `llamaindex_costs` для бюджетирования
- [ ] Таблица `llamaindex_config` для настроек

### Индексы производительности
- [ ] FTS индекс: `idx_llamaindex_nodes_fts`
- [ ] Vector индекс: `idx_llamaindex_nodes_embedding` (pgvector)
- [ ] Метаданные: `idx_llamaindex_nodes_metadata` (jsonb gin)
- [ ] Временные: `idx_llamaindex_nodes_created_at`

---

## 📊 3. Данные и чанкинг (замена Stage 6)

### Умный чанкинг
- [ ] Заменён `chunking_simple.py` на **LlamaIndex SentenceSplitter**
- [ ] Размер чанка: 512 токенов (настраиваемо)
- [ ] Overlap: 50 токенов
- [ ] Границы: по предложениям (`paragraph_separator="\n\n"`)

### Unified Node ID
- [ ] Каждый чанк получает `node_id = {article_id}#{chunk_index}`
- [ ] Одинаковый ID в Postgres и Pinecone
- [ ] Связь с `article_chunks` через `article_id`

### Метаданные чанков
- [ ] **Обязательные**: `article_id, chunk_index, title, url, source, published_at`
- [ ] **Маршрутизация**: `language, namespace` (en/ru, hot/archive)
- [ ] **Качество**: `relevance_score, freshness_score`
- [ ] **Извлечённые**: `extracted_keywords, extracted_questions, extracted_titles`

---

## 🔍 4. Индексация (замена Stage 7)

### Pinecone настройка
- [ ] Namespaces созданы: `en_hot, en_archive, ru_hot, ru_archive`
- [ ] Dimension: 768 (Gemini text-embedding-004)
- [ ] Metric: cosine similarity
- [ ] Подключение тестировано

### Двойное хранение
- [ ] **Postgres**: FTS векторы + метаданные (быстрый поиск по ключевым словам)
- [ ] **Pinecone**: эмбеддинги Gemini (семантический поиск)
- [ ] Синхронизация: один чанк → обе системы

### Эмбеддинги
- [ ] Всегда **Gemini Embeddings** (консистентность)
- [ ] Модель: `text-embedding-004` (768 dim)
- [ ] Batch обработка для экономии

---

## 🚦 5. Маршрутизация и правила

### Жёсткие правила (без экспериментов)
- [ ] **Эмбеддинги**: всегда Gemini ✅
- [ ] **Ретривер**: Hybrid (FTS Postgres + Vector Pinecone) ✅
- [ ] **LLM по умолчанию**: OpenAI GPT-5 ✅
- [ ] **Автопереключение на Gemini**: длинный контекст, лимиты OpenAI, RU тексты ✅

### Временные окна (namespaces)
- [ ] **hot** (7–30 дней): поиск первым
- [ ] **archive** (старше 30 дней): догружается при нехватке фактов
- [ ] Автоматическая маршрутизация по `published_at`

### Языковое разделение
- [ ] EN/RU раздельные индексы
- [ ] Автоопределение языка запроса (Cyrillic vs Latin)
- [ ] Router: язык запроса → соответствующий namespace

---

## 🔄 6. Поиск и ретривал (замена Stage 8)

### Hybrid Retrieval
- [ ] **FTS (Postgres)**: поиск по ключевым словам (BM25-like)
- [ ] **Vector (Pinecone)**: семантический поиск
- [ ] **Alpha**: 0.5 по умолчанию (50/50), настраиваемо
- [ ] **Комбинирование**: нормализация скоров + weighted sum

### Постобработка (pipeline)
- [ ] **Similarity filter**: отсекать слабые совпадения (score < 0.6)
- [ ] **Domain diversification**: max 1–2 куска/домен в финальном top-N
- [ ] **Freshness boost**: статьи ≤7 дней получают +20% к скору
- [ ] **Semantic rerank**: top-24 → финальные 8–10 через cross-encoder

### Поиск стратегия
- [ ] Сначала поиск в `hot` namespace
- [ ] Если фактов мало (< min_sources) → догружаем из `archive`
- [ ] Итого top-K: 24 до rerank → 8–12 финал

---

## 📝 7. Пресеты форматов вывода

### digest (новостные сводки)
- [ ] **Окно**: 7–14 дней
- [ ] **Источники**: K=24 → финал 10–12
- [ ] **Домены**: ≥3 разных
- [ ] **Формат**: список с 1–2 предложениями + ссылка + дата

### qa (вопрос-ответ)
- [ ] **Окно**: 30 дней по умолчанию
- [ ] **Источники**: K=24 → 8–10
- [ ] **Формат**: краткий ответ + источники
- [ ] **Self-check**: предупреждение при <3 источников

### shorts (сценарии видео)
- [ ] **Окно**: 30–90 дней
- [ ] **Источники**: K=24 → 6–8
- [ ] **Формат**: hook → 3–5 ключевых тезисов (30-60 сек) → CTA + источники

### ideas (широкое исследование)
- [ ] **Окно**: 30–90 дней, фильтр по tags/категориям
- [ ] **Источники**: K=40 → 12–15 (больше для анализа)
- [ ] **Формат**: тренды → связи между источниками → прогнозы → диверсные перспективы

---

## 🛡️ 8. Анти-галлюцинации и grounding

### Grounded ответы
- [ ] Ответ **только** по извлечённым чанкам (no hallucination)
- [ ] Каждый факт — минимум одна ссылка
- [ ] Предупреждение при недостатке источников
- [ ] Явное указание ограничений поиска

### Source attribution
- [ ] Каждый финальный чанк: `title, url, source_domain, published_at`
- [ ] Relevance score отображается (опционально)
- [ ] Preview текста (первые 200 символов)

---

## 💰 9. Производительность и cost control

### Top-K оптимизация
- [ ] **Retrieval**: 24 чанка (умеренно для скорости)
- [ ] **Final**: 8–12 (держит quality vs. speed)
- [ ] Настраиваемые лимиты по пресетам

### Кэширование
- [ ] **Query cache**: 10–15 минут TTL
- [ ] **Cache key**: query + preset + language + max_sources (MD5)
- [ ] **LRU eviction**: при достижении max_size
- [ ] **Cache hit rate** мониторится

### Cost guards (бюджетирование)
- [ ] **Дневные лимиты**: OpenAI $50, Gemini $30, total $100
- [ ] **Токен лимиты** на синтез (предотвращение runaway)
- [ ] **Автопереключение** на дешёвую модель при приближении к лимиту
- [ ] **Alerting** при достижении 80% лимита

---

## 📊 10. Наблюдаемость и логирование

### Query logging
- [ ] **Запрос**: текст, hash, язык, пресет
- [ ] **Результат**: `retrieved_node_ids, used_node_ids, response_length`
- [ ] **Performance**: время обработки, cache_hit, provider
- [ ] **Quality**: диверсификация доменов, средняя свежесть, relevance

### Cost tracking
- [ ] **Daily/hourly aggregates**: по провайдерам (OpenAI, Gemini, embeddings)
- [ ] **Usage counts**: запросы, processed nodes, embeddings created
- [ ] **Budget status**: spent vs. limits, alerts sent

### Performance monitoring
- [ ] **Operation timing**: ingest, query, migrate (по компонентам)
- [ ] **Success rates**: error counting по типам
- [ ] **Resource usage**: memory, concurrent operations

### Analytics views
- [ ] `llamaindex_daily_costs`: дневные расходы + лимиты
- [ ] `llamaindex_query_stats`: производительность по пресетам/языкам
- [ ] `llamaindex_node_distribution`: распределение по namespace/языкам
- [ ] `llamaindex_performance_summary`: ошибки, latency P95

---

## 🚀 11. Поэтапное внедрение

### Phase 1: Параллельное тестирование (1-2 недели)
- [ ] LlamaIndex работает **параллельно** с существующей системой
- [ ] Обработка: 100–500 статей для сравнения качества
- [ ] A/B comparison: результаты LlamaIndex vs. legacy Stage 6-8
- [ ] Метрики: precision, recall, user satisfaction

### Phase 2: Селективная замена (2-4 недели)
- [ ] **Новые статьи** идут через LlamaIndex SentenceSplitter
- [ ] **Stage 7-8** пока остаются legacy (для стабильности)
- [ ] **Backfill**: свежие статьи (30 дней) в `hot` namespace
- [ ] **Мониторинг**: качество чанкинга, performance

### Phase 3: Полная замена (4-8 недель)
- [ ] **Retrieval** переключён на Hybrid LlamaIndex
- [ ] **Synthesis** через пресеты (digest/qa/shorts/ideas)
- [ ] **Migration**: все старые статьи в `archive`
- [ ] **Legacy Mode**: готов для экстренного отката

---

## 🔧 12. Legacy Mode и аварийный план

### Кнопка "Legacy Mode"
- [ ] **Конфигурация**: одна команда `python main.py llamaindex-legacy enable`
- [ ] **Компонентный откат**: можно включить legacy только для chunking/retrieval/synthesis
- [ ] **Мониторинг**: статус legacy режима в dashboard

### Rollback процедура (если что-то сломалось)
- [ ] **Шаг 1**: `llamaindex-legacy enable --components full`
- [ ] **Шаг 2**: Переключение трафика на старый Stage 6-8
- [ ] **Шаг 3**: Анализ проблемы в логах `llamaindex_performance`
- [ ] **Шаг 4**: Исправление → тестирование → повторное включение

### Документированный план отката
- [ ] **SLA**: максимум 10 минут на откат к legacy
- [ ] **Процедуры**: пошаговый список команд
- [ ] **Ответственные**: кто принимает решение об откате
- [ ] **Escalation**: когда вызывать внешнюю поддержку

---

## 📊 13. Дашборд и алерты

### Key metrics на дашборде
- [ ] **Latency**: P50, P95, P99 по операциям (retrieval, synthesis)
- [ ] **Cost**: дневные расходы vs. лимиты, тренды
- [ ] **Quality**: диверсификация, свежесть, cache hit rate
- [ ] **Errors**: процент ошибок по компонентам, топ-5 ошибок

### Alerting
- [ ] **Cost alerts**: 80% от дневного лимита
- [ ] **Performance alerts**: P95 latency > 5 секунд
- [ ] **Error alerts**: >5% ошибок за 10 минут
- [ ] **Capacity alerts**: Pinecone quota, Postgres connections

---

## ✅ 14. Финальная проверка

### Smoke test полной системы
- [ ] **Ingestion**: `python main.py llamaindex-ingest --limit 10`
- [ ] **Query test**: все 4 пресета работают
- [ ] **Monitoring**: `python main.py llamaindex-monitor` показывает метрики
- [ ] **Legacy toggle**: переключение работает за <30 секунд

### Production readiness
- [ ] **Documentation**: LLAMAINDEX_SETUP.md заполнена
- [ ] **Runbooks**: процедуры troubleshooting готовы
- [ ] **Team training**: команда знает новые команды
- [ ] **Backup plan**: legacy режим протестирован

### Go/No-go критерии
- [ ] **Performance**: latency ≤ текущей системы
- [ ] **Quality**: precision/recall ≥ текущей системы
- [ ] **Reliability**: error rate ≤ 1%
- [ ] **Cost**: в рамках запланированного бюджета

---

## 🎯 **PROD READY!**

**Когда все галочки ✅ поставлены — система готова к production!**

---

### Команды для быстрой проверки:

```bash
# Полная проверка системы
python setup_llamaindex.py

# Статус всех компонентов
python main.py llamaindex-monitor

# Тест всех пресетов
python main.py llamaindex-query "latest tech news" --preset qa
python main.py llamaindex-query "this week digest" --preset digest
python main.py llamaindex-query "video about AI" --preset shorts
python main.py llamaindex-query "future of robotics" --preset ideas

# Включить legacy при проблемах
python main.py llamaindex-legacy enable
```

**🚀 Готово к запуску!**