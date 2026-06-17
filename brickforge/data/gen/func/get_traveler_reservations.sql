CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.get_traveler_reservations(p_search STRING)
RETURNS TABLE (
  reservation_id STRING,
  full_name STRING,
  hotel_name STRING,
  room_type_name STRING,
  check_in_date DATE,
  check_out_date DATE,
  num_guests INT,
  total_cost_credits DOUBLE,
  status STRING
)
LANGUAGE SQL
RETURN
SELECT
  r.reservation_id,
  t.full_name,
  h.hotel_name,
  rt.room_type_name,
  r.check_in_date,
  r.check_out_date,
  r.num_guests,
  r.total_cost_credits,
  r.status
FROM __SCHEMA_QUALIFIED__.travelers t
JOIN __SCHEMA_QUALIFIED__.reservations r ON t.traveler_id = r.traveler_id
JOIN __SCHEMA_QUALIFIED__.space_hotels h ON r.hotel_id = h.hotel_id
JOIN __SCHEMA_QUALIFIED__.room_types rt ON r.room_type_id = rt.room_type_id
WHERE lower(t.full_name) LIKE lower('%' || get_traveler_reservations.p_search || '%')
   OR lower(t.email) LIKE lower('%' || get_traveler_reservations.p_search || '%')
