CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.make_reservation(
  p_traveler_id STRING,
  p_hotel_id STRING,
  p_room_type_id STRING,
  p_check_in STRING,
  p_check_out STRING,
  p_num_guests STRING
)
LANGUAGE SQL
SQL SECURITY INVOKER
BEGIN
  INSERT INTO __SCHEMA_QUALIFIED__.reservations (
    reservation_id,
    traveler_id,
    hotel_id,
    room_type_id,
    check_in_date,
    check_out_date,
    num_guests,
    total_cost_credits,
    status,
    created_at
  )
  SELECT
    'RES-' || LPAD(CAST(FLOOR(RAND()*99999) AS STRING), 5, '0'),
    p_traveler_id,
    p_hotel_id,
    p_room_type_id,
    CAST(p_check_in AS DATE),
    CAST(p_check_out AS DATE),
    CAST(p_num_guests AS INT),
    DATEDIFF(CAST(p_check_out AS DATE), CAST(p_check_in AS DATE)) * h.price_per_night_credits * rt.price_modifier,
    'Confirmed',
    current_timestamp()
  FROM __SCHEMA_QUALIFIED__.space_hotels h
  JOIN __SCHEMA_QUALIFIED__.room_types rt ON rt.room_type_id = p_room_type_id AND rt.hotel_id = h.hotel_id
  WHERE h.hotel_id = p_hotel_id;
END
