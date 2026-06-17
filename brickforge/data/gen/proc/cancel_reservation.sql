CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.cancel_reservation(p_reservation_id STRING)
LANGUAGE SQL
SQL SECURITY INVOKER
BEGIN
  UPDATE __SCHEMA_QUALIFIED__.reservations SET status = 'Cancelled' WHERE reservation_id = p_reservation_id;
END
