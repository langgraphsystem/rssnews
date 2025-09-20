-- LlamaIndex Database Schema Extensions
-- =====================================
--
-- Additional tables and indexes for LlamaIndex integration
-- Run after existing RSS schema is created

-- LlamaIndex nodes table (dual storage with article_chunks)
CREATE TABLE IF NOT EXISTS llamaindex_nodes (
    id SERIAL PRIMARY KEY,
    node_id VARCHAR(255) UNIQUE NOT NULL,  -- {article_id}#{chunk_index}

    -- Core content
    text TEXT NOT NULL,

    -- Source tracking
    article_id INTEGER REFERENCES raw(id),
    chunk_index INTEGER NOT NULL,

    -- LlamaIndex metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Vector storage (pgvector)
    embedding vector(768),  -- Gemini embedding dimension

    -- FTS (Full-Text Search)
    fts_vector tsvector,

    -- Routing metadata
    language VARCHAR(5) NOT NULL DEFAULT 'en',  -- en/ru
    namespace VARCHAR(20) NOT NULL DEFAULT 'hot',  -- hot/archive

    -- Processing metadata
    processing_version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- LlamaIndex extractors metadata
    extracted_keywords TEXT[],
    extracted_questions TEXT[],
    extracted_titles TEXT[],

    -- Quality scores
    relevance_score FLOAT DEFAULT 0.0,
    freshness_score FLOAT DEFAULT 0.0,

    UNIQUE(article_id, chunk_index, processing_version)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_node_id ON llamaindex_nodes(node_id);
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_article_id ON llamaindex_nodes(article_id);
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_language ON llamaindex_nodes(language);
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_namespace ON llamaindex_nodes(namespace);
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_created_at ON llamaindex_nodes(created_at);

-- FTS index
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_fts ON llamaindex_nodes USING gin(fts_vector);

-- Vector similarity index (requires pgvector extension)
-- CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_embedding ON llamaindex_nodes
-- USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Metadata indexes
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_metadata ON llamaindex_nodes USING gin(metadata);

-- Query performance and analytics
CREATE TABLE IF NOT EXISTS llamaindex_queries (
    id SERIAL PRIMARY KEY,

    -- Query details
    query_text TEXT NOT NULL,
    query_hash VARCHAR(64) NOT NULL,  -- MD5 hash for deduplication

    -- Routing information
    language VARCHAR(5) NOT NULL,
    preset VARCHAR(20) NOT NULL,  -- qa/digest/shorts/ideas

    -- Performance metrics
    processing_time_ms INTEGER,
    nodes_retrieved INTEGER,
    nodes_used INTEGER,

    -- Quality metrics
    domain_diversity INTEGER,
    freshness_avg FLOAT,
    relevance_avg FLOAT,

    -- Cost tracking
    llm_provider VARCHAR(20),  -- openai/gemini
    cost_estimate DECIMAL(10, 6),

    -- Result metadata
    response_length INTEGER,
    sources_count INTEGER,
    cache_hit BOOLEAN DEFAULT FALSE,

    -- Timing
    created_at TIMESTAMP DEFAULT NOW(),

    -- Source tracking
    node_ids TEXT[],  -- Array of node_ids used in response
    namespaces_searched TEXT[]  -- hot/archive
);

-- Query analytics indexes
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_hash ON llamaindex_queries(query_hash);
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_created_at ON llamaindex_queries(created_at);
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_language ON llamaindex_queries(language);
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_preset ON llamaindex_queries(preset);
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_llm_provider ON llamaindex_queries(llm_provider);

-- Cost tracking and budgets
CREATE TABLE IF NOT EXISTS llamaindex_costs (
    id SERIAL PRIMARY KEY,

    -- Time period
    date DATE NOT NULL,
    hour INTEGER, -- 0-23, NULL for daily aggregates

    -- Provider costs
    openai_cost DECIMAL(10, 6) DEFAULT 0,
    gemini_cost DECIMAL(10, 6) DEFAULT 0,
    embedding_cost DECIMAL(10, 6) DEFAULT 0,
    total_cost DECIMAL(10, 6) DEFAULT 0,

    -- Usage counts
    queries_count INTEGER DEFAULT 0,
    nodes_processed INTEGER DEFAULT 0,
    embeddings_created INTEGER DEFAULT 0,

    -- Limits and alerts
    daily_limit DECIMAL(10, 6) DEFAULT 100.00,
    alert_threshold DECIMAL(10, 6) DEFAULT 80.00,
    alert_sent BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(date, hour)
);

-- Cost tracking indexes
CREATE INDEX IF NOT EXISTS idx_llamaindex_costs_date ON llamaindex_costs(date);
CREATE INDEX IF NOT EXISTS idx_llamaindex_costs_hour ON llamaindex_costs(date, hour);

-- Performance monitoring
CREATE TABLE IF NOT EXISTS llamaindex_performance (
    id SERIAL PRIMARY KEY,

    -- Operation details
    operation VARCHAR(50) NOT NULL,  -- ingest/query/migrate
    component VARCHAR(50),  -- chunking/retrieval/synthesis

    -- Performance metrics
    duration_ms INTEGER NOT NULL,
    memory_usage_mb INTEGER,
    cpu_usage_percent FLOAT,

    -- Quality metrics
    success BOOLEAN NOT NULL,
    error_message TEXT,

    -- Context
    batch_size INTEGER,
    concurrent_ops INTEGER,

    -- Timing
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP DEFAULT NOW(),

    -- Additional metadata
    metadata JSONB DEFAULT '{}'
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_operation ON llamaindex_performance(operation);
CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_component ON llamaindex_performance(component);
CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_completed_at ON llamaindex_performance(completed_at);
CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_success ON llamaindex_performance(success);

-- Migration tracking
CREATE TABLE IF NOT EXISTS llamaindex_migrations (
    id SERIAL PRIMARY KEY,

    -- Migration details
    migration_name VARCHAR(100) NOT NULL,
    migration_type VARCHAR(50) NOT NULL,  -- fresh/backfill/archive

    -- Progress tracking
    total_articles INTEGER,
    processed_articles INTEGER,
    successful_articles INTEGER,
    failed_articles INTEGER,

    -- Status
    status VARCHAR(20) DEFAULT 'running',  -- running/completed/failed/cancelled

    -- Performance
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    estimated_completion TIMESTAMP,

    -- Error tracking
    last_error TEXT,
    error_count INTEGER DEFAULT 0,

    -- Metadata
    configuration JSONB DEFAULT '{}',

    UNIQUE(migration_name)
);

-- Migration indexes
CREATE INDEX IF NOT EXISTS idx_llamaindex_migrations_status ON llamaindex_migrations(status);
CREATE INDEX IF NOT EXISTS idx_llamaindex_migrations_started_at ON llamaindex_migrations(started_at);

-- System configuration and feature flags
CREATE TABLE IF NOT EXISTS llamaindex_config (
    id SERIAL PRIMARY KEY,

    -- Configuration key
    key VARCHAR(100) UNIQUE NOT NULL,

    -- Configuration value
    value JSONB NOT NULL,

    -- Metadata
    description TEXT,
    category VARCHAR(50),  -- routing/performance/costs/features

    -- Versioning
    version INTEGER DEFAULT 1,
    active BOOLEAN DEFAULT TRUE,

    -- Timing
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50) DEFAULT 'system'
);

-- Config indexes
CREATE INDEX IF NOT EXISTS idx_llamaindex_config_key ON llamaindex_config(key);
CREATE INDEX IF NOT EXISTS idx_llamaindex_config_category ON llamaindex_config(category);
CREATE INDEX IF NOT EXISTS idx_llamaindex_config_active ON llamaindex_config(active);

-- Insert default configuration
INSERT INTO llamaindex_config (key, value, description, category) VALUES
('routing.default_language', '"auto"', 'Default language routing: auto, en, ru', 'routing'),
('routing.namespace_days.hot', '30', 'Days to keep in hot namespace', 'routing'),
('routing.namespace_days.archive', '999999', 'Archive namespace threshold', 'routing'),
('routing.alpha_default', '0.5', 'Default hybrid search alpha (0=vector, 1=FTS)', 'routing'),

('performance.similarity_top_k', '24', 'Default similarity top-k for retrieval', 'performance'),
('performance.max_sources', '10', 'Default maximum sources in response', 'performance'),
('performance.cache_ttl_minutes', '15', 'Query cache TTL in minutes', 'performance'),
('performance.batch_size', '10', 'Default batch size for processing', 'performance'),

('costs.daily_limit_total', '100.00', 'Total daily cost limit in USD', 'costs'),
('costs.daily_limit_openai', '50.00', 'OpenAI daily cost limit in USD', 'costs'),
('costs.daily_limit_gemini', '30.00', 'Gemini daily cost limit in USD', 'costs'),
('costs.alert_threshold', '0.8', 'Alert when reaching this fraction of limit', 'costs'),

('features.legacy_mode', 'false', 'Enable legacy mode fallback', 'features'),
('features.domain_diversification', 'true', 'Enable domain diversification', 'features'),
('features.freshness_boost', 'true', 'Enable freshness boosting', 'features'),
('features.semantic_rerank', 'true', 'Enable semantic reranking', 'features'),
('features.query_cache', 'true', 'Enable query caching', 'features')

ON CONFLICT (key) DO NOTHING;

-- Update articles_index table to track LlamaIndex processing
ALTER TABLE articles_index
ADD COLUMN IF NOT EXISTS llamaindex_processed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS llamaindex_nodes_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS llamaindex_processed_at TIMESTAMP;

-- Index for LlamaIndex processing status
CREATE INDEX IF NOT EXISTS idx_articles_index_llamaindex_processed
ON articles_index(llamaindex_processed);

-- Views for analytics and monitoring

-- Daily cost summary
CREATE OR REPLACE VIEW llamaindex_daily_costs AS
SELECT
    date,
    SUM(total_cost) as daily_total,
    SUM(openai_cost) as daily_openai,
    SUM(gemini_cost) as daily_gemini,
    SUM(embedding_cost) as daily_embedding,
    SUM(queries_count) as daily_queries,
    MAX(daily_limit) as limit_total,
    CASE
        WHEN MAX(daily_limit) > 0 THEN SUM(total_cost) / MAX(daily_limit) * 100
        ELSE 0
    END as limit_usage_percent
FROM llamaindex_costs
WHERE hour IS NULL  -- Daily aggregates only
GROUP BY date
ORDER BY date DESC;

-- Query performance summary
CREATE OR REPLACE VIEW llamaindex_query_stats AS
SELECT
    DATE(created_at) as date,
    preset,
    language,
    COUNT(*) as query_count,
    AVG(processing_time_ms) as avg_processing_time,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY processing_time_ms) as p95_processing_time,
    AVG(domain_diversity) as avg_domain_diversity,
    AVG(relevance_avg) as avg_relevance,
    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as cache_hit_rate
FROM llamaindex_queries
GROUP BY DATE(created_at), preset, language
ORDER BY date DESC, preset, language;

-- Node distribution by namespace and language
CREATE OR REPLACE VIEW llamaindex_node_distribution AS
SELECT
    language,
    namespace,
    COUNT(*) as node_count,
    COUNT(DISTINCT article_id) as unique_articles,
    AVG(LENGTH(text)) as avg_text_length,
    COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END) as embedded_count,
    COUNT(CASE WHEN fts_vector IS NOT NULL THEN 1 END) as fts_indexed_count
FROM llamaindex_nodes
GROUP BY language, namespace
ORDER BY language, namespace;

-- Performance monitoring summary
CREATE OR REPLACE VIEW llamaindex_performance_summary AS
SELECT
    operation,
    component,
    DATE(completed_at) as date,
    COUNT(*) as operation_count,
    AVG(duration_ms) as avg_duration_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration_ms,
    SUM(CASE WHEN success THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as success_rate,
    COUNT(CASE WHEN NOT success THEN 1 END) as error_count
FROM llamaindex_performance
GROUP BY operation, component, DATE(completed_at)
ORDER BY date DESC, operation, component;

-- Comments for documentation
COMMENT ON TABLE llamaindex_nodes IS 'LlamaIndex processed nodes with dual vector/FTS storage';
COMMENT ON TABLE llamaindex_queries IS 'Query performance and analytics tracking';
COMMENT ON TABLE llamaindex_costs IS 'Cost tracking and budget management';
COMMENT ON TABLE llamaindex_performance IS 'System performance monitoring';
COMMENT ON TABLE llamaindex_migrations IS 'Migration progress and status tracking';
COMMENT ON TABLE llamaindex_config IS 'System configuration and feature flags';

COMMENT ON COLUMN llamaindex_nodes.node_id IS 'Unified identifier: {article_id}#{chunk_index}';
COMMENT ON COLUMN llamaindex_nodes.namespace IS 'Pinecone namespace: hot (recent) or archive (older)';
COMMENT ON COLUMN llamaindex_nodes.embedding IS 'Gemini text-embedding-004 vector (768 dimensions)';
COMMENT ON COLUMN llamaindex_nodes.fts_vector IS 'PostgreSQL full-text search vector';

-- Maintenance functions
CREATE OR REPLACE FUNCTION update_llamaindex_node_fts()
RETURNS TRIGGER AS $$
BEGIN
    -- Automatically update FTS vector when text changes
    NEW.fts_vector := to_tsvector('english', COALESCE(NEW.text, ''));
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for automatic FTS updates
DROP TRIGGER IF EXISTS trigger_update_llamaindex_node_fts ON llamaindex_nodes;
CREATE TRIGGER trigger_update_llamaindex_node_fts
    BEFORE INSERT OR UPDATE OF text ON llamaindex_nodes
    FOR EACH ROW EXECUTE FUNCTION update_llamaindex_node_fts();

-- Function to clean up old data
CREATE OR REPLACE FUNCTION cleanup_old_llamaindex_data(days_to_keep INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Clean up old queries (keep analytics for specified days)
    DELETE FROM llamaindex_queries
    WHERE created_at < NOW() - INTERVAL '1 day' * days_to_keep;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Clean up old performance data
    DELETE FROM llamaindex_performance
    WHERE completed_at < NOW() - INTERVAL '1 day' * days_to_keep;

    -- Clean up completed migrations older than 30 days
    DELETE FROM llamaindex_migrations
    WHERE status = 'completed' AND completed_at < NOW() - INTERVAL '30 days';

    -- Clean up old hourly cost data (keep daily aggregates)
    DELETE FROM llamaindex_costs
    WHERE hour IS NOT NULL AND created_at < NOW() - INTERVAL '7 days';

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create a cleanup job (run manually or schedule with cron)
-- SELECT cleanup_old_llamaindex_data(90);

COMMIT;