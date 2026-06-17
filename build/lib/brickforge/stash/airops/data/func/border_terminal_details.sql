CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.border_terminal_details(
    p_zone STRING
)
RETURNS TABLE(terminal_id STRING, status STRING, terminal_count LONG)
LANGUAGE SQL
RETURN
    SELECT terminal_id, status, NULL AS terminal_count
    FROM __SCHEMA_QUALIFIED__.border_terminals
    WHERE zone = p_zone
    UNION ALL
    SELECT 'TOTAL' AS terminal_id, status, COUNT(*) AS terminal_count
    FROM __SCHEMA_QUALIFIED__.border_terminals
    WHERE zone = p_zone
    GROUP BY status;
