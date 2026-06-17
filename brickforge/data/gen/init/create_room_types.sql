CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.room_types (
    room_type_id STRING,
    hotel_id STRING,
    room_type_name STRING,
    capacity INT,
    has_viewport BOOLEAN,
    gravity_setting STRING,
    price_modifier DOUBLE
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.room_types VALUES
('RT-001', 'HTL-001', 'Zero-G Pod', 1, TRUE, 'Zero-G', 2.5),
('RT-002', 'HTL-001', 'Nebula Penthouse', 4, TRUE, 'Earth Standard (1g)', 3.5),
('RT-003', 'HTL-001', 'Standard Capsule', 2, FALSE, 'Lunar (0.16g)', 0.9),
('RT-004', 'HTL-002', 'Panoramic Suite', 3, TRUE, 'Mars (0.38g)', 2.8),
('RT-005', 'HTL-002', 'Crater View Deluxe', 2, TRUE, 'Lunar (0.16g)', 2.1),
('RT-006', 'HTL-003', 'Zero-G Pod', 1, FALSE, 'Zero-G', 1.8),
('RT-007', 'HTL-003', 'Standard Capsule', 2, FALSE, 'Earth Standard (1g)', 0.8),
('RT-008', 'HTL-003', 'Nebula Penthouse', 4, TRUE, 'Mars (0.38g)', 3.2),
('RT-009', 'HTL-004', 'Crater View Deluxe', 3, TRUE, 'Lunar (0.16g)', 2.4),
('RT-010', 'HTL-004', 'Panoramic Suite', 2, TRUE, 'Zero-G', 3.0),
('RT-011', 'HTL-005', 'Standard Capsule', 1, FALSE, 'Earth Standard (1g)', 0.85),
('RT-012', 'HTL-005', 'Zero-G Pod', 2, TRUE, 'Zero-G', 2.2),
('RT-013', 'HTL-005', 'Crater View Deluxe', 3, TRUE, 'Mars (0.38g)', 2.6),
('RT-014', 'HTL-006', 'Nebula Penthouse', 4, TRUE, 'Earth Standard (1g)', 3.4),
('RT-015', 'HTL-006', 'Standard Capsule', 2, FALSE, 'Lunar (0.16g)', 1.1),
('RT-016', 'HTL-007', 'Panoramic Suite', 3, TRUE, 'Mars (0.38g)', 2.9),
('RT-017', 'HTL-007', 'Zero-G Pod', 1, TRUE, 'Zero-G', 2.3),
('RT-018', 'HTL-007', 'Standard Capsule', 2, FALSE, 'Earth Standard (1g)', 0.95),
('RT-019', 'HTL-008', 'Crater View Deluxe', 2, TRUE, 'Lunar (0.16g)', 1.95),
('RT-020', 'HTL-008', 'Nebula Penthouse', 4, TRUE, 'Zero-G', 3.45),
('RT-021', 'HTL-009', 'Standard Capsule', 1, FALSE, 'Mars (0.38g)', 0.82),
('RT-022', 'HTL-009', 'Panoramic Suite', 3, TRUE, 'Earth Standard (1g)', 2.75),
('RT-023', 'HTL-009', 'Zero-G Pod', 2, TRUE, 'Zero-G', 2.15),
('RT-024', 'HTL-010', 'Nebula Penthouse', 4, TRUE, 'Lunar (0.16g)', 3.35),
('RT-025', 'HTL-010', 'Crater View Deluxe', 3, TRUE, 'Mars (0.38g)', 2.55);
