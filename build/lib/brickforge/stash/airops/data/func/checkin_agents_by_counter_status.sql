CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.checkin_agents_by_counter_status(
    p_zone STRING
)
RETURNS TABLE(at_counter STRING, agent_count LONG, agent_ids ARRAY<STRING>, agent_names ARRAY<STRING>)
LANGUAGE SQL
RETURN
    SELECT at_counter, COUNT(*) AS agent_count,
           COLLECT_LIST(agent_id) AS agent_ids,
           COLLECT_LIST(name) AS agent_names
    FROM __SCHEMA_QUALIFIED__.checkin_agents
    WHERE zone = p_zone
    AND at_counter IS NOT NULL
    GROUP BY at_counter
    ORDER BY agent_count DESC;
