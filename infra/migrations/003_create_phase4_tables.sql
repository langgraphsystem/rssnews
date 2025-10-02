-- Phase 4 Tables: History, Schedules, Alerts
-- Migration: 003

-- ============================================================================
-- 1. METRICS HISTORY TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase4_metrics (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id VARCHAR(128),
    metric VARCHAR(64) NOT NULL,  -- 'traffic', 'ctr', 'conv', 'roi', 'cac', 'ltv'
    value FLOAT NOT NULL,
    time_window VARCHAR(16),  -- '1h', '1d', '1w', etc.
    source VARCHAR(64),  -- 'dashboard', 'reports', 'manual'
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_phase4_metrics_ts ON phase4_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS idx_phase4_metrics_user_metric ON phase4_metrics(user_id, metric, ts DESC);
CREATE INDEX IF NOT EXISTS idx_phase4_metrics_metric_window ON phase4_metrics(metric, time_window, ts DESC);

-- ============================================================================
-- 2. SNAPSHOTS TABLE (trends, momentum, sentiment)
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase4_snapshots (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id VARCHAR(128),
    topic VARCHAR(512) NOT NULL,
    momentum FLOAT DEFAULT 0.0,  -- -1.0 to 1.0
    sentiment FLOAT DEFAULT 0.0,  -- -1.0 to 1.0
    volume INT DEFAULT 0,  -- article count
    time_window VARCHAR(16),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phase4_snapshots_ts ON phase4_snapshots(ts DESC);
CREATE INDEX IF NOT EXISTS idx_phase4_snapshots_user_topic ON phase4_snapshots(user_id, topic, ts DESC);
CREATE INDEX IF NOT EXISTS idx_phase4_snapshots_momentum ON phase4_snapshots(momentum DESC, ts DESC);

-- ============================================================================
-- 3. SCHEDULES TABLE (for /schedule report)
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase4_schedules (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    chat_id VARCHAR(128) NOT NULL,
    schedule_type VARCHAR(32) NOT NULL,  -- 'report'
    report_type VARCHAR(32),  -- 'weekly', 'monthly', 'daily'
    cron_expression VARCHAR(128) NOT NULL,  -- '0 9 * * 1'
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP NOT NULL,
    params JSONB DEFAULT '{}'::jsonb,  -- audience, metrics, lang, etc.
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phase4_schedules_next_run ON phase4_schedules(next_run) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_phase4_schedules_user ON phase4_schedules(user_id);

-- ============================================================================
-- 4. ALERTS TABLE (for /alerts setup)
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase4_alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    chat_id VARCHAR(128) NOT NULL,
    name VARCHAR(128) NOT NULL,
    condition TEXT NOT NULL,  -- 'roi < 200', 'ctr > 0.05', 'error_rate > 0.1'
    metric VARCHAR(64) NOT NULL,  -- extracted from condition
    threshold FLOAT NOT NULL,  -- extracted value
    operator VARCHAR(8) NOT NULL,  -- '<', '>', '<=', '>=', '==', '!='
    time_window VARCHAR(16) DEFAULT '5m',
    severity VARCHAR(8) DEFAULT 'P2',  -- 'P1', 'P2', 'P3'
    action VARCHAR(32) DEFAULT 'notify',  -- 'notify', 'page', 'throttle'
    enabled BOOLEAN DEFAULT TRUE,
    last_triggered TIMESTAMP,
    trigger_count INT DEFAULT 0,
    cooldown_minutes INT DEFAULT 60,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phase4_alerts_enabled ON phase4_alerts(enabled, user_id);
CREATE INDEX IF NOT EXISTS idx_phase4_alerts_metric ON phase4_alerts(metric, enabled);

-- ============================================================================
-- 5. ALERT HISTORY TABLE (log of triggered alerts)
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase4_alert_history (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES phase4_alerts(id) ON DELETE CASCADE,
    triggered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metric_value FLOAT NOT NULL,
    threshold FLOAT NOT NULL,
    condition TEXT NOT NULL,
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_error TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_phase4_alert_history_alert ON phase4_alert_history(alert_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_phase4_alert_history_ts ON phase4_alert_history(triggered_at DESC);

-- ============================================================================
-- 6. COMPETITORS TABLE (for reports competitor analysis)
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase4_competitors (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128),
    domain VARCHAR(256) NOT NULL,
    overlap_score FLOAT DEFAULT 0.0,  -- 0.0 to 1.0
    last_seen TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phase4_competitors_user ON phase4_competitors(user_id, overlap_score DESC);
CREATE INDEX IF NOT EXISTS idx_phase4_competitors_domain ON phase4_competitors(domain);

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE phase4_metrics IS 'Time-series metrics for dashboards and reports';
COMMENT ON TABLE phase4_snapshots IS 'Topic momentum and sentiment snapshots';
COMMENT ON TABLE phase4_schedules IS 'Scheduled reports configuration';
COMMENT ON TABLE phase4_alerts IS 'Alert rules and thresholds';
COMMENT ON TABLE phase4_alert_history IS 'Alert trigger history log';
COMMENT ON TABLE phase4_competitors IS 'Competitor domains for analysis';
