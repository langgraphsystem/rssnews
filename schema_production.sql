-- Production-grade RSS Processing System Database Schema
-- Supports millions of articles per day with high availability and performance

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- =====================================================
-- FEEDS TABLE - RSS sources with health tracking
-- =====================================================
CREATE TABLE feeds (
    id SERIAL PRIMARY KEY,
    feed_url TEXT NOT NULL UNIQUE,
    feed_url_canon TEXT NOT NULL,
    domain VARCHAR(255) NOT NULL,
    lang VARCHAR(10),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    priority INTEGER NOT NULL DEFAULT 1, -- 1=highest, 5=lowest
    trust_score INTEGER NOT NULL DEFAULT 50, -- 0-100
    
    -- Scheduling and health
    crawl_interval_minutes INTEGER NOT NULL DEFAULT 60,
    last_entry_date TIMESTAMP,
    last_crawled TIMESTAMP,
    last_success TIMESTAMP,
    no_updates_days INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    
    -- HTTP optimization
    etag TEXT,
    last_modified TEXT,
    
    -- Health metrics
    health_score INTEGER NOT NULL DEFAULT 100, -- 0-100
    avg_response_time_ms INTEGER DEFAULT 0,
    error_rate_24h DECIMAL(5,2) DEFAULT 0.0,
    duplicate_rate_24h DECIMAL(5,2) DEFAULT 0.0,
    content_quality_score DECIMAL(3,2) DEFAULT 1.0,
    
    -- Quotas and limits
    daily_quota INTEGER DEFAULT 10000,
    daily_processed INTEGER DEFAULT 0,
    rate_limit_rps INTEGER DEFAULT 1,
    
    -- Metadata
    notes TEXT,
    tags TEXT[],
    owner VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    checked_at TIMESTAMP,
    
    -- Data contracts
    expected_article_fields JSONB DEFAULT '{}',
    validation_rules JSONB DEFAULT '{}',
    
    CONSTRAINT feeds_trust_score_range CHECK (trust_score BETWEEN 0 AND 100),
    CONSTRAINT feeds_health_score_range CHECK (health_score BETWEEN 0 AND 100),
    CONSTRAINT feeds_priority_range CHECK (priority BETWEEN 1 AND 5)
);

-- Indexes for feeds
CREATE INDEX idx_feeds_active ON feeds(status) WHERE status = 'active';
CREATE INDEX idx_feeds_priority_health ON feeds(priority, health_score DESC) WHERE status = 'active';
CREATE INDEX idx_feeds_domain ON feeds(domain);
CREATE INDEX idx_feeds_next_crawl ON feeds(last_crawled, crawl_interval_minutes) WHERE status = 'active';
CREATE INDEX idx_feeds_trust_score ON feeds(trust_score DESC);

-- =====================================================
-- RAW ARTICLES - Partitioned by date for performance
-- =====================================================
CREATE TABLE raw_articles (
    id BIGSERIAL,
    feed_id INTEGER NOT NULL REFERENCES feeds(id),
    
    -- URLs and identification
    url TEXT NOT NULL,
    canonical_url TEXT,
    url_hash VARCHAR(64) NOT NULL,
    text_hash VARCHAR(64),
    
    -- Content
    title TEXT,
    description TEXT,
    content TEXT,
    authors TEXT[],
    
    -- Temporal data
    published_at_raw TEXT,
    published_at TIMESTAMP,
    published_is_estimated BOOLEAN DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Language and categorization
    language_raw VARCHAR(10),
    language_detected VARCHAR(5),
    language_confidence DECIMAL(3,2),
    section TEXT,
    tags TEXT[],
    keywords TEXT[],
    
    -- Processing state
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    processing_stage VARCHAR(50) DEFAULT 'fetched',
    batch_id VARCHAR(50),
    idempotency_key VARCHAR(100) UNIQUE,
    
    -- Distributed locking
    lock_owner VARCHAR(100),
    lock_acquired_at TIMESTAMP,
    lock_expires_at TIMESTAMP,
    
    -- Error handling and retries
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error_at TIMESTAMP,
    error_log JSONB DEFAULT '[]',
    
    -- Quality metrics
    word_count INTEGER,
    char_count INTEGER,
    quality_score DECIMAL(3,2) DEFAULT 0.0,
    quality_flags TEXT[] DEFAULT '{}',
    
    -- Metadata
    article_type VARCHAR(50),
    source_metadata JSONB DEFAULT '{}',
    extraction_metadata JSONB DEFAULT '{}',
    
    -- Versioning
    processing_version VARCHAR(20) DEFAULT '1.0',
    schema_version INTEGER DEFAULT 1,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (id, fetched_at),
    
    CONSTRAINT raw_articles_status_valid CHECK (status IN ('pending', 'processing', 'processed', 'rejected', 'failed', 'duplicate')),
    CONSTRAINT raw_articles_retry_limit CHECK (retry_count <= max_retries),
    CONSTRAINT raw_articles_quality_range CHECK (quality_score BETWEEN 0.0 AND 1.0)
    
) PARTITION BY RANGE (fetched_at);

-- Create partitions for the next 90 days (automated script should create more)
DO $$
DECLARE
    start_date DATE := CURRENT_DATE;
    end_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..90 LOOP
        end_date := start_date + INTERVAL '1 day';
        partition_name := 'raw_articles_' || TO_CHAR(start_date, 'YYYY_MM_DD');
        
        EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF raw_articles 
                       FOR VALUES FROM (%L) TO (%L)',
                       partition_name, start_date, end_date);
        
        -- Create indexes on each partition
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (status, batch_id) WHERE status IN (''pending'', ''processing'')',
                       'idx_' || partition_name || '_status_batch', partition_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (url_hash)',
                       'idx_' || partition_name || '_url_hash', partition_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (feed_id, fetched_at DESC)',
                       'idx_' || partition_name || '_feed_date', partition_name);
        
        start_date := end_date;
    END LOOP;
END $$;

-- Global indexes for raw_articles
CREATE INDEX idx_raw_articles_batch_status ON raw_articles(batch_id, status) WHERE batch_id IS NOT NULL;
CREATE INDEX idx_raw_articles_lock_owner ON raw_articles(lock_owner, lock_expires_at) WHERE lock_owner IS NOT NULL;
CREATE INDEX idx_raw_articles_retry ON raw_articles(retry_count, last_error_at) WHERE status = 'failed' AND retry_count < max_retries;
CREATE INDEX idx_raw_articles_idempotency ON raw_articles(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX idx_raw_articles_duplicate_check ON raw_articles(url_hash, text_hash) WHERE status NOT IN ('rejected', 'duplicate');

-- =====================================================
-- ARTICLES INDEX - Deduplicated and processed articles
-- =====================================================
CREATE TABLE articles_index (
    article_id VARCHAR(64) PRIMARY KEY,
    
    -- Source reference
    raw_article_id BIGINT NOT NULL,
    feed_id INTEGER NOT NULL REFERENCES feeds(id),
    
    -- URLs and identification
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source_domain VARCHAR(255) NOT NULL,
    url_hash VARCHAR(64) NOT NULL,
    text_hash VARCHAR(64) NOT NULL,
    
    -- Content
    title TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    description TEXT,
    clean_text TEXT NOT NULL,
    full_text TEXT,
    
    -- Authors and metadata
    authors TEXT[] DEFAULT '{}',
    authors_norm TEXT[] DEFAULT '{}',
    
    -- Temporal data
    published_at TIMESTAMP NOT NULL,
    published_is_estimated BOOLEAN DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL,
    
    -- Language and categorization
    language VARCHAR(5) NOT NULL,
    language_confidence DECIMAL(3,2) NOT NULL DEFAULT 0.0,
    category VARCHAR(50),
    category_confidence DECIMAL(3,2),
    subcategory VARCHAR(50),
    
    -- Tags and keywords
    tags_raw TEXT[] DEFAULT '{}',
    tags_norm TEXT[] DEFAULT '{}',
    keywords TEXT[] DEFAULT '{}',
    entities JSONB DEFAULT '{}',
    
    -- Content metrics
    word_count INTEGER NOT NULL,
    char_count INTEGER NOT NULL,
    reading_time_minutes INTEGER,
    
    -- Quality assessment
    quality_score DECIMAL(3,2) NOT NULL DEFAULT 0.0,
    quality_flags TEXT[] DEFAULT '{}',
    readability_score DECIMAL(3,2),
    sentiment_score DECIMAL(3,2), -- -1.0 to 1.0
    
    -- Deduplication
    is_duplicate BOOLEAN DEFAULT FALSE,
    dup_reason VARCHAR(50),
    dup_original_id VARCHAR(64),
    dup_similarity_score DECIMAL(3,2),
    dup_cluster_id VARCHAR(64),
    
    -- Processing state
    ready_for_chunking BOOLEAN DEFAULT FALSE,
    chunking_completed BOOLEAN DEFAULT FALSE,
    indexing_completed BOOLEAN DEFAULT FALSE,
    
    -- Content enrichment
    summary TEXT,
    top_image TEXT,
    images JSONB DEFAULT '[]',
    videos JSONB DEFAULT '[]',
    outlinks TEXT[] DEFAULT '{}',
    
    -- Paywalled and access
    paywalled BOOLEAN DEFAULT FALSE,
    partial BOOLEAN DEFAULT FALSE,
    access_level VARCHAR(20) DEFAULT 'public',
    
    -- SEO and social
    meta_description TEXT,
    social_shares INTEGER DEFAULT 0,
    social_metadata JSONB DEFAULT '{}',
    
    -- Versioning and metadata
    processing_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    schema_version INTEGER NOT NULL DEFAULT 1,
    extraction_metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT articles_quality_range CHECK (quality_score BETWEEN 0.0 AND 1.0),
    CONSTRAINT articles_sentiment_range CHECK (sentiment_score BETWEEN -1.0 AND 1.0),
    CONSTRAINT articles_language_valid CHECK (length(language) BETWEEN 2 AND 5),
    CONSTRAINT articles_word_count_positive CHECK (word_count > 0)
);

-- Indexes for articles_index
CREATE INDEX idx_articles_domain_date ON articles_index(source_domain, published_at DESC);
CREATE INDEX idx_articles_lang_cat_date ON articles_index(language, category, published_at DESC);
CREATE INDEX idx_articles_quality_date ON articles_index(quality_score DESC, published_at DESC) WHERE quality_score >= 0.7;
CREATE INDEX idx_articles_ready_chunking ON articles_index(ready_for_chunking) WHERE ready_for_chunking = TRUE AND chunking_completed = FALSE;
CREATE INDEX idx_articles_feed_date ON articles_index(feed_id, published_at DESC);
CREATE INDEX idx_articles_duplicates ON articles_index(is_duplicate, dup_original_id) WHERE is_duplicate = TRUE;
CREATE INDEX idx_articles_category_date ON articles_index(category, published_at DESC) WHERE category IS NOT NULL;
CREATE INDEX idx_articles_url_hash ON articles_index(url_hash);
CREATE INDEX idx_articles_text_hash ON articles_index(text_hash);

-- GIN indexes for arrays and JSONB
CREATE INDEX idx_articles_tags ON articles_index USING GIN(tags_norm);
CREATE INDEX idx_articles_keywords ON articles_index USING GIN(keywords);
CREATE INDEX idx_articles_entities ON articles_index USING GIN(entities);
CREATE INDEX idx_articles_authors ON articles_index USING GIN(authors_norm);

-- =====================================================
-- ARTICLE CHUNKS - For search and AI processing
-- =====================================================
CREATE TABLE article_chunks (
    id BIGSERIAL PRIMARY KEY,
    article_id VARCHAR(64) NOT NULL REFERENCES articles_index(article_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    
    -- Chunk content
    text TEXT NOT NULL,
    text_clean TEXT NOT NULL,
    text_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(text_clean, '')), 'A')
    ) STORED,
    
    -- Chunk metadata
    word_count_chunk INTEGER NOT NULL,
    char_count_chunk INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    
    -- Semantic information
    semantic_type VARCHAR(20) DEFAULT 'body', -- 'intro', 'body', 'conclusion', 'list', 'quote', 'code'
    importance_score DECIMAL(3,2) DEFAULT 0.5,
    
    -- Denormalized fields for fast search (avoiding JOINs)
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    source_domain VARCHAR(255) NOT NULL,
    published_at TIMESTAMP NOT NULL,
    language VARCHAR(5) NOT NULL,
    category VARCHAR(50),
    tags_norm TEXT[] DEFAULT '{}',
    authors_norm TEXT[] DEFAULT '{}',
    quality_score DECIMAL(3,2) NOT NULL,
    
    -- Vector embeddings (for future AI features)
    embedding_vector VECTOR(768), -- Assuming 768-dim embeddings
    embedding_model VARCHAR(50),
    embedding_created_at TIMESTAMP,
    
    -- Processing metadata
    chunk_strategy VARCHAR(50) NOT NULL DEFAULT 'paragraph',
    processing_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uk_article_chunk UNIQUE(article_id, chunk_index),
    CONSTRAINT chunks_word_count_positive CHECK (word_count_chunk > 0),
    CONSTRAINT chunks_char_positions CHECK (char_start >= 0 AND char_end > char_start),
    CONSTRAINT chunks_importance_range CHECK (importance_score BETWEEN 0.0 AND 1.0)
);

-- Indexes for article_chunks
CREATE INDEX idx_chunks_text_vector ON article_chunks USING GIN(text_vector);
CREATE INDEX idx_chunks_article_id ON article_chunks(article_id, chunk_index);
CREATE INDEX idx_chunks_search_composite ON article_chunks(language, category, published_at DESC, quality_score DESC);
CREATE INDEX idx_chunks_domain_date ON article_chunks(source_domain, published_at DESC);
CREATE INDEX idx_chunks_semantic_type ON article_chunks(semantic_type, importance_score DESC);
CREATE INDEX idx_chunks_embedding ON article_chunks USING ivfflat(embedding_vector) WITH (lists = 100);

-- GIN indexes for arrays
CREATE INDEX idx_chunks_tags ON article_chunks USING GIN(tags_norm);
CREATE INDEX idx_chunks_authors ON article_chunks USING GIN(authors_norm);

-- =====================================================
-- BATCH PROCESSING TABLES
-- =====================================================
CREATE TABLE batches (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(50) UNIQUE NOT NULL,
    
    -- Batch configuration
    batch_size INTEGER NOT NULL DEFAULT 200,
    priority INTEGER NOT NULL DEFAULT 1,
    source_filter JSONB DEFAULT '{}',
    processing_config JSONB DEFAULT '{}',
    
    -- Processing state
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    current_stage VARCHAR(50) DEFAULT 'planning',
    articles_total INTEGER NOT NULL DEFAULT 0,
    articles_processed INTEGER DEFAULT 0,
    articles_successful INTEGER DEFAULT 0,
    articles_failed INTEGER DEFAULT 0,
    articles_skipped INTEGER DEFAULT 0,
    
    -- Worker assignment
    worker_id VARCHAR(100),
    worker_node VARCHAR(100),
    assigned_at TIMESTAMP,
    
    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    estimated_completion TIMESTAMP,
    processing_time_ms BIGINT,
    
    -- Error handling
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 2,
    last_error JSONB,
    error_stage VARCHAR(50),
    
    -- Idempotency and correlation
    idempotency_key VARCHAR(100) UNIQUE,
    correlation_id VARCHAR(50),
    parent_batch_id VARCHAR(50),
    
    -- Quality metrics
    avg_quality_score DECIMAL(3,2),
    duplicate_rate DECIMAL(5,2),
    rejection_rate DECIMAL(5,2),
    
    -- Resource usage
    memory_usage_mb INTEGER,
    cpu_usage_percent DECIMAL(5,2),
    
    -- Metadata
    config_hash VARCHAR(64),
    processing_version VARCHAR(20) DEFAULT '1.0',
    notes TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT batches_status_valid CHECK (status IN ('created', 'planning', 'ready', 'processing', 'completed', 'failed', 'cancelled')),
    CONSTRAINT batches_articles_counts CHECK (
        articles_processed = articles_successful + articles_failed + articles_skipped
        AND articles_processed <= articles_total
    )
);

-- Indexes for batches
CREATE INDEX idx_batches_status ON batches(status, priority) WHERE status IN ('ready', 'processing');
CREATE INDEX idx_batches_worker ON batches(worker_id, status) WHERE worker_id IS NOT NULL;
CREATE INDEX idx_batches_retry ON batches(retry_count, status) WHERE status = 'failed' AND retry_count < max_retries;
CREATE INDEX idx_batches_created ON batches(created_at DESC);
CREATE INDEX idx_batches_correlation ON batches(correlation_id) WHERE correlation_id IS NOT NULL;

-- =====================================================
-- BATCH DIAGNOSTICS - Detailed processing metrics
-- =====================================================
CREATE TABLE batch_diagnostics (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(50) NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
    
    -- Processing stage
    stage VARCHAR(50) NOT NULL,
    stage_order INTEGER NOT NULL,
    
    -- Execution details
    worker_id VARCHAR(100),
    worker_node VARCHAR(100),
    
    -- Article metrics
    articles_input INTEGER NOT NULL DEFAULT 0,
    articles_output INTEGER NOT NULL DEFAULT 0,
    articles_rejected INTEGER DEFAULT 0,
    articles_duplicates INTEGER DEFAULT 0,
    articles_errors INTEGER DEFAULT 0,
    
    -- Content metrics
    avg_word_count DECIMAL,
    avg_quality_score DECIMAL(3,2),
    avg_processing_time_ms DECIMAL,
    p50_processing_time_ms DECIMAL,
    p95_processing_time_ms DECIMAL,
    p99_processing_time_ms DECIMAL,
    
    -- Error analysis
    error_types JSONB DEFAULT '{}',
    rejection_reasons JSONB DEFAULT '{}',
    warning_count INTEGER DEFAULT 0,
    
    -- Resource usage
    memory_usage_mb INTEGER,
    cpu_usage_percent DECIMAL(5,2),
    disk_io_mb INTEGER,
    network_io_mb INTEGER,
    
    -- Configuration
    stage_config JSONB DEFAULT '{}',
    config_hash VARCHAR(64),
    processing_version VARCHAR(20) DEFAULT '1.0',
    
    -- Timing
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms BIGINT,
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    
    -- Correlation
    correlation_id VARCHAR(50),
    trace_id VARCHAR(100),
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT batch_diag_status_valid CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT batch_diag_articles_balance CHECK (articles_output + articles_rejected <= articles_input)
);

-- Indexes for batch_diagnostics
CREATE INDEX idx_batch_diag_batch_stage ON batch_diagnostics(batch_id, stage_order);
CREATE INDEX idx_batch_diag_performance ON batch_diagnostics(stage, avg_processing_time_ms DESC);
CREATE INDEX idx_batch_diag_errors ON batch_diagnostics(status, articles_errors DESC) WHERE articles_errors > 0;
CREATE INDEX idx_batch_diag_correlation ON batch_diagnostics(correlation_id) WHERE correlation_id IS NOT NULL;

-- =====================================================
-- PERFORMANCE METRICS - Time-series data
-- =====================================================
CREATE TABLE performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    
    -- Metric identification
    metric_name VARCHAR(100) NOT NULL,
    metric_type VARCHAR(20) NOT NULL DEFAULT 'gauge', -- gauge, counter, histogram
    
    -- Metric value
    metric_value DECIMAL NOT NULL,
    metric_unit VARCHAR(20),
    
    -- Dimensions/tags
    tags JSONB DEFAULT '{}',
    
    -- Context
    component VARCHAR(50),
    service VARCHAR(50),
    environment VARCHAR(20) DEFAULT 'production',
    version VARCHAR(20),
    
    -- Correlation
    correlation_id VARCHAR(50),
    trace_id VARCHAR(100),
    
    -- Time
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Hypertable for time-series (if using TimescaleDB)
-- SELECT create_hypertable('performance_metrics', 'recorded_at', if_not_exists => TRUE);

-- Indexes for performance_metrics
CREATE INDEX idx_metrics_name_time ON performance_metrics(metric_name, recorded_at DESC);
CREATE INDEX idx_metrics_component_time ON performance_metrics(component, recorded_at DESC);
CREATE INDEX idx_metrics_tags ON performance_metrics USING GIN(tags);
CREATE INDEX idx_metrics_correlation ON performance_metrics(correlation_id) WHERE correlation_id IS NOT NULL;

-- =====================================================
-- DISTRIBUTED LOCKS TABLE
-- =====================================================
CREATE TABLE distributed_locks (
    lock_key VARCHAR(255) PRIMARY KEY,
    owner VARCHAR(100) NOT NULL,
    acquired_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT locks_valid_expiry CHECK (expires_at > acquired_at)
);

CREATE INDEX idx_locks_expiry ON distributed_locks(expires_at);
CREATE INDEX idx_locks_owner ON distributed_locks(owner);

-- =====================================================
-- CONFIGURATION TABLE
-- =====================================================
CREATE TABLE system_config (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    value_type VARCHAR(20) DEFAULT 'string', -- string, number, boolean, json
    description TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    is_sensitive BOOLEAN DEFAULT FALSE,
    validation_pattern TEXT,
    default_value TEXT,
    environment VARCHAR(20) DEFAULT 'production',
    component VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- Insert default configuration
INSERT INTO system_config (key, value, value_type, description, component) VALUES
('batch.default_size', '200', 'number', 'Default batch size for processing', 'pipeline'),
('batch.max_size', '300', 'number', 'Maximum allowed batch size', 'pipeline'),
('batch.min_size', '100', 'number', 'Minimum allowed batch size', 'pipeline'),
('pipeline.max_retries', '3', 'number', 'Maximum retry attempts for failed articles', 'pipeline'),
('pipeline.timeout_seconds', '300', 'number', 'Processing timeout per batch', 'pipeline'),
('quality.min_score', '0.3', 'number', 'Minimum quality score for acceptance', 'quality'),
('dedup.similarity_threshold', '0.9', 'number', 'Text similarity threshold for duplicates', 'deduplication'),
('monitoring.metrics_retention_days', '90', 'number', 'How long to keep metrics data', 'monitoring'),
('feeds.health_check_interval_minutes', '60', 'number', 'Health check interval for feeds', 'feeds'),
('feeds.min_health_score', '50', 'number', 'Minimum health score to keep feed active', 'feeds')
ON CONFLICT (key) DO NOTHING;

-- =====================================================
-- FUNCTIONS AND PROCEDURES
-- =====================================================

-- Function to get next batch for processing
CREATE OR REPLACE FUNCTION get_next_batch(
    worker_id_param VARCHAR(100),
    preferred_batch_size INTEGER DEFAULT 200
) RETURNS TABLE (
    batch_id VARCHAR(50),
    article_ids BIGINT[]
) AS $$
DECLARE
    batch_uuid VARCHAR(50);
    lock_acquired BOOLEAN := FALSE;
    batch_articles BIGINT[];
BEGIN
    -- Generate batch ID
    batch_uuid := 'batch_' || EXTRACT(EPOCH FROM NOW())::BIGINT || '_' || LEFT(MD5(RANDOM()::TEXT), 8);
    
    -- Try to acquire distributed lock
    BEGIN
        INSERT INTO distributed_locks (lock_key, owner, expires_at)
        VALUES ('batch_creation', worker_id_param, NOW() + INTERVAL '30 seconds');
        lock_acquired := TRUE;
    EXCEPTION WHEN unique_violation THEN
        -- Another worker is creating a batch
        RETURN;
    END;
    
    -- Select articles for batch with intelligent prioritization
    SELECT ARRAY(
        SELECT ra.id
        FROM raw_articles ra
        JOIN feeds f ON ra.feed_id = f.id
        WHERE ra.status = 'pending'
          AND ra.lock_owner IS NULL
          AND f.status = 'active'
          AND f.health_score >= 50
        ORDER BY 
            -- Priority factors
            f.priority ASC,                    -- Feed priority
            f.trust_score DESC,               -- Feed trust
            ra.fetched_at ASC,                -- FIFO for fairness
            CASE WHEN ra.retry_count > 0 THEN 1 ELSE 0 END ASC  -- New articles first
        LIMIT preferred_batch_size
        FOR UPDATE SKIP LOCKED
    ) INTO batch_articles;
    
    -- If no articles found, release lock and return
    IF array_length(batch_articles, 1) IS NULL THEN
        DELETE FROM distributed_locks WHERE lock_key = 'batch_creation' AND owner = worker_id_param;
        RETURN;
    END IF;
    
    -- Create batch record
    INSERT INTO batches (
        batch_id, batch_size, articles_total, status, 
        worker_id, idempotency_key, correlation_id
    ) VALUES (
        batch_uuid, 
        array_length(batch_articles, 1),
        array_length(batch_articles, 1),
        'ready',
        worker_id_param,
        batch_uuid || '_' || worker_id_param,
        'corr_' || LEFT(MD5(RANDOM()::TEXT), 16)
    );
    
    -- Lock selected articles
    UPDATE raw_articles 
    SET 
        batch_id = batch_uuid,
        lock_owner = worker_id_param,
        lock_acquired_at = NOW(),
        lock_expires_at = NOW() + INTERVAL '1 hour',
        status = 'processing'
    WHERE id = ANY(batch_articles);
    
    -- Release batch creation lock
    DELETE FROM distributed_locks WHERE lock_key = 'batch_creation' AND owner = worker_id_param;
    
    -- Return batch info
    RETURN QUERY SELECT batch_uuid, batch_articles;
END;
$$ LANGUAGE plpgsql;

-- Function to cleanup expired locks
CREATE OR REPLACE FUNCTION cleanup_expired_locks() RETURNS INTEGER AS $$
DECLARE
    cleaned_count INTEGER;
BEGIN
    -- Reset expired article locks
    UPDATE raw_articles 
    SET 
        lock_owner = NULL,
        lock_acquired_at = NULL,
        lock_expires_at = NULL,
        status = 'pending',
        batch_id = NULL
    WHERE lock_expires_at < NOW() 
      AND lock_owner IS NOT NULL;
    
    GET DIAGNOSTICS cleaned_count = ROW_COUNT;
    
    -- Clean up expired distributed locks
    DELETE FROM distributed_locks WHERE expires_at < NOW();
    
    RETURN cleaned_count;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate feed health scores
CREATE OR REPLACE FUNCTION update_feed_health_scores() RETURNS VOID AS $$
BEGIN
    UPDATE feeds SET 
        health_score = GREATEST(0, LEAST(100, (
            -- Base score starts at 100
            100 
            -- Subtract for response time (0-30 points)
            - CASE 
                WHEN avg_response_time_ms > 10000 THEN 30
                WHEN avg_response_time_ms > 5000 THEN 20
                WHEN avg_response_time_ms > 2000 THEN 10
                ELSE 0
              END
            -- Subtract for error rate (0-40 points)
            - LEAST(40, error_rate_24h * 0.4)
            -- Subtract for high duplicate rate (0-20 points)
            - CASE 
                WHEN duplicate_rate_24h > 50 THEN 20
                WHEN duplicate_rate_24h > 30 THEN 10
                ELSE 0
              END
            -- Subtract for consecutive failures (0-30 points)
            - LEAST(30, consecutive_failures * 5)
            -- Add for content quality (0-20 points)
            + (content_quality_score * 20)
        )::INTEGER)),
        updated_at = NOW()
    WHERE last_crawled > NOW() - INTERVAL '24 hours';
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- VIEWS FOR COMMON QUERIES
-- =====================================================

-- Active batches with progress
CREATE VIEW active_batches AS
SELECT 
    b.batch_id,
    b.status,
    b.current_stage,
    b.articles_total,
    b.articles_processed,
    ROUND((b.articles_processed::DECIMAL / NULLIF(b.articles_total, 0)) * 100, 1) as progress_percent,
    b.worker_id,
    b.started_at,
    EXTRACT(EPOCH FROM (NOW() - b.started_at))::INTEGER as running_seconds,
    b.estimated_completion
FROM batches b
WHERE b.status IN ('processing', 'ready')
ORDER BY b.started_at;

-- Feed health summary
CREATE VIEW feed_health_summary AS
SELECT 
    f.domain,
    COUNT(*) as total_feeds,
    COUNT(*) FILTER (WHERE f.status = 'active') as active_feeds,
    AVG(f.health_score) as avg_health_score,
    AVG(f.error_rate_24h) as avg_error_rate,
    AVG(f.duplicate_rate_24h) as avg_duplicate_rate,
    SUM(f.daily_processed) as daily_total_processed
FROM feeds f
GROUP BY f.domain
ORDER BY avg_health_score DESC;

-- Recent processing metrics
CREATE VIEW processing_metrics_hourly AS
SELECT 
    DATE_TRUNC('hour', recorded_at) as hour,
    metric_name,
    AVG(metric_value) as avg_value,
    MAX(metric_value) as max_value,
    MIN(metric_value) as min_value,
    COUNT(*) as sample_count
FROM performance_metrics
WHERE recorded_at > NOW() - INTERVAL '24 hours'
GROUP BY hour, metric_name
ORDER BY hour DESC, metric_name;

-- =====================================================
-- TRIGGERS
-- =====================================================

-- Update timestamps
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER feeds_updated_at BEFORE UPDATE ON feeds FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER raw_articles_updated_at BEFORE UPDATE ON raw_articles FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER articles_index_updated_at BEFORE UPDATE ON articles_index FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER batches_updated_at BEFORE UPDATE ON batches FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- Batch progress calculation
CREATE OR REPLACE FUNCTION update_batch_progress()
RETURNS TRIGGER AS $$
BEGIN
    -- Update batch progress when articles change status
    UPDATE batches SET
        articles_processed = (
            SELECT COUNT(*) FROM raw_articles 
            WHERE batch_id = NEW.batch_id 
            AND status IN ('processed', 'rejected', 'duplicate')
        ),
        articles_successful = (
            SELECT COUNT(*) FROM raw_articles 
            WHERE batch_id = NEW.batch_id 
            AND status = 'processed'
        ),
        articles_failed = (
            SELECT COUNT(*) FROM raw_articles 
            WHERE batch_id = NEW.batch_id 
            AND status IN ('rejected', 'failed')
        ),
        updated_at = NOW()
    WHERE batch_id = NEW.batch_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER raw_articles_batch_progress 
    AFTER UPDATE OF status ON raw_articles 
    FOR EACH ROW 
    WHEN (NEW.batch_id IS NOT NULL AND OLD.status != NEW.status)
    EXECUTE FUNCTION update_batch_progress();

-- =====================================================
-- MAINTENANCE PROCEDURES
-- =====================================================

-- Daily maintenance procedure
CREATE OR REPLACE FUNCTION daily_maintenance() RETURNS VOID AS $$
BEGIN
    -- Clean up old metrics (keep 90 days)
    DELETE FROM performance_metrics WHERE recorded_at < NOW() - INTERVAL '90 days';
    
    -- Clean up old batch diagnostics (keep 30 days)
    DELETE FROM batch_diagnostics WHERE created_at < NOW() - INTERVAL '30 days';
    
    -- Clean up completed batches (keep 7 days)
    DELETE FROM batches WHERE status IN ('completed', 'failed') AND created_at < NOW() - INTERVAL '7 days';
    
    -- Update feed health scores
    PERFORM update_feed_health_scores();
    
    -- Clean up expired locks
    PERFORM cleanup_expired_locks();
    
    -- Update table statistics
    ANALYZE feeds, raw_articles, articles_index, article_chunks, batches;
    
    -- Log maintenance completion
    INSERT INTO performance_metrics (metric_name, metric_value, component, tags)
    VALUES ('maintenance.daily_completed', 1, 'system', '{"type": "maintenance"}');
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- GRANTS AND SECURITY
-- =====================================================

-- Create roles
CREATE ROLE rss_reader;
CREATE ROLE rss_writer; 
CREATE ROLE rss_admin;

-- Grant permissions
GRANT SELECT ON ALL TABLES IN SCHEMA public TO rss_reader;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO rss_writer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO rss_admin;

-- Grant sequence usage
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO rss_writer, rss_admin;

-- Function permissions
GRANT EXECUTE ON FUNCTION get_next_batch(VARCHAR, INTEGER) TO rss_writer;
GRANT EXECUTE ON FUNCTION cleanup_expired_locks() TO rss_writer;
GRANT EXECUTE ON FUNCTION update_feed_health_scores() TO rss_writer;
GRANT EXECUTE ON FUNCTION daily_maintenance() TO rss_admin;

-- RLS policies (Row Level Security) - Example for multi-tenancy
-- ALTER TABLE feeds ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY feeds_owner_policy ON feeds FOR ALL TO rss_writer USING (owner = current_user);

-- =====================================================
-- COMMENTS AND DOCUMENTATION
-- =====================================================

COMMENT ON TABLE feeds IS 'RSS feed sources with health tracking and quotas';
COMMENT ON TABLE raw_articles IS 'Raw articles from RSS feeds, partitioned by date';
COMMENT ON TABLE articles_index IS 'Processed and deduplicated articles index';
COMMENT ON TABLE article_chunks IS 'Article content broken into searchable chunks';
COMMENT ON TABLE batches IS 'Processing batches for parallel execution';
COMMENT ON TABLE batch_diagnostics IS 'Detailed metrics for each processing stage';
COMMENT ON TABLE performance_metrics IS 'Time-series performance and business metrics';
COMMENT ON TABLE distributed_locks IS 'Distributed locking for coordination';
COMMENT ON TABLE system_config IS 'System configuration parameters';

COMMENT ON FUNCTION get_next_batch(VARCHAR, INTEGER) IS 'Gets next batch of articles for processing with intelligent prioritization';
COMMENT ON FUNCTION cleanup_expired_locks() IS 'Cleans up expired locks and resets article status';
COMMENT ON FUNCTION update_feed_health_scores() IS 'Recalculates health scores for all feeds';
COMMENT ON FUNCTION daily_maintenance() IS 'Daily maintenance tasks including cleanup and stats updates';