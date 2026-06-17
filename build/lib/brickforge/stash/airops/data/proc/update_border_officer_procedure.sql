CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.update_border_officer(
  IN officer_id_param STRING,
  IN at_post_param STRING
)
LANGUAGE SQL
SQL SECURITY INVOKER
AS 
BEGIN
  UPDATE __SCHEMA_QUALIFIED__.border_officers
  SET at_post = at_post_param
  WHERE officer_id = officer_id_param;

  SELECT 'UPDATED' AS status;
END;


--CALL __SCHEMA_QUALIFIED__.update_border_officer('O03', 'ACTIVE');
