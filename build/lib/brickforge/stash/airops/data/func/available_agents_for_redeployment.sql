CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.available_agents_for_redeployment(
    p_zone STRING
)
RETURNS TABLE(agent_id STRING, name STRING, zone STRING, counter STRING, at_counter STRING)
LANGUAGE SQL
RETURN
    SELECT agent_id, name, zone, counter, at_counter
    FROM __SCHEMA_QUALIFIED__.checkin_agents
    WHERE at_counter IN ('BREAK', 'AVAILABLE')
    AND agent_id IS NOT NULL
    AND name IS NOT NULL
    AND (p_zone IS NULL OR zone = p_zone);
