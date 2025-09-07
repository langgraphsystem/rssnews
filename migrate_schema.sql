-- Database schema migration for enhanced RSS news aggregation system
-- This script migrates the existing schema to support the new enhanced features

BEGIN;

-- ================================
-- FEEDS TABLE MIGRATION
-- ================================

-- Add missing columns to feeds table
ALTER TABLE feeds 
  ADD COLUMN IF NOT EXISTS category TEXT DEFAULT '';

-- Ensure feed_url_canon is nullable (some feeds may not have canonical URLs initially)
ALTER TABLE feeds ALTER COLUMN feed_url_canon DROP NOT NULL;

-- ================================
-- RAW TABLE MIGRATION  
-- ================================

-- Rename article_url to url for consistency with new schema
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'article_url') THEN
        ALTER TABLE raw RENAME COLUMN article_url TO url;
    END IF;
END $$;

-- Rename article_url_canon to canonical_url for consistency
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'article_url_canon') THEN
        ALTER TABLE raw RENAME COLUMN article_url_canon TO canonical_url;
    END IF;
END $$;

-- Rename subtitle to description for consistency
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'subtitle') THEN
        ALTER TABLE raw RENAME COLUMN subtitle TO description;
    END IF;
END $$;

-- Rename tags to keywords for consistency  
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'tags') THEN
        -- First convert text to text[] if it's not already
        ALTER TABLE raw ALTER COLUMN tags TYPE text[] USING string_to_array(tags, ', ');
        ALTER TABLE raw RENAME COLUMN tags TO keywords;
    END IF;
END $$;

-- Convert authors from text to text[] if needed
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'authors' AND data_type = 'text') THEN
        ALTER TABLE raw ALTER COLUMN authors TYPE text[] USING string_to_array(authors, ', ');
    END IF;
END $$;

-- Add new columns for enhanced functionality
ALTER TABLE raw
  ADD COLUMN IF NOT EXISTS publisher      TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS top_image      TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS images         JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS videos         JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS enclosures     JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS outlinks       TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS updated_at     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS fetched_at     TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS paywalled      BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS partial        BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS full_text      TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS reading_time   INTEGER DEFAULT 0;

-- Convert date fields to proper TIMESTAMPTZ if they're text
DO $$ 
BEGIN
    -- Convert published_at from text to timestamptz
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'published_at' AND data_type = 'text') THEN
        -- Add temp column
        ALTER TABLE raw ADD COLUMN published_at_temp TIMESTAMPTZ;
        -- Convert non-empty values
        UPDATE raw SET published_at_temp = published_at::timestamptz 
        WHERE published_at IS NOT NULL AND published_at != '';
        -- Drop old column and rename
        ALTER TABLE raw DROP COLUMN published_at;
        ALTER TABLE raw RENAME COLUMN published_at_temp TO published_at;
    END IF;
END $$;

-- Rename error_msg to error_reason for consistency
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'raw' AND column_name = 'error_msg') THEN
        ALTER TABLE raw RENAME COLUMN error_msg TO error_reason;
    END IF;
END $$;

-- ================================
-- ARTICLES_INDEX TABLE MIGRATION
-- ================================

-- Add missing columns to articles_index table for deduplication
ALTER TABLE articles_index
  ADD COLUMN IF NOT EXISTS title  TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS author TEXT DEFAULT '';

-- ================================
-- CREATE NEW INDEXES FOR PERFORMANCE
-- ================================

-- Indexes for raw table
CREATE INDEX IF NOT EXISTS idx_raw_status ON raw(status);
CREATE INDEX IF NOT EXISTS idx_raw_url_hash ON raw(url_hash);
CREATE INDEX IF NOT EXISTS idx_raw_text_hash ON raw(text_hash);
CREATE INDEX IF NOT EXISTS idx_raw_published_at ON raw(published_at);
CREATE INDEX IF NOT EXISTS idx_raw_fetched_at ON raw(fetched_at);
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw(source);

-- Indexes for articles_index table  
CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles_index(url_hash);
CREATE INDEX IF NOT EXISTS idx_articles_text_hash ON articles_index(text_hash);

-- ================================
-- UPDATE EXISTING DATA
-- ================================

-- Update empty/null status values to 'pending' for consistency
UPDATE raw SET status = 'pending' WHERE status IS NULL OR status = '';

-- Update source field from URL if empty
UPDATE raw 
SET source = split_part(split_part(url, '://', 2), '/', 1)
WHERE (source IS NULL OR source = '') AND url IS NOT NULL AND url != '';

-- ================================
-- VERIFY MIGRATION
-- ================================

-- Check that all required columns exist
DO $$
DECLARE
    missing_cols TEXT[] := ARRAY[]::TEXT[];
    required_cols TEXT[] := ARRAY[
        'url', 'canonical_url', 'url_hash', 'source', 'section', 
        'title', 'description', 'keywords', 'authors', 'publisher',
        'top_image', 'images', 'videos', 'enclosures', 'outlinks',
        'published_at', 'updated_at', 'fetched_at', 'language',
        'paywalled', 'partial', 'full_text', 'text_hash', 
        'word_count', 'reading_time', 'status', 'error_reason'
    ];
    col TEXT;
BEGIN
    FOREACH col IN ARRAY required_cols LOOP
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'raw' AND column_name = col) THEN
            missing_cols := array_append(missing_cols, col);
        END IF;
    END LOOP;
    
    IF array_length(missing_cols, 1) > 0 THEN
        RAISE EXCEPTION 'Migration incomplete: missing columns: %', array_to_string(missing_cols, ', ');
    ELSE
        RAISE NOTICE 'Migration verification passed: all required columns present';
    END IF;
END $$;

COMMIT;

-- ================================
-- POST-MIGRATION STATISTICS
-- ================================

-- Show migration results
SELECT 
    'FEEDS' as table_name,
    COUNT(*) as total_rows,
    COUNT(*) FILTER (WHERE status = 'active') as active_feeds
FROM feeds

UNION ALL

SELECT 
    'RAW' as table_name,
    COUNT(*) as total_rows,
    COUNT(*) FILTER (WHERE status = 'stored') as stored_articles
FROM raw

UNION ALL

SELECT 
    'ARTICLES_INDEX' as table_name,
    COUNT(*) as total_rows,
    COUNT(DISTINCT text_hash) as unique_text_hashes
FROM articles_index;

-- Show column info for verification
SELECT 
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name IN ('raw', 'feeds', 'articles_index')
ORDER BY table_name, ordinal_position;