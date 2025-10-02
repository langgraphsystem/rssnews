-- Memory Storage Schema for Phase 3
-- Supports episodic and semantic memory with vector embeddings

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Memory records table
CREATE TABLE IF NOT EXISTS memory_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Memory type
    type VARCHAR(20) NOT NULL CHECK (type IN ('episodic', 'semantic')),

    -- Content
    content TEXT NOT NULL,

    -- Vector embedding for semantic search (1536 dimensions for OpenAI ada-002)
    embedding vector(1536),

    -- Metadata
    importance FLOAT NOT NULL DEFAULT 0.5 CHECK (importance >= 0.0 AND importance <= 1.0),
    ttl_days INTEGER NOT NULL DEFAULT 90 CHECK (ttl_days >= 0 AND ttl_days <= 365),

    -- References to source articles
    refs TEXT[] DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP,
    access_count INTEGER NOT NULL DEFAULT 0,

    -- Soft delete
    deleted_at TIMESTAMP,

    -- User context (for multi-tenant)
    user_id VARCHAR(100),

    -- Tags for categorization
    tags TEXT[] DEFAULT '{}'
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_memory_records_type ON memory_records(type);
CREATE INDEX IF NOT EXISTS idx_memory_records_created_at ON memory_records(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_records_expires_at ON memory_records(expires_at);
CREATE INDEX IF NOT EXISTS idx_memory_records_user_id ON memory_records(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_deleted_at ON memory_records(deleted_at) WHERE deleted_at IS NULL;

-- Vector similarity index (IVFFlat for fast approximate search)
CREATE INDEX IF NOT EXISTS idx_memory_records_embedding ON memory_records
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Composite index for active records
CREATE INDEX IF NOT EXISTS idx_memory_records_active ON memory_records(user_id, type, expires_at)
WHERE deleted_at IS NULL;

-- Function to auto-set expires_at based on ttl_days
CREATE OR REPLACE FUNCTION set_memory_expiration()
RETURNS TRIGGER AS $$
BEGIN
    NEW.expires_at := NEW.created_at + (NEW.ttl_days || ' days')::INTERVAL;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to set expires_at on insert
CREATE TRIGGER trigger_set_memory_expiration
BEFORE INSERT ON memory_records
FOR EACH ROW
EXECUTE FUNCTION set_memory_expiration();

-- Function to clean up expired records (run periodically via cron)
CREATE OR REPLACE FUNCTION cleanup_expired_memory()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Soft delete expired records
    UPDATE memory_records
    SET deleted_at = NOW()
    WHERE expires_at < NOW()
      AND deleted_at IS NULL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Memory access log (optional, for analytics)
CREATE TABLE IF NOT EXISTS memory_access_log (
    id BIGSERIAL PRIMARY KEY,
    memory_id UUID NOT NULL REFERENCES memory_records(id) ON DELETE CASCADE,
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    query_text TEXT,
    similarity_score FLOAT,
    user_id VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_memory_access_log_memory_id ON memory_access_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_access_log_accessed_at ON memory_access_log(accessed_at DESC);

-- View for active memories (not expired, not deleted)
CREATE OR REPLACE VIEW active_memory_records AS
SELECT
    id,
    type,
    content,
    embedding,
    importance,
    ttl_days,
    refs,
    created_at,
    expires_at,
    last_accessed_at,
    access_count,
    user_id,
    tags
FROM memory_records
WHERE deleted_at IS NULL
  AND expires_at > NOW();

-- Statistics view
CREATE OR REPLACE VIEW memory_stats AS
SELECT
    user_id,
    type,
    COUNT(*) as total_records,
    COUNT(*) FILTER (WHERE expires_at > NOW()) as active_records,
    COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted_records,
    AVG(importance) as avg_importance,
    AVG(access_count) as avg_access_count,
    MAX(created_at) as last_created_at
FROM memory_records
GROUP BY user_id, type;

-- Sample queries for testing

-- 1. Semantic search by embedding similarity
-- SELECT id, content, 1 - (embedding <=> query_embedding) as similarity
-- FROM active_memory_records
-- WHERE user_id = 'user123'
-- ORDER BY embedding <=> query_embedding
-- LIMIT 10;

-- 2. Get memories by importance
-- SELECT * FROM active_memory_records
-- WHERE user_id = 'user123'
--   AND type = 'semantic'
-- ORDER BY importance DESC, created_at DESC
-- LIMIT 10;

-- 3. Get episodic memories in time range
-- SELECT * FROM active_memory_records
-- WHERE user_id = 'user123'
--   AND type = 'episodic'
--   AND created_at BETWEEN '2025-01-01' AND '2025-01-31'
-- ORDER BY created_at DESC;

-- 4. Update access tracking
-- UPDATE memory_records
-- SET last_accessed_at = NOW(),
--     access_count = access_count + 1
-- WHERE id = 'memory-uuid';

-- 5. Cleanup expired memories (run daily)
-- SELECT cleanup_expired_memory();

-- Comments
COMMENT ON TABLE memory_records IS 'Long-term memory storage with vector embeddings for semantic search';
COMMENT ON COLUMN memory_records.type IS 'Memory type: episodic (event-based) or semantic (fact-based)';
COMMENT ON COLUMN memory_records.embedding IS 'Vector embedding (1536-dim) for semantic similarity search';
COMMENT ON COLUMN memory_records.importance IS 'Importance score [0.0, 1.0] for prioritization';
COMMENT ON COLUMN memory_records.ttl_days IS 'Time-to-live in days before expiration';
COMMENT ON COLUMN memory_records.refs IS 'Array of article IDs or URLs referenced';
COMMENT ON COLUMN memory_records.expires_at IS 'Auto-calculated expiration timestamp';
COMMENT ON FUNCTION cleanup_expired_memory() IS 'Soft-delete expired memory records';
