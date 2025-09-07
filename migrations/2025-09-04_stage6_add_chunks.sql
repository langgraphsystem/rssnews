-- Stage 6 schema extension: articles_index fields + article_chunks table

-- 1) Extend articles_index for Stage 6 inputs/state
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS article_id TEXT;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS clean_text TEXT;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS title_norm TEXT;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS tags_norm JSONB DEFAULT '[]';
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS quality_score FLOAT DEFAULT 0.0;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS ready_for_chunking BOOLEAN DEFAULT FALSE;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS chunking_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS processing_version INTEGER DEFAULT 1;

-- Backfill article_id from url_hash_v2 if exists, else url_hash
UPDATE articles_index SET article_id = COALESCE(url_hash_v2, url_hash) WHERE article_id IS NULL;

-- Index for article_id and scheduling
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ux_articles_index_article_id'
    ) THEN
        CREATE UNIQUE INDEX ux_articles_index_article_id ON articles_index(article_id);
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ix_articles_index_ready_for_chunking'
    ) THEN
        CREATE INDEX ix_articles_index_ready_for_chunking ON articles_index(ready_for_chunking) WHERE ready_for_chunking = TRUE;
    END IF;
END$$;

-- 2) Create article_chunks table
CREATE TABLE IF NOT EXISTS article_chunks (
    id BIGSERIAL PRIMARY KEY,
    article_id TEXT NOT NULL,
    processing_version INTEGER NOT NULL DEFAULT 1,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    word_count_chunk INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    semantic_type TEXT,
    boundary_confidence FLOAT DEFAULT 0.0,
    llm_action TEXT DEFAULT 'noop',
    llm_confidence FLOAT DEFAULT 0.0,
    llm_reason TEXT,
    -- Denormalized metadata
    url TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    language TEXT NOT NULL,
    category TEXT,
    tags_norm JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Uniqueness and helpful indexes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ux_article_chunks_article_idx_ver'
    ) THEN
        CREATE UNIQUE INDEX ux_article_chunks_article_idx_ver ON article_chunks(article_id, processing_version, chunk_index);
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ix_article_chunks_article_id'
    ) THEN
        CREATE INDEX ix_article_chunks_article_id ON article_chunks(article_id);
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ix_article_chunks_src_pub'
    ) THEN
        CREATE INDEX ix_article_chunks_src_pub ON article_chunks(source_domain, published_at DESC);
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ix_article_chunks_lang_cat'
    ) THEN
        CREATE INDEX ix_article_chunks_lang_cat ON article_chunks(language, category);
    END IF;
END$$;

