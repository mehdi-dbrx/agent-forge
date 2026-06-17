CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.checkin_metrics (
    zone STRING,
    avg_checkin_time_mins DOUBLE,
    baseline_mins DOUBLE,
    pct_change DOUBLE,
    window_mins INT,
    recorded_at TIMESTAMP_NTZ
)
USING DELTA;

-- Insert anomaly into checkin_metrics
INSERT INTO __SCHEMA_QUALIFIED__.checkin_metrics VALUES
('B', 5.10, 5.0, 2.0, 30, CAST('2026-02-25 10:00:00' AS TIMESTAMP_NTZ));