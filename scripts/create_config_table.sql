-- Create config table for storing dynamic configuration values
-- This table stores scoring weights and other runtime configuration

CREATE TABLE IF NOT EXISTS config (
    config_key TEXT PRIMARY KEY,
    config_value TEXT NOT NULL,
    config_type TEXT NOT NULL DEFAULT 'string',  -- 'string', 'int', 'float', 'bool', 'json'
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT DEFAULT 'system'
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_config_key ON config(config_key);

-- Insert default scoring weights
INSERT INTO config (config_key, config_value, config_type, description) VALUES
    ('scoring.semantic_weight', '0.58', 'float', 'Weight for semantic similarity score'),
    ('scoring.fts_weight', '0.32', 'float', 'Weight for full-text search score'),
    ('scoring.freshness_weight', '0.06', 'float', 'Weight for article freshness'),
    ('scoring.source_weight', '0.04', 'float', 'Weight for source reputation'),
    ('scoring.tau_hours', '72', 'int', 'Time decay parameter in hours'),
    ('scoring.max_per_domain', '3', 'int', 'Maximum results per domain'),
    ('scoring.max_per_article', '2', 'int', 'Maximum chunks per article')
ON CONFLICT (config_key) DO NOTHING;  -- Don't overwrite existing values

-- Add comment to table
COMMENT ON TABLE config IS 'Runtime configuration storage for dynamic settings';
COMMENT ON COLUMN config.config_key IS 'Unique configuration key (e.g., scoring.semantic_weight)';
COMMENT ON COLUMN config.config_value IS 'Configuration value stored as text';
COMMENT ON COLUMN config.config_type IS 'Data type of the value for proper parsing';
