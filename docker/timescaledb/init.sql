-- ============================================================================
-- FreeCalls Analytics Database Schema
-- TimescaleDB (PostgreSQL + Time-Series Extension)
-- ============================================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- Main Calls Table (Hypertable)
-- ============================================================================

CREATE TABLE IF NOT EXISTS calls (
    call_uuid TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    agent_id TEXT,
    duration INTEGER DEFAULT 0,  -- seconds
    wait_time INTEGER DEFAULT 0, -- seconds
    status TEXT DEFAULT 'completed', -- completed, abandoned, missed, failed
    
    -- Multi-leg call tracking
    conference_room TEXT,
    conference_participants TEXT, -- JSON array as text
    
    -- Supervisor monitoring
    supervisor_id TEXT,
    
    -- Recording
    recording_path TEXT,
    
    -- Timestamps (all in UTC)
    parked_at TIMESTAMPTZ,
    bridged_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Composite primary key including partitioning column
    PRIMARY KEY (call_uuid, ended_at)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_calls_ended_at ON calls (ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_calls_agent_id ON calls (agent_id) WHERE agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calls_caller_id ON calls (caller_id);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls (status);

-- Convert to hypertable (partitioned by time)
-- Chunk interval: 7 days (optimize for weekly analysis)
SELECT create_hypertable('calls', 'ended_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- ============================================================================
-- Continuous Aggregates (Pre-computed for fast dashboards)
-- ============================================================================

-- Hourly aggregates (for "today" and "this week" views)
CREATE MATERIALIZED VIEW IF NOT EXISTS calls_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', ended_at) as hour,
    COUNT(*) as total_calls,
    COALESCE(AVG(duration), 0)::INTEGER as avg_duration,
    COALESCE(AVG(wait_time), 0)::INTEGER as avg_wait_time,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_calls,
    SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END) as abandoned_calls,
    SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END) as missed_calls,
    SUM(CASE WHEN agent_id IS NOT NULL THEN 1 ELSE 0 END) as handled_calls
FROM calls
GROUP BY hour
WITH NO DATA;

-- Refresh policy: Update every 15 minutes
SELECT add_continuous_aggregate_policy('calls_hourly',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

-- Daily aggregates (for "this month" and "last 3 months" views)
CREATE MATERIALIZED VIEW IF NOT EXISTS calls_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', ended_at) as day,
    COUNT(*) as total_calls,
    COALESCE(AVG(duration), 0)::INTEGER as avg_duration,
    COALESCE(AVG(wait_time), 0)::INTEGER as avg_wait_time,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_calls,
    SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END) as abandoned_calls,
    SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END) as missed_calls,
    SUM(CASE WHEN agent_id IS NOT NULL THEN 1 ELSE 0 END) as handled_calls
FROM calls
GROUP BY day
WITH NO DATA;

-- Refresh policy: Update daily at 2 AM
SELECT add_continuous_aggregate_policy('calls_daily',
    start_offset => INTERVAL '90 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Agent performance (daily rollup)
CREATE MATERIALIZED VIEW IF NOT EXISTS agent_stats_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', ended_at) as day,
    agent_id,
    COUNT(*) as calls_handled,
    COALESCE(AVG(duration), 0)::INTEGER as avg_duration,
    SUM(duration) as total_talk_time,
    COALESCE(AVG(wait_time), 0)::INTEGER as avg_wait_time,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_calls
FROM calls
WHERE agent_id IS NOT NULL
GROUP BY day, agent_id
WITH NO DATA;

-- Refresh policy: Update every hour
SELECT add_continuous_aggregate_policy('agent_stats_daily',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ============================================================================
-- Data Retention Policy (optional - keep 2 years of raw data)
-- ============================================================================

-- Compress chunks older than 30 days (save storage)
SELECT add_compression_policy('calls', INTERVAL '30 days', if_not_exists => TRUE);

-- Drop chunks older than 2 years (COMMENTED OUT - enable if needed)
-- SELECT add_retention_policy('calls', INTERVAL '2 years', if_not_exists => TRUE);

-- ============================================================================
-- Helper Functions for Dashboard Queries
-- ============================================================================

-- Get call volume for date range with dynamic bucketing
CREATE OR REPLACE FUNCTION get_call_volume(
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ,
    p_interval TEXT DEFAULT 'hour'
)
RETURNS TABLE (
    time_bucket TIMESTAMPTZ,
    call_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        time_bucket(p_interval::INTERVAL, ended_at) as time_bucket,
        COUNT(*) as call_count
    FROM calls
    WHERE ended_at >= p_start AND ended_at < p_end
    GROUP BY time_bucket
    ORDER BY time_bucket;
END;
$$ LANGUAGE plpgsql;

-- Get top agents for date range
CREATE OR REPLACE FUNCTION get_top_agents(
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    agent_id TEXT,
    calls_handled BIGINT,
    avg_duration INTEGER,
    total_talk_time BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.agent_id,
        COUNT(*) as calls_handled,
        COALESCE(AVG(c.duration), 0)::INTEGER as avg_duration,
        SUM(c.duration) as total_talk_time
    FROM calls c
    WHERE c.agent_id IS NOT NULL
      AND c.ended_at >= p_start 
      AND c.ended_at < p_end
    GROUP BY c.agent_id
    ORDER BY calls_handled DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Initial Data (optional - for testing)
-- ============================================================================

-- Uncomment to insert sample data for testing
/*
INSERT INTO calls (call_uuid, caller_id, agent_id, duration, wait_time, status, ended_at) VALUES
('test-uuid-1', '+15551234567', 'agent-101', 245, 12, 'completed', NOW() - INTERVAL '2 hours'),
('test-uuid-2', '+15559876543', 'agent-102', 180, 5, 'completed', NOW() - INTERVAL '1 hour'),
('test-uuid-3', '+15555555555', NULL, 0, 45, 'abandoned', NOW() - INTERVAL '30 minutes');
*/

-- ============================================================================
-- Refresh initial data for continuous aggregates
-- ============================================================================

-- Manually refresh views for immediate availability
-- (Automatic policies will keep them updated going forward)
CALL refresh_continuous_aggregate('calls_hourly', NULL, NULL);
CALL refresh_continuous_aggregate('calls_daily', NULL, NULL);
CALL refresh_continuous_aggregate('agent_stats_daily', NULL, NULL);

COMMIT;
