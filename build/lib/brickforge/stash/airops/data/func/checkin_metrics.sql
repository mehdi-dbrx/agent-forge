CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.checkin_metrics(
    p_flight_number STRING
)
RETURNS TABLE(flight_number STRING, zone STRING, departure_time TIMESTAMP_NTZ, delay_risk STRING, status STRING)
LANGUAGE SQL
RETURN
    SELECT flight_number, zone, departure_time, delay_risk, status
    FROM __SCHEMA_QUALIFIED__.flights
    WHERE flight_number = p_flight_number;
