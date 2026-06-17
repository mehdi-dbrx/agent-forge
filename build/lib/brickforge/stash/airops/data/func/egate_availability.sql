CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.egate_availability(
    p_zone STRING
)
RETURNS TABLE(status STRING, num_terminals LONG, terminal_ids ARRAY<STRING>)
LANGUAGE SQL
RETURN
    SELECT status, COUNT(*) AS num_terminals,
           COLLECT_LIST(terminal_id) AS terminal_ids
    FROM __SCHEMA_QUALIFIED__.border_terminals
    WHERE zone ILIKE CONCAT('%', p_zone, '%')
    AND status IN ('OPERATIONAL', 'OUT OF SERVICE')
    GROUP BY status;
