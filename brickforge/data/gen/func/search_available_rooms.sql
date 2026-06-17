CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.search_available_rooms(p_check_in DATE, p_check_out DATE)
RETURNS TABLE (
  hotel_name STRING,
  location STRING,
  orbit_type STRING,
  star_rating INT,
  price_per_night_credits DOUBLE,
  room_type_name STRING,
  capacity INT,
  has_viewport BOOLEAN,
  gravity_setting STRING,
  price_modifier DOUBLE,
  nightly_rate DOUBLE
)
LANGUAGE SQL
RETURN
SELECT
  h.hotel_name,
  h.location,
  h.orbit_type,
  h.star_rating,
  h.price_per_night_credits,
  rt.room_type_name,
  rt.capacity,
  rt.has_viewport,
  rt.gravity_setting,
  rt.price_modifier,
  h.price_per_night_credits * rt.price_modifier AS nightly_rate
FROM __SCHEMA_QUALIFIED__.space_hotels h
JOIN __SCHEMA_QUALIFIED__.room_types rt ON rt.hotel_id = h.hotel_id
LEFT JOIN __SCHEMA_QUALIFIED__.reservations r
  ON r.room_type_id = rt.room_type_id
  AND r.check_in_date < search_available_rooms.p_check_out
  AND r.check_out_date > search_available_rooms.p_check_in
  AND r.status NOT IN ('Cancelled')
WHERE h.is_operational = true
  AND r.reservation_id IS NULL
ORDER BY nightly_rate
