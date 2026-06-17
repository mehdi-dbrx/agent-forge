CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.staffing_duties(
    p_agent_id STRING
)
RETURNS TABLE(zone STRING, counter STRING, assigned_by_id STRING, assigned_at TIMESTAMP_NTZ)
LANGUAGE SQL
RETURN
    SELECT zone, counter, assigned_by_id, assigned_at
    FROM __SCHEMA_QUALIFIED__.checkin_agents
    WHERE agent_id = p_agent_id
    AND staffing_status = 'NEW';
