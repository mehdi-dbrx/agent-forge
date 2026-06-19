CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.update_checkin_agent(
  IN agent_id_param STRING,
  IN zone_param STRING,
  IN counter_param STRING,
  IN at_counter_param STRING,
  IN assigned_by_id_param STRING
)
LANGUAGE SQL
SQL SECURITY INVOKER
AS 
BEGIN
  IF assigned_by_id_param IS NOT NULL THEN
    UPDATE __SCHEMA_QUALIFIED__.checkin_agents
    SET zone = zone_param, counter = counter_param, at_counter = at_counter_param,
        staffing_status = 'NEW', assigned_by_id = assigned_by_id_param, assigned_at = current_timestamp()
    WHERE agent_id = agent_id_param;
  ELSE
    UPDATE __SCHEMA_QUALIFIED__.checkin_agents
    SET zone = zone_param, counter = counter_param, at_counter = at_counter_param
    WHERE agent_id = agent_id_param;
  END IF;
  SELECT 'UPDATED' AS status;
END;
