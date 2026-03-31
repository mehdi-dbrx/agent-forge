CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.update_flight_risk(
    flight_number STRING,
    at_risk BOOLEAN
)
LANGUAGE SQL
BEGIN
    UPDATE __SCHEMA_QUALIFIED__.flights
    SET delay_risk = CASE WHEN at_risk THEN 'AT_RISK' ELSE 'NORMAL' END
    WHERE flights.flight_number = flight_number;
END;
