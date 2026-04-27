CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.checkin_agents (
    agent_id STRING,
    name STRING,
    zone STRING,
    counter STRING,
    at_counter STRING,
    last_checked TIMESTAMP_NTZ,
    staffing_status STRING,
    assigned_by_id STRING,
    assigned_at TIMESTAMP_NTZ
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.checkin_agents VALUES
('A14', 'M. Hassan', 'C', 'C04', 'AVAILABLE', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A10', 'R. Singh',  'C', 'C03', 'ACTIVE', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A13', 'J. Parker', 'C', 'C05', 'ACTIVE', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A15', 'D. Osei',   'C', 'C07', 'ACTIVE', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A01', 'S. Patel',  'B', 'B01', 'AWAY', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A02', 'T. Nguyen', 'B', 'B02', 'BREAK', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A03', 'C. Okafor', 'B', 'B03', 'AWAY', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A11', 'L. Moreno', 'B', 'B08', 'ACTIVE', '2026-02-25T10:00:00.000', NULL, NULL, NULL),
('A12', 'K. Wilson', 'B', 'B15', 'ACTIVE', '2026-02-25T10:00:00.000', NULL, NULL, NULL);
