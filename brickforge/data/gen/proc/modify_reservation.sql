CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.modify_reservation(
    p_reservation_id STRING,
    p_new_check_in STRING,
    p_new_check_out STRING,
    p_new_room_type_id STRING
)
LANGUAGE SQL
SQL SECURITY INVOKER
BEGIN
    UPDATE __SCHEMA_QUALIFIED__.reservations r
    SET
        check_in_date = CAST(p_new_check_in AS DATE),
        check_out_date = CAST(p_new_check_out AS DATE),
        room_type_id = p_new_room_type_id,
        total_cost_credits = (
            SELECT DATEDIFF(CAST(p_new_check_out AS DATE), CAST(p_new_check_in AS DATE)) * h.price_per_night_credits * rt.price_modifier
            FROM __SCHEMA_QUALIFIED__.space_hotels h
            JOIN __SCHEMA_QUALIFIED__.room_types rt ON rt.room_type_id = p_new_room_type_id
            WHERE h.hotel_id = r.hotel_id
            LIMIT 1
        )
    WHERE r.reservation_id = p_reservation_id;
END
