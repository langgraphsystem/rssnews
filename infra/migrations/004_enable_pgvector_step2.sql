-- Migration 004 Step 2: Create index AFTER data migration
-- Run this AFTER migrating embeddings with Python script

-- Create HNSW index for fast similarity search
-- This runs fast because it only indexes non-NULL vectors
CREATE INDEX IF NOT EXISTS article_chunks_embedding_vector_idx
ON article_chunks USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

COMMENT ON INDEX article_chunks_embedding_vector_idx IS 'HNSW index for cosine similarity search';
