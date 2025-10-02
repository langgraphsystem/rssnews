-- Migration 004 Step 1: Enable pgvector and add column (lightweight)
-- Run this first - no data migration, just schema changes

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Add vector column to article_chunks (NULL initially)
ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(768);

-- Step 3: Create function for efficient vector search
CREATE OR REPLACE FUNCTION search_chunks_by_vector(
    query_vector vector(768),
    result_limit INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id BIGINT,
    article_id BIGINT,
    chunk_index INTEGER,
    text TEXT,
    url TEXT,
    title_norm TEXT,
    source_domain TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ac.id,
        ac.article_id,
        ac.chunk_index,
        ac.text,
        ac.url,
        ac.title_norm,
        ac.source_domain,
        1 - (ac.embedding_vector <=> query_vector) AS similarity
    FROM article_chunks ac
    WHERE ac.embedding_vector IS NOT NULL
      AND (1 - (ac.embedding_vector <=> query_vector)) >= similarity_threshold
    ORDER BY ac.embedding_vector <=> query_vector
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- Step 4: Add helpful comments
COMMENT ON COLUMN article_chunks.embedding_vector IS 'pgvector 768-dim embedding for fast similarity search';
COMMENT ON FUNCTION search_chunks_by_vector IS 'Fast vector similarity search using pgvector';
