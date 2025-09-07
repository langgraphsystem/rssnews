# Продакшн-система обработки RSS-статей

## Архитектурная диаграмма

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   RSS Feeds     │    │    Redis        │    │   PostgreSQL    │
│                 │    │  (Queue/Cache)  │    │   (Primary)     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │                      │                      │
┌─────────▼───────────────────────▼──────────────────────▼───────┐
│                  RSS Processing Pipeline                       │
├───────────────────────────────────────────────────────────────┤
│ Stage 1: Polling      │ Stage 2: Validation  │ Stage 3: Dedup │
│ - Feed discovery      │ - Format validation  │ - URL hash     │
│ - RSS parsing         │ - Language detection │ - Text hash    │
│ - Etag/Modified       │ - Quality gates      │ - Similarity   │
├───────────────────────┼──────────────────────┼────────────────┤
│ Stage 4: Normalize    │ Stage 5: Clean       │ Stage 6: Index │
│ - URL canonicalization│ - HTML cleanup       │ - Text extract │
│ - Date parsing        │ - Text extraction    │ - Category     │
│ - Author extraction   │ - Content scoring    │ - Full-text    │
├───────────────────────┼──────────────────────┼────────────────┤
│ Stage 7: Chunking     │ Stage 8: Quality     │ Final: Ready   │
│ - Semantic segments   │ - Final validation   │ - For RAG      │
│ - Overlapping chunks  │ - Quality scoring    │ - Searchable   │
│ - Metadata injection  │ - Error handling     │ - Indexed      │
└───────────────────────────────────────────────────────────────┘
          │                      │                      │
          │                      │                      │
┌─────────▼───────┐    ┌─────────▼───────┐    ┌─────────▼───────┐
│   Monitoring    │    │   Diagnostics   │    │    Alerting     │
│ - Prometheus    │    │ - Performance   │    │ - Grafana       │
│ - Metrics       │    │ - Error tracking│    │ - PagerDuty     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Компоненты системы

### 1. Pipeline Controller
- **Цель**: Управление батчами и планирование
- **SLA**: Латентность p99 < 5s на батч
- **Масштаб**: До 50 параллельных воркеров

### 2. Stage Processors
- **Валидация**: Формат, язык, качественные пороги
- **Дедупликация**: URL/text hash, семантическое сходство
- **Нормализация**: URL, даты, авторы, категории
- **Очистка**: HTML→текст, качественная фильтрация
- **Чанкинг**: Семантические сегменты 200-800 слов
- **Индексация**: PostgreSQL FTS + векторы

### 3. Data Layer
#### PostgreSQL Tables (обновленная схема):

```sql
-- Feeds (источники RSS)
CREATE TABLE feeds (
    id SERIAL PRIMARY KEY,
    feed_url TEXT UNIQUE NOT NULL,
    feed_url_canon TEXT,
    language_guess TEXT,
    status TEXT DEFAULT 'active',
    etag TEXT,
    last_modified TEXT,
    health_score FLOAT DEFAULT 1.0,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_scanned_at TIMESTAMPTZ,
    notes TEXT DEFAULT ''
);

-- Raw articles (сырые данные)
CREATE TABLE raw (
    id BIGSERIAL PRIMARY KEY,
    row_id_raw BIGINT DEFAULT nextval('raw_id_seq'),
    feed_url TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT,
    url_hash TEXT NOT NULL,
    text_hash TEXT,
    found_at TIMESTAMPTZ DEFAULT NOW(),
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    published_at_raw TEXT,
    title TEXT,
    description TEXT,
    authors JSONB DEFAULT '[]',
    section TEXT,
    keywords JSONB DEFAULT '[]',
    tags JSONB DEFAULT '[]',
    full_text TEXT,
    html TEXT,
    status TEXT DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    retries INTEGER DEFAULT 0,
    error_reason TEXT,
    language TEXT,
    category_guess TEXT,
    
    -- Indexing
    UNIQUE(url_hash),
    INDEX(status, fetched_at),
    INDEX(published_at DESC),
    INDEX(source, status)
) PARTITION BY RANGE (fetched_at);

-- Articles index (обработанные статьи)
CREATE TABLE articles_index (
    id BIGSERIAL PRIMARY KEY,
    article_id TEXT UNIQUE NOT NULL, -- url_hash
    row_id_raw BIGINT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT,
    source_domain TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    published_is_estimated BOOLEAN DEFAULT FALSE,
    language TEXT NOT NULL,
    category TEXT,
    tags_norm JSONB DEFAULT '[]',
    word_count INTEGER NOT NULL,
    quality_flags JSONB DEFAULT '[]',
    quality_score FLOAT DEFAULT 0.0,
    is_duplicate BOOLEAN DEFAULT FALSE,
    dup_reason TEXT,
    dup_original_id TEXT,
    ready_for_chunking BOOLEAN DEFAULT FALSE,
    chunking_completed BOOLEAN DEFAULT FALSE,
    processing_version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes
    INDEX(source_domain, published_at DESC),
    INDEX(language, category),
    INDEX(published_at DESC),
    INDEX(quality_score DESC),
    INDEX(ready_for_chunking) WHERE ready_for_chunking = TRUE
);

-- Article chunks (для RAG)
CREATE TABLE article_chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT UNIQUE NOT NULL,
    article_id TEXT NOT NULL REFERENCES articles_index(article_id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    word_count_chunk INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    semantic_type TEXT, -- intro/body/list/conclusion
    
    -- Denormalized metadata for faster queries
    url TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    language TEXT NOT NULL,
    category TEXT,
    tags_norm JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes
    UNIQUE(article_id, chunk_index),
    INDEX(article_id),
    INDEX(source_domain, published_at DESC),
    INDEX(language, category)
);

-- Batch diagnostics
CREATE TABLE batch_diagnostics (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL, -- queued/running/partial_success/failed/succeeded
    worker_id TEXT,
    articles_total INTEGER NOT NULL,
    processed_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    avg_processing_time_ms INTEGER,
    p95_processing_time_ms INTEGER,
    p99_processing_time_ms INTEGER,
    rejection_reasons JSONB DEFAULT '{}',
    error_details JSONB DEFAULT '{}',
    cpu_percent FLOAT,
    mem_mb INTEGER,
    config_hash TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    correlation_id UUID,
    
    INDEX(batch_id, stage),
    INDEX(status, started_at DESC),
    INDEX(worker_id, started_at DESC)
);

-- Performance metrics
CREATE TABLE performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL,
    metric_value FLOAT NOT NULL,
    tags JSONB DEFAULT '{}',
    recorded_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX(metric_name, recorded_at DESC),
    INDEX(recorded_at DESC)
);

-- Configuration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. Queue System (Redis/Celery)
```python
# Queue priorities
QUEUE_PRIORITIES = {
    'critical': 9,      # System health, alerts
    'high': 7,          # Fresh articles (< 1h old)
    'normal': 5,        # Regular processing
    'low': 3,           # Backfill, analytics
    'bulk': 1           # Mass operations
}

# Queue routing
CELERY_ROUTES = {
    'pipeline.validate': {'queue': 'validation'},
    'pipeline.dedupe': {'queue': 'dedup'},
    'pipeline.normalize': {'queue': 'normalize'},
    'pipeline.clean': {'queue': 'clean'},
    'pipeline.chunk': {'queue': 'chunking'},
    'pipeline.index': {'queue': 'indexing'}
}
```

### 5. Monitoring & Alerting
#### SLI/SLO Метрики:
- **Availability**: 99.9%
- **Latency**: p99 < 5s per batch
- **Throughput**: ≥10k articles/min в пики  
- **Error Rate**: < 1%

#### Критические алерты:
- Error rate > 5% за 5 мин
- Latency p99 > 10s за 10 мин
- Queue depth > 100k
- DB connection pool exhausted
- Replication lag > 30s

## Этапы обработки

### Stage 1: Validation
- Проверка формата статьи
- Языковая детекция
- Применение качественных порогов

### Stage 2: Deduplication  
- URL hash сравнение
- Text hash для идентичного содержания
- Семантическое сходство (опционально)

### Stage 3: Normalization
- Канонизация URL
- Парсинг и нормализация дат
- Извлечение и нормализация авторов
- Категоризация

### Stage 4: Cleaning
- Конвертация HTML в чистый текст
- Удаление шума (реклама, навигация)
- Оценка качества контента

### Stage 5: Passporting
- Создание "паспорта" статьи
- Финальная валидация
- Подготовка метаданных

### Stage 6: Chunking  
- Разбивка на семантические сегменты
- Создание перекрывающихся окон
- Инжекция метаданных в chunks

### Stage 7: Indexing
- PostgreSQL Full-Text Search
- Тематические индексы
- Подготовка к поиску

## Развертывание и масштабирование

### Горизонтальное масштабирование:
- Celery workers: автомасштабирование 5-50 экземпляров
- PostgreSQL: read replicas для поиска
- Redis: кластер для высокой доступности

### Мониторинг производительности:
- Prometheus + Grafana дашборды
- Custom metrics для каждого этапа
- Алерты в PagerDuty

### DR/Backup:
- RPO ≤ 5 мин, RTO ≤ 30 мин  
- PostgreSQL PITR
- Еженедельные DR-drills