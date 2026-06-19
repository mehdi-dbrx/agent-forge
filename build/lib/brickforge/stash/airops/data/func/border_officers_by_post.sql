CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.border_officers_by_post(
    p_zone STRING
)
RETURNS TABLE(status STRING, officer_count LONG, officer_ids ARRAY<STRING>, officer_names ARRAY<STRING>)
LANGUAGE SQL
RETURN
    SELECT at_post AS status, COUNT(*) AS officer_count,
           COLLECT_LIST(officer_id) AS officer_ids,
           COLLECT_LIST(name) AS officer_names
    FROM __SCHEMA_QUALIFIED__.border_officers
    WHERE zone = p_zone
    GROUP BY at_post;
