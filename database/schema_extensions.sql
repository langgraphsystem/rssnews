-- Production Schema Extensions for RSS News System
-- Adds canonicalization, search logs, quality metrics, and monitoring

-- ==============================================================================
-- 1. ARTICLES_INDEX Extensions
-- ==============================================================================

-- Add production columns to articles_index
ALTER TABLE articles_index
ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
ADD COLUMN IF NOT EXISTS is_canonical BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS canonical_article_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS alternatives_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS source_score DECIMAL(3,2) DEFAULT 0.5,
ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en',
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS domain VARCHAR(255),
ADD COLUMN IF NOT EXISTS content_length INTEGER,
ADD COLUMN IF NOT EXISTS processing_flags JSONB DEFAULT '{}';

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles_index(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_canonical ON articles_index(canonical_article_id);
CREATE INDEX IF NOT EXISTS idx_articles_language ON articles_index(language);
CREATE INDEX IF NOT EXISTS idx_articles_domain ON articles_index(domain);
CREATE INDEX IF NOT EXISTS idx_articles_source_score ON articles_index(source_score);
CREATE INDEX IF NOT EXISTS idx_articles_is_canonical ON articles_index(is_canonical);

-- ==============================================================================
-- 2. ARTICLE_CHUNKS Extensions
-- ==============================================================================

-- Add production columns to article_chunks
ALTER TABLE article_chunks
ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en',
ADD COLUMN IF NOT EXISTS chunk_hash VARCHAR(64),
ADD COLUMN IF NOT EXISTS offset_start INTEGER,
ADD COLUMN IF NOT EXISTS offset_end INTEGER,
ADD COLUMN IF NOT EXISTS content_length INTEGER,
ADD COLUMN IF NOT EXISTS processing_flags JSONB DEFAULT '{}';

-- Create indexes for chunk operations
CREATE INDEX IF NOT EXISTS idx_chunks_language ON article_chunks(language);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON article_chunks(chunk_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_offsets ON article_chunks(offset_start, offset_end);

-- ==============================================================================
-- 3. SEARCH_LOGS Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS search_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    query TEXT NOT NULL,
    query_normalized TEXT,
    search_method VARCHAR(50) DEFAULT 'hybrid', -- 'fts', 'semantic', 'hybrid'
    filters JSONB DEFAULT '{}',
    results_count INTEGER DEFAULT 0,
    response_time_ms INTEGER,
    top_result_ids TEXT[], -- Array of result IDs
    clicked_result_ids TEXT[], -- Tracking user clicks
    timestamp TIMESTAMP DEFAULT NOW(),
    session_id VARCHAR(100),
    user_agent TEXT,
    ip_address INET
);

-- Indexes for search analytics
CREATE INDEX IF NOT EXISTS idx_search_logs_user ON search_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs USING gin(to_tsvector('english', query));
CREATE INDEX IF NOT EXISTS idx_search_logs_timestamp ON search_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_search_logs_method ON search_logs(search_method);

-- ==============================================================================
-- 4. DOMAIN_PROFILES Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS domain_profiles (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) UNIQUE NOT NULL,
    source_score DECIMAL(3,2) DEFAULT 0.5,
    authority_level VARCHAR(20) DEFAULT 'standard', -- 'high', 'medium', 'standard', 'low'

    -- User engagement metrics
    total_clicks INTEGER DEFAULT 0,
    total_impressions INTEGER DEFAULT 0,
    ctr_percentage DECIMAL(5,2) DEFAULT 0.0,

    -- Quality indicators
    avg_dwell_time_seconds INTEGER DEFAULT 0,
    bounce_rate DECIMAL(5,2) DEFAULT 0.0,
    complaint_count INTEGER DEFAULT 0,

    -- Content characteristics
    avg_content_length INTEGER DEFAULT 0,
    language_primary VARCHAR(10) DEFAULT 'en',
    categories TEXT[],

    -- Dynamic scoring
    score_last_updated TIMESTAMP DEFAULT NOW(),
    score_update_reason TEXT,
    manual_override BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Domain profiles indexes
CREATE INDEX IF NOT EXISTS idx_domain_profiles_domain ON domain_profiles(domain);
CREATE INDEX IF NOT EXISTS idx_domain_profiles_score ON domain_profiles(source_score);
CREATE INDEX IF NOT EXISTS idx_domain_profiles_authority ON domain_profiles(authority_level);

-- ==============================================================================
-- 5. ALERTS_SUBSCRIPTIONS Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS alerts_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'keyword', 'entity', 'domain', 'topic'
    alert_key TEXT NOT NULL, -- The term/entity/domain to watch

    -- Trigger configuration
    threshold_score DECIMAL(3,2) DEFAULT 0.7,
    min_results INTEGER DEFAULT 1,
    time_window_hours INTEGER DEFAULT 24,

    -- Filtering
    excluded_domains TEXT[],
    required_domains TEXT[],
    language_filter VARCHAR(10) DEFAULT 'en',
    freshness_requirement_hours INTEGER,

    -- Delivery settings
    delivery_method VARCHAR(20) DEFAULT 'telegram', -- 'telegram', 'email', 'webhook'
    delivery_address TEXT, -- Chat ID, email, webhook URL
    frequency VARCHAR(20) DEFAULT 'immediate', -- 'immediate', 'daily', 'weekly'

    -- State
    is_active BOOLEAN DEFAULT TRUE,
    last_triggered TIMESTAMP,
    total_triggers INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Alerts indexes
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_type_key ON alerts_subscriptions(alert_type, alert_key);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts_subscriptions(is_active);

-- ==============================================================================
-- 6. CLUSTERS_TOPICS Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS clusters_topics (
    id SERIAL PRIMARY KEY,
    topic_id VARCHAR(100) UNIQUE NOT NULL,

    -- Topic metadata
    topic_label TEXT NOT NULL,
    topic_description TEXT,
    confidence_score DECIMAL(3,2) DEFAULT 0.0,

    -- Content analysis
    top_keywords TEXT[],
    entities JSONB DEFAULT '{}', -- {person: [], organization: [], location: []}
    key_phrases TEXT[],

    -- Articles in cluster
    article_ids TEXT[],
    canonical_articles TEXT[], -- Top representative articles
    total_articles INTEGER DEFAULT 0,

    -- Temporal data
    time_window_start TIMESTAMP NOT NULL,
    time_window_end TIMESTAMP NOT NULL,
    peak_activity TIMESTAMP,

    -- Engagement metrics
    total_views INTEGER DEFAULT 0,
    total_shares INTEGER DEFAULT 0,
    avg_engagement_score DECIMAL(3,2) DEFAULT 0.0,

    -- Classification
    category VARCHAR(100),
    urgency_level VARCHAR(20) DEFAULT 'normal', -- 'urgent', 'high', 'normal', 'low'
    trend_status VARCHAR(20) DEFAULT 'emerging', -- 'emerging', 'growing', 'peak', 'declining'

    -- Processing metadata
    cluster_algorithm VARCHAR(50),
    processing_version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Clusters indexes
CREATE INDEX IF NOT EXISTS idx_clusters_topic_id ON clusters_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_clusters_time_window ON clusters_topics(time_window_start, time_window_end);
CREATE INDEX IF NOT EXISTS idx_clusters_category ON clusters_topics(category);
CREATE INDEX IF NOT EXISTS idx_clusters_trend_status ON clusters_topics(trend_status);
CREATE INDEX IF NOT EXISTS idx_clusters_urgency ON clusters_topics(urgency_level);

-- ==============================================================================
-- 7. QUALITY_METRICS Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS quality_metrics (
    id SERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    metric_type VARCHAR(50) NOT NULL, -- 'search_quality', 'freshness', 'diversity', 'latency'

    -- Search quality metrics
    ndcg_at_10 DECIMAL(5,4),
    recall_at_20 DECIMAL(5,4),
    precision_at_10 DECIMAL(5,4),
    fresh_at_10 DECIMAL(5,4),
    duplicates_at_10 DECIMAL(5,4),

    -- Performance metrics
    avg_response_time_ms INTEGER,
    p95_response_time_ms INTEGER,
    p99_response_time_ms INTEGER,

    -- Content metrics
    avg_results_per_query DECIMAL(5,2),
    zero_results_rate DECIMAL(5,4),

    -- User engagement
    avg_click_through_rate DECIMAL(5,4),
    avg_dwell_time_seconds INTEGER,
    bounce_rate DECIMAL(5,4),

    -- System health
    error_rate DECIMAL(5,4),
    cache_hit_rate DECIMAL(5,4),

    -- Metadata
    total_queries INTEGER,
    total_unique_users INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Quality metrics indexes
CREATE INDEX IF NOT EXISTS idx_quality_date_type ON quality_metrics(metric_date, metric_type);
CREATE INDEX IF NOT EXISTS idx_quality_date ON quality_metrics(metric_date);

-- ==============================================================================
-- 8. USER_INTERACTIONS Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS user_interactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    interaction_type VARCHAR(50) NOT NULL, -- 'click', 'share', 'save', 'mute', 'report'

    -- Target of interaction
    target_type VARCHAR(50) NOT NULL, -- 'article', 'domain', 'search_result'
    target_id TEXT NOT NULL,

    -- Context
    source_query TEXT, -- Query that led to this interaction
    result_position INTEGER, -- Position in search results
    search_session_id VARCHAR(100),

    -- Interaction details
    interaction_value TEXT, -- Additional data (e.g., share platform)
    dwell_time_seconds INTEGER,

    -- Metadata
    timestamp TIMESTAMP DEFAULT NOW(),
    user_agent TEXT,
    ip_address INET
);

-- User interactions indexes
CREATE INDEX IF NOT EXISTS idx_interactions_user ON user_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type ON user_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_interactions_target ON user_interactions(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON user_interactions(timestamp);

-- ==============================================================================
-- 9. SYSTEM_CONFIG Table (New)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    config_type VARCHAR(20) DEFAULT 'string', -- 'string', 'number', 'boolean', 'json'
    description TEXT,
    category VARCHAR(50), -- 'scoring', 'search', 'alerts', 'performance'
    is_feature_flag BOOLEAN DEFAULT FALSE,
    requires_restart BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- System config indexes
CREATE INDEX IF NOT EXISTS idx_config_key ON system_config(config_key);
CREATE INDEX IF NOT EXISTS idx_config_category ON system_config(category);
CREATE INDEX IF NOT EXISTS idx_config_feature_flag ON system_config(is_feature_flag);

-- ==============================================================================
-- 10. Default System Configuration Values
-- ==============================================================================

-- Insert default scoring weights
INSERT INTO system_config (config_key, config_value, config_type, description, category) VALUES
('scoring.semantic_weight', '0.58', 'number', 'Weight for semantic similarity in scoring', 'scoring'),
('scoring.fts_weight', '0.32', 'number', 'Weight for FTS relevance in scoring', 'scoring'),
('scoring.freshness_weight', '0.06', 'number', 'Weight for content freshness in scoring', 'scoring'),
('scoring.source_weight', '0.04', 'number', 'Weight for source authority in scoring', 'scoring'),
('scoring.tau_hours', '72', 'number', 'Time decay parameter in hours', 'scoring'),
('scoring.max_per_domain', '3', 'number', 'Maximum results per domain', 'scoring'),
('scoring.max_per_article', '2', 'number', 'Maximum chunks per article', 'scoring'),

-- Search configuration
('search.default_limit', '10', 'number', 'Default number of search results', 'search'),
('search.max_limit', '50', 'number', 'Maximum allowed search results', 'search'),
('search.cache_ttl_seconds', '900', 'number', 'Search cache TTL (15 minutes)', 'search'),
('search.enable_mmr', 'true', 'boolean', 'Enable MMR diversification', 'search'),
('search.mmr_lambda', '0.7', 'number', 'MMR lambda parameter', 'search'),

-- Performance settings
('performance.max_response_time_ms', '500', 'number', 'Maximum allowed response time', 'performance'),
('performance.enable_caching', 'true', 'boolean', 'Enable result caching', 'performance'),
('performance.batch_size_embedding', '1500', 'number', 'Embedding processing batch size', 'performance'),
('performance.batch_size_fts', '100000', 'number', 'FTS processing batch size', 'performance')

ON CONFLICT (config_key) DO NOTHING;

-- ==============================================================================
-- 11. Initial Domain Profiles
-- ==============================================================================

-- Insert authoritative domain profiles
INSERT INTO domain_profiles (domain, source_score, authority_level, notes) VALUES
('reuters.com', 0.85, 'high', 'International news agency'),
('ap.org', 0.85, 'high', 'Associated Press'),
('bbc.com', 0.80, 'high', 'British Broadcasting Corporation'),
('nytimes.com', 0.78, 'high', 'The New York Times'),
('theguardian.com', 0.75, 'high', 'The Guardian'),
('washingtonpost.com', 0.75, 'high', 'The Washington Post'),
('wsj.com', 0.78, 'high', 'The Wall Street Journal'),
('economist.com', 0.80, 'high', 'The Economist'),
('bloomberg.com', 0.75, 'high', 'Bloomberg News'),
('npr.org', 0.75, 'high', 'National Public Radio'),
('cnn.com', 0.70, 'medium', 'Cable News Network'),
('abcnews.go.com', 0.70, 'medium', 'ABC News'),
('cbsnews.com', 0.70, 'medium', 'CBS News'),
('nbcnews.com', 0.70, 'medium', 'NBC News')
ON CONFLICT (domain) DO NOTHING;

-- ==============================================================================
-- 12. Helper Functions
-- ==============================================================================

-- Function to update domain scores based on engagement
CREATE OR REPLACE FUNCTION update_domain_score(domain_name VARCHAR(255))
RETURNS VOID AS $$
BEGIN
    UPDATE domain_profiles
    SET
        ctr_percentage = CASE
            WHEN total_impressions > 0 THEN (total_clicks::DECIMAL / total_impressions) * 100
            ELSE 0
        END,
        score_last_updated = NOW()
    WHERE domain = domain_name;
END;
$$ LANGUAGE plpgsql;

-- Function to get current scoring weights
CREATE OR REPLACE FUNCTION get_scoring_weights()
RETURNS TABLE(
    semantic_weight DECIMAL,
    fts_weight DECIMAL,
    freshness_weight DECIMAL,
    source_weight DECIMAL,
    tau_hours INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT config_value::DECIMAL FROM system_config WHERE config_key = 'scoring.semantic_weight'),
        (SELECT config_value::DECIMAL FROM system_config WHERE config_key = 'scoring.fts_weight'),
        (SELECT config_value::DECIMAL FROM system_config WHERE config_key = 'scoring.freshness_weight'),
        (SELECT config_value::DECIMAL FROM system_config WHERE config_key = 'scoring.source_weight'),
        (SELECT config_value::INTEGER FROM system_config WHERE config_key = 'scoring.tau_hours');
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- 13. Data Retention Policies
-- ==============================================================================

-- Function to clean old search logs (keep 60 days)
CREATE OR REPLACE FUNCTION cleanup_old_search_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM search_logs
    WHERE timestamp < NOW() - INTERVAL '60 days';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to clean old user interactions (keep 90 days)
CREATE OR REPLACE FUNCTION cleanup_old_interactions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_interactions
    WHERE timestamp < NOW() - INTERVAL '90 days';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to archive old quality metrics (keep 1 year)
CREATE OR REPLACE FUNCTION cleanup_old_quality_metrics()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM quality_metrics
    WHERE metric_date < CURRENT_DATE - INTERVAL '1 year';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;