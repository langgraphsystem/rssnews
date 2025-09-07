-- Migration to Production RSS Processing Schema
-- Migrates existing system to full production architecture

BEGIN;

-- =====================================================
-- 1. Enhanced Articles Index Table
-- =====================================================

-- Add missing columns to articles_index
ALTER TABLE articles_index 
  ADD COLUMN IF NOT EXISTS article_id TEXT,
  ADD COLUMN IF NOT EXISTS row_id_raw BIGINT,
  ADD COLUMN IF NOT EXISTS url TEXT,
  ADD COLUMN IF NOT EXISTS canonical_url TEXT,
  ADD COLUMN IF NOT EXISTS source_domain TEXT,
  ADD COLUMN IF NOT EXISTS title_norm TEXT,
  ADD COLUMN IF NOT EXISTS clean_text TEXT,
  ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS published_is_estimated BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS language TEXT,
  ADD COLUMN IF NOT EXISTS category TEXT,
  ADD COLUMN IF NOT EXISTS tags_norm JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS word_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS quality_flags JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS quality_score FLOAT DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dup_reason TEXT,
  ADD COLUMN IF NOT EXISTS dup_original_id TEXT,
  ADD COLUMN IF NOT EXISTS ready_for_chunking BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS chunking_completed BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS processing_version INTEGER DEFAULT 1;

-- Update article_id to be url_hash if not set
UPDATE articles_index 
SET article_id = url_hash 
WHERE article_id IS NULL AND url_hash IS NOT NULL;

-- Make article_id unique
CREATE UNIQUE INDEX IF NOT EXISTS articles_index_article_id_key 
ON articles_index(article_id) 
WHERE article_id IS NOT NULL;

-- Add performance indexes
CREATE INDEX IF NOT EXISTS idx_articles_source_published 
ON articles_index(source_domain, published_at DESC) 
WHERE source_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_articles_language_category 
ON articles_index(language, category)
WHERE language IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_articles_quality_score 
ON articles_index(quality_score DESC) 
WHERE quality_score > 0;

CREATE INDEX IF NOT EXISTS idx_articles_ready_chunking 
ON articles_index(ready_for_chunking) 
WHERE ready_for_chunking = TRUE;

-- =====================================================
-- 2. Article Chunks Table (NEW)
-- =====================================================

CREATE TABLE IF NOT EXISTS article_chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT UNIQUE NOT NULL,
    article_id TEXT NOT NULL,
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks indexes
CREATE UNIQUE INDEX IF NOT EXISTS article_chunks_article_chunk_idx 
ON article_chunks(article_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_chunks_article_id 
ON article_chunks(article_id);

CREATE INDEX IF NOT EXISTS idx_chunks_source_published 
ON article_chunks(source_domain, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_chunks_language_category 
ON article_chunks(language, category);

-- =====================================================
-- 3. Enhanced Batch Diagnostics Table
-- =====================================================

DROP TABLE IF EXISTS batch_diagnostics;
CREATE TABLE batch_diagnostics (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL DEFAULT gen_random_uuid(),
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
    correlation_id UUID
);

-- Batch diagnostics indexes
CREATE INDEX IF NOT EXISTS idx_batch_diag_batch_stage 
ON batch_diagnostics(batch_id, stage);

CREATE INDEX IF NOT EXISTS idx_batch_diag_status_started 
ON batch_diagnostics(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_batch_diag_worker_started 
ON batch_diagnostics(worker_id, started_at DESC) 
WHERE worker_id IS NOT NULL;

-- =====================================================
-- 4. Performance Metrics Table (NEW)
-- =====================================================

CREATE TABLE IF NOT EXISTS performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL,
    metric_value FLOAT NOT NULL,
    tags JSONB DEFAULT '{}',
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance metrics indexes
CREATE INDEX IF NOT EXISTS idx_perf_metrics_name_time 
ON performance_metrics(metric_name, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_perf_metrics_recorded_at 
ON performance_metrics(recorded_at DESC);

-- =====================================================
-- 5. Enhanced Raw Table Updates
-- =====================================================

-- Add missing columns to raw table
ALTER TABLE raw 
  ADD COLUMN IF NOT EXISTS row_id_raw BIGINT DEFAULT nextval('raw_id_seq'),
  ADD COLUMN IF NOT EXISTS canonical_url TEXT,
  ADD COLUMN IF NOT EXISTS published_at_raw TEXT,
  ADD COLUMN IF NOT EXISTS html TEXT,
  ADD COLUMN IF NOT EXISTS images JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS videos JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS enclosures JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS outlinks JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS paywalled BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS partial BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS reading_time INTEGER DEFAULT 0;

-- Ensure proper JSON serialization for existing data
UPDATE raw SET keywords = '[]'::jsonb WHERE keywords IS NULL OR keywords::text = '';
UPDATE raw SET authors = '[]'::jsonb WHERE authors IS NULL OR authors::text = '';
UPDATE raw SET images = '[]'::jsonb WHERE images IS NULL;
UPDATE raw SET videos = '[]'::jsonb WHERE videos IS NULL;
UPDATE raw SET enclosures = '[]'::jsonb WHERE enclosures IS NULL;
UPDATE raw SET outlinks = '[]'::jsonb WHERE outlinks IS NULL;

-- Add performance indexes to raw table
CREATE INDEX IF NOT EXISTS idx_raw_status_fetched 
ON raw(status, fetched_at) 
WHERE status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_raw_source_status 
ON raw(source, status) 
WHERE source IS NOT NULL AND status IS NOT NULL;

-- =====================================================
-- 6. Enhanced Feeds Table
-- =====================================================

ALTER TABLE feeds 
  ADD COLUMN IF NOT EXISTS feed_url_canon TEXT,
  ADD COLUMN IF NOT EXISTS language_guess TEXT,
  ADD COLUMN IF NOT EXISTS health_score FLOAT DEFAULT 1.0,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS last_scanned_at TIMESTAMPTZ;

-- Update language_guess from existing lang field
UPDATE feeds SET language_guess = lang WHERE language_guess IS NULL AND lang IS NOT NULL;

-- =====================================================
-- 7. Configuration Table Enhancement
-- =====================================================

-- Ensure config table has proper structure
ALTER TABLE config 
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Insert default configuration values
INSERT INTO config (key, value, description) VALUES 
  ('batch_size_default', '200', 'Default batch size for processing'),
  ('batch_size_min', '100', 'Minimum allowed batch size'),
  ('batch_size_max', '300', 'Maximum allowed batch size'),
  ('min_word_count', '50', 'Minimum word count for articles'),
  ('quality_threshold', '0.5', 'Minimum quality score'),
  ('max_retries', '3', 'Maximum retry attempts'),
  ('chunk_size_words', '500', 'Target words per chunk'),
  ('chunk_overlap_words', '50', 'Overlap between chunks'),
  ('supported_languages', '["en", "ru", "es", "fr", "de"]', 'Supported language codes'),
  ('processing_version', '1', 'Current processing version')
ON CONFLICT (key) DO NOTHING;

-- =====================================================
-- 8. Create Partitions for Raw Table
-- =====================================================

-- Enable partitioning on raw table if not already done
-- Note: This requires recreating the table for existing data
-- For production, this should be done during maintenance window

-- =====================================================
-- 9. Full Text Search Setup
-- =====================================================

-- Add FTS columns to articles_index if not exists
ALTER TABLE articles_index 
  ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Create FTS index
CREATE INDEX IF NOT EXISTS idx_articles_search_vector 
ON articles_index USING GIN(search_vector);

-- Create trigger to automatically update search_vector
CREATE OR REPLACE FUNCTION update_articles_search_vector() 
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector := 
    setweight(to_tsvector('english', COALESCE(NEW.title_norm, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(NEW.clean_text, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_articles_search_vector ON articles_index;
CREATE TRIGGER trigger_update_articles_search_vector
  BEFORE INSERT OR UPDATE ON articles_index
  FOR EACH ROW EXECUTE FUNCTION update_articles_search_vector();

-- =====================================================
-- 10. Cleanup and Validation
-- =====================================================

-- Update statistics
ANALYZE articles_index;
ANALYZE article_chunks;
ANALYZE batch_diagnostics;
ANALYZE performance_metrics;
ANALYZE raw;
ANALYZE feeds;
ANALYZE config;

-- Validate migration
DO $$
DECLARE
    table_exists BOOLEAN;
BEGIN
    -- Check if all required tables exist
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = 'article_chunks'
    ) INTO table_exists;
    
    IF NOT table_exists THEN
        RAISE EXCEPTION 'Migration failed: article_chunks table not created';
    END IF;
    
    RAISE NOTICE 'Migration completed successfully!';
END $$;

COMMIT;

-- =====================================================
-- Post-Migration Notes
-- =====================================================

/*
After running this migration:

1. Update your application code to use the new schema
2. Run data validation scripts
3. Setup monitoring for new tables
4. Configure backup policies for new tables
5. Test the new pipeline components

Key changes:
- Enhanced articles_index with production fields
- New article_chunks table for RAG preparation  
- Enhanced batch_diagnostics for detailed monitoring
- New performance_metrics table
- Full-text search capabilities
- Proper JSON field handling
- Performance indexes

Next steps:
1. Implement Pipeline Controller
2. Create Stage Processors  
3. Setup Chunking Engine
4. Configure monitoring
*/