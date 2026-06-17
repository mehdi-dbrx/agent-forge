CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.flights_at_risk(
    p_zone STRING,
    p_time_start STRING,
    p_time_end STRING
)
RETURNS TABLE(flight_number STRING, departure_time TIMESTAMP_NTZ)
LANGUAGE SQL
RETURN
    SELECT flight_number, departure_time
    FROM __SCHEMA_QUALIFIED__.flights
    WHERE zone = p_zone
    AND departure_time >= CAST(p_time_start AS TIMESTAMP_NTZ)
    AND departure_time < CAST(p_time_end AS TIMESTAMP_NTZ)
    AND flight_number IS NOT NULL
    AND departure_time IS NOT NULL;
