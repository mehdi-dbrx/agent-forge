CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.border_terminals (
    terminal_id STRING,
    zone STRING,
    priority STRING,
    status STRING
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.border_terminals VALUES
('eGate-C1', 'C', 'fast-track',   'OPERATIONAL'),
('eGate-C2', 'C', 'standard', 'OPERATIONAL'),
('eGate-C3', 'C', 'standard',   'OUT OF SERVICE');