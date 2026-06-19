CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.border_officer_staffing(
    p_zone STRING
)
RETURNS TABLE(at_post STRING, officer_count LONG, officer_names ARRAY<STRING>)
LANGUAGE SQL
RETURN
    SELECT at_post, COUNT(*) AS officer_count, COLLECT_LIST(name) AS officer_names
    FROM __SCHEMA_QUALIFIED__.border_officers
    WHERE TRIM(UPPER(zone)) = CONCAT('ZONE ', UPPER(p_zone))
    AND at_post IN ('ACTIVE', 'AWAY', 'BREAK')
    GROUP BY at_post;
