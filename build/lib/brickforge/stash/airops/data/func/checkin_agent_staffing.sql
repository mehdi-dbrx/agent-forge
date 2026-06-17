CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.checkin_agent_staffing(
    p_zone STRING
)
RETURNS TABLE(status_group STRING, agent_count LONG, agent_names ARRAY<STRING>)
LANGUAGE SQL
RETURN
    SELECT CASE
        WHEN UPPER(at_counter) IN ('AWAY', 'BREAK') THEN 'AWAY_OR_BREAK'
        WHEN UPPER(at_counter) = 'ACTIVE' THEN 'ACTIVE'
        ELSE 'OTHER'
    END AS status_group,
    COUNT(*) AS agent_count,
    COLLECT_LIST(name) AS agent_names
    FROM __SCHEMA_QUALIFIED__.checkin_agents
    WHERE zone = p_zone
    AND at_counter IS NOT NULL
    AND name IS NOT NULL
    GROUP BY status_group;
