CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.border_officers (
    officer_id STRING,
    name STRING,
    zone STRING,
    at_post STRING
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.border_officers VALUES
('O01', 'J. Martinez', 'C', 'ACTIVE'),
('O02', 'P. Kowalski', 'C', 'ACTIVE'),
('O03', 'A. Chen', 'C', 'BREAK');
