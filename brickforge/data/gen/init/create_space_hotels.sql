CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.space_hotels (
    hotel_id STRING,
    hotel_name STRING,
    location STRING,
    orbit_type STRING,
    star_rating INT,
    total_rooms INT,
    price_per_night_credits DOUBLE,
    is_operational BOOLEAN
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.space_hotels VALUES
('HTL-001', 'Lunar Grand Hyatt', 'Luna Surface', 'Surface Base', 5, 180, 9500.0, TRUE),
('HTL-002', 'Olympus Mons Resort', 'Mars Orbit', 'Low Orbit', 4, 120, 7250.5, TRUE),
('HTL-003', 'Europa Deep Station', 'Europa', 'Surface Base', 3, 45, 5800.75, TRUE),
('HTL-004', 'Titan Sky Lounge', 'Titan', 'Low Orbit', 4, 75, 8100.0, TRUE),
('HTL-005', 'Orbital Zenith Hotel', 'Low Earth Orbit', 'Geostationary', 5, 200, 9999.99, TRUE),
('HTL-006', 'Lagrange Point Suites', 'Low Earth Orbit', 'Lagrange Point', 3, 60, 3450.25, FALSE),
('HTL-007', 'Crimson Dunes Retreat', 'Mars Orbit', 'Geostationary', 2, 35, 2100.0, TRUE),
('HTL-008', 'Selene Crater Inn', 'Luna Surface', 'Surface Base', 3, 90, 4750.5, TRUE),
('HTL-009', 'Void Wanderer Station', 'Low Earth Orbit', 'Low Orbit', 1, 20, 599.99, FALSE),
('HTL-010', 'Cassini Ring View Lodge', 'Titan', 'Lagrange Point', 5, 155, 9250.0, TRUE);
