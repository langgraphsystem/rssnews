-- Migration 004: Enable pgvector extension and migrate embeddings
-- Purpose: Replace JSON-based embeddings with native pgvector for performance

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Add vector column to article_chunks
ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(768);

-- Step 3: Create index for fast similarity search (HNSW for large datasets)
CREATE INDEX IF NOT EXISTS article_chunks_embedding_vector_idx
ON article_chunks USING hnsw (embedding_vector vector_cosine_ops);

-- Step 4: Migrate existing JSON embeddings to vector column
-- This runs only if embedding is populated but embedding_vector is NULL
UPDATE article_chunks
SET embedding_vector = (
    -- Parse JSON array and convert to vector
    SELECT vector_in(
        CAST(
            '[' || string_agg(value::text, ',') || ']'
            AS cstring
        )
    )
    FROM jsonb_array_elements_text(
        CASE
            WHEN jsonb_typeof(embedding::jsonb) = 'array' THEN embedding::jsonb
            ELSE NULL
        END
    )
)
WHERE embedding IS NOT NULL
  AND embedding_vector IS NULL
  AND embedding != 'null'
  AND jsonb_typeof(embedding::jsonb) = 'array';

-- Step 5: Create function for efficient vector search
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

-- Step 6: Add helpful comments
COMMENT ON COLUMN article_chunks.embedding_vector IS 'pgvector 768-dim embedding for fast similarity search';
COMMENT ON INDEX article_chunks_embedding_vector_idx IS 'HNSW index for cosine similarity search';
COMMENT ON FUNCTION search_chunks_by_vector IS 'Fast vector similarity search using pgvector';
