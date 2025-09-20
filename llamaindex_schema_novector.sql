-- LlamaIndex Database Schema (No Vector Extension)
-- ================================================
--
-- Simplified schema without pgvector for initial testing

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

    -- FTS (Full-Text Search) - no vector for now
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

-- JSONB metadata index
CREATE INDEX IF NOT EXISTS idx_llamaindex_nodes_metadata ON llamaindex_nodes USING gin(metadata);

-- LlamaIndex queries table (analytics)
CREATE TABLE IF NOT EXISTS llamaindex_queries (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,
    preset VARCHAR(20) NOT NULL,  -- qa/digest/shorts/ideas
    language VARCHAR(5) NOT NULL,
    max_sources INTEGER DEFAULT 10,

    -- Results
    retrieved_node_ids TEXT[],
    used_node_ids TEXT[],
    response_length INTEGER,

    -- Performance
    total_time_ms INTEGER,
    retrieval_time_ms INTEGER,
    synthesis_time_ms INTEGER,
    cache_hit BOOLEAN DEFAULT FALSE,

    -- Quality metrics
    domains_used TEXT[],
    avg_freshness_days FLOAT,
    avg_relevance FLOAT,

    -- Provider usage
    embedding_provider VARCHAR(20),  -- gemini/openai
    llm_provider VARCHAR(20),        -- openai/gemini

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_hash ON llamaindex_queries(query_hash);
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_preset ON llamaindex_queries(preset);
CREATE INDEX IF NOT EXISTS idx_llamaindex_queries_created_at ON llamaindex_queries(created_at);

-- LlamaIndex costs table (budget control)
CREATE TABLE IF NOT EXISTS llamaindex_costs (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    provider VARCHAR(20) NOT NULL,  -- openai/gemini
    operation VARCHAR(20) NOT NULL, -- embeddings/completions/chat

    -- Usage counts
    requests_count INTEGER DEFAULT 0,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,

    -- Costs
    cost_usd DECIMAL(10,4) DEFAULT 0.0000,

    -- Limits
    daily_limit DECIMAL(10,2) DEFAULT 100.00,

    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(date, provider, operation)
);

CREATE INDEX IF NOT EXISTS idx_llamaindex_costs_date ON llamaindex_costs(date);
CREATE INDEX IF NOT EXISTS idx_llamaindex_costs_provider ON llamaindex_costs(provider);

-- LlamaIndex performance table (monitoring)
CREATE TABLE IF NOT EXISTS llamaindex_performance (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(50) NOT NULL,  -- ingest/query/migrate/monitor
    component VARCHAR(50),           -- retrieval/synthesis/chunking

    -- Timing
    duration_ms INTEGER NOT NULL,

    -- Status
    status VARCHAR(20) NOT NULL,     -- success/error/timeout
    error_message TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_operation ON llamaindex_performance(operation);
CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_created_at ON llamaindex_performance(created_at);

-- LlamaIndex configuration table
CREATE TABLE IF NOT EXISTS llamaindex_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llamaindex_config_key ON llamaindex_config(key);

-- Insert default configuration
INSERT INTO llamaindex_config (key, value, description) VALUES
('features.hybrid_retrieval', 'true', 'Enable hybrid FTS + vector retrieval'),
('features.domain_diversification', 'true', 'Diversify domains in results'),
('features.freshness_boost', 'true', 'Boost recent articles in ranking'),
('features.semantic_rerank', 'true', 'Enable semantic reranking'),
('features.query_cache', 'true', 'Enable query result caching'),

('routing.alpha_default', '0.5', 'Default alpha for hybrid retrieval (0.0=vector only, 1.0=FTS only)'),
('routing.similarity_threshold', '0.6', 'Minimum similarity score for retrieval'),
('routing.freshness_boost_days', '7', 'Days for freshness boost'),
('routing.freshness_boost_factor', '0.2', 'Freshness boost multiplier'),

('limits.retrieval_top_k', '24', 'Initial retrieval count'),
('limits.final_top_k', '10', 'Final result count'),
('limits.cache_ttl_minutes', '15', 'Query cache TTL in minutes'),
('limits.daily_budget_openai', '50.00', 'Daily OpenAI budget in USD'),
('limits.daily_budget_gemini', '30.00', 'Daily Gemini budget in USD'),
('limits.max_tokens_synthesis', '4000', 'Max tokens for synthesis'),

('legacy.enabled', 'false', 'Legacy mode enabled')
ON CONFLICT (key) DO NOTHING;

-- System metadata
ALTER TABLE llamaindex_config ADD COLUMN IF NOT EXISTS system_managed BOOLEAN DEFAULT FALSE;

-- Index on metadata for complex queries
CREATE INDEX IF NOT EXISTS idx_llamaindex_performance_metadata ON llamaindex_performance USING gin(metadata);

-- Views for analytics

-- Daily cost summary
CREATE OR REPLACE VIEW llamaindex_daily_costs AS
SELECT
    date,
    SUM(cost_usd) as total_cost,
    MAX(daily_limit) as daily_limit,
    ROUND((SUM(cost_usd) / MAX(daily_limit) * 100)::numeric, 2) as budget_used_pct,
    COUNT(DISTINCT provider) as providers_used,
    SUM(requests_count) as total_requests
FROM llamaindex_costs
GROUP BY date
ORDER BY date DESC;

-- Query performance stats
CREATE OR REPLACE VIEW llamaindex_query_stats AS
SELECT
    DATE(created_at) as date,
    preset,
    language,
    COUNT(*) as query_count,
    AVG(total_time_ms) as avg_time_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_time_ms) as p95_time_ms,
    COUNT(*) FILTER (WHERE cache_hit) as cache_hits,
    ROUND(COUNT(*) FILTER (WHERE cache_hit)::float / COUNT(*) * 100, 2) as cache_hit_rate,
    AVG(response_length) as avg_response_length,
    AVG(array_length(domains_used, 1)) as avg_domains_per_query
FROM llamaindex_queries
GROUP BY DATE(created_at), preset, language
ORDER BY date DESC, preset, language;

-- Node distribution by namespace/language
CREATE OR REPLACE VIEW llamaindex_node_distribution AS
SELECT
    language,
    namespace,
    COUNT(*) as node_count,
    MIN(created_at) as oldest_node,
    MAX(created_at) as newest_node,
    AVG(relevance_score) as avg_relevance,
    AVG(freshness_score) as avg_freshness
FROM llamaindex_nodes
GROUP BY language, namespace
ORDER BY language, namespace;

-- Comments for documentation
COMMENT ON TABLE llamaindex_nodes IS 'LlamaIndex processed text chunks with metadata and embeddings';
COMMENT ON TABLE llamaindex_queries IS 'Query analytics and performance tracking';
COMMENT ON TABLE llamaindex_costs IS 'API usage costs and budget tracking';
COMMENT ON TABLE llamaindex_performance IS 'System performance monitoring';

-- Auto-update timestamps
CREATE OR REPLACE FUNCTION update_llamaindex_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Drop existing triggers to avoid conflicts
DROP TRIGGER IF EXISTS tr_llamaindex_nodes_updated_at ON llamaindex_nodes;

-- Create updated_at triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ language 'plpgsql';

COMMIT;