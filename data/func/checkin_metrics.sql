-- Check-in metrics for a given flight: zone, departure time, delay risk, and status. Param: {flight_number}
SELECT `flight_number`, `zone`, `departure_time`, `delay_risk`, `status`
FROM __SCHEMA_QUALIFIED__.`flights`
WHERE `flight_number` = '{flight_number}';
