-- 005_station_execution_seed_minimal.sql
-- Minimal SQL-driven station execution master/config seed for the local
-- box packaging demo scenario.
--
-- This seed is idempotent and writes only to:
-- - mes.items
-- - mes.process_routes
-- - mes.route_operations
-- - mes.station_event_sources
-- - mes.operation_steps

BEGIN;

INSERT INTO mes.items (
    item_id,
    item_code,
    item_name,
    item_type,
    unit,
    active,
    source_system,
    external_ref,
    metadata
)
VALUES
    (
        'ITEM_RAW_BOX',
        'RAW_BOX',
        'Raw Box',
        'raw_material',
        'piece',
        true,
        'local_seed',
        'seed:005:items:RAW_BOX',
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ITEM_COLOR_CLASSIFIED_BOX',
        'COLOR_CLASSIFIED_BOX',
        'Color Classified Box',
        'semi_finished',
        'piece',
        true,
        'local_seed',
        'seed:005:items:COLOR_CLASSIFIED_BOX',
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ITEM_PACKAGED_PRODUCT',
        'PACKAGED_PRODUCT',
        'Packaged Product',
        'finished_good',
        'piece',
        true,
        'local_seed',
        'seed:005:items:PACKAGED_PRODUCT',
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    )
ON CONFLICT (item_code) DO UPDATE SET
    item_id = EXCLUDED.item_id,
    item_name = EXCLUDED.item_name,
    item_type = EXCLUDED.item_type,
    unit = EXCLUDED.unit,
    active = EXCLUDED.active,
    source_system = EXCLUDED.source_system,
    external_ref = EXCLUDED.external_ref,
    metadata = EXCLUDED.metadata,
    updated_at = now();

INSERT INTO mes.process_routes (
    route_id,
    route_code,
    route_name,
    item_code,
    version,
    active,
    source_system,
    external_ref,
    metadata
)
VALUES (
    'ROUTE_BOX_PACKAGING_V1',
    'ROUTE_BOX_PACKAGING_V1',
    'Box Packaging Demo Route V1',
    'PACKAGED_PRODUCT',
    1,
    true,
    'local_seed',
    'seed:005:process_routes:ROUTE_BOX_PACKAGING_V1',
    '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
)
ON CONFLICT (route_code, version) DO UPDATE SET
    route_id = EXCLUDED.route_id,
    route_name = EXCLUDED.route_name,
    item_code = EXCLUDED.item_code,
    active = EXCLUDED.active,
    source_system = EXCLUDED.source_system,
    external_ref = EXCLUDED.external_ref,
    metadata = EXCLUDED.metadata,
    updated_at = now();

INSERT INTO mes.route_operations (
    route_operation_id,
    route_code,
    route_version,
    sequence_no,
    operation_code,
    operation_name,
    station_code,
    input_item_code,
    output_item_code,
    input_qty_per_cycle,
    output_qty_per_cycle,
    input_location_role,
    output_location_role,
    scrap_location_role,
    operation_completion_policy,
    planned_cycle_time_sec,
    active,
    metadata
)
VALUES
    (
        'ROUTE_BOX_PACKAGING_V1_OP10',
        'ROUTE_BOX_PACKAGING_V1',
        1,
        10,
        'OP10_ASSEMBLY_CLASSIFICATION',
        'Assembly / Classification',
        'ASSEMBLY_01',
        'RAW_BOX',
        'COLOR_CLASSIFIED_BOX',
        1,
        1,
        'input',
        'output_buffer',
        'output_scrap',
        'auto_complete_pending_approval',
        NULL,
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ROUTE_BOX_PACKAGING_V1_OP20',
        'ROUTE_BOX_PACKAGING_V1',
        1,
        20,
        'OP20_PACKAGING',
        'Packaging',
        'PACKAGING_01',
        'COLOR_CLASSIFIED_BOX',
        'PACKAGED_PRODUCT',
        1,
        1,
        'input',
        'output_good',
        'output_scrap',
        'auto_complete_pending_approval',
        NULL,
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    )
ON CONFLICT (route_operation_id) DO UPDATE SET
    route_code = EXCLUDED.route_code,
    route_version = EXCLUDED.route_version,
    sequence_no = EXCLUDED.sequence_no,
    operation_code = EXCLUDED.operation_code,
    operation_name = EXCLUDED.operation_name,
    station_code = EXCLUDED.station_code,
    input_item_code = EXCLUDED.input_item_code,
    output_item_code = EXCLUDED.output_item_code,
    input_qty_per_cycle = EXCLUDED.input_qty_per_cycle,
    output_qty_per_cycle = EXCLUDED.output_qty_per_cycle,
    input_location_role = EXCLUDED.input_location_role,
    output_location_role = EXCLUDED.output_location_role,
    scrap_location_role = EXCLUDED.scrap_location_role,
    operation_completion_policy = EXCLUDED.operation_completion_policy,
    planned_cycle_time_sec = EXCLUDED.planned_cycle_time_sec,
    active = EXCLUDED.active,
    metadata = EXCLUDED.metadata,
    updated_at = now();

INSERT INTO mes.station_event_sources (
    event_source_id,
    station_code,
    source_code,
    source_name,
    source_type,
    event_channel,
    mqtt_topic,
    active,
    metadata
)
VALUES
    (
        'ASSEMBLY_01_COLOR_SENSOR_ENTRY',
        'ASSEMBLY_01',
        'COLOR_SENSOR_ENTRY',
        'Color Sensor Entry',
        'sensor',
        'mqtt',
        'mes/stations/ASSEMBLY_01/sources/COLOR_SENSOR_ENTRY/events',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ASSEMBLY_01_ROBOT_ARM_DROP',
        'ASSEMBLY_01',
        'ROBOT_ARM_DROP',
        'Robot Arm Drop',
        'robot',
        'mqtt',
        'mes/stations/ASSEMBLY_01/sources/ROBOT_ARM_DROP/events',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ASSEMBLY_01_KIOSK_OPERATOR',
        'ASSEMBLY_01',
        'KIOSK_OPERATOR',
        'Kiosk Operator',
        'kiosk',
        'kiosk',
        NULL,
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'PACKAGING_01_KIOSK_OPERATOR',
        'PACKAGING_01',
        'KIOSK_OPERATOR',
        'Kiosk Operator',
        'kiosk',
        'kiosk',
        NULL,
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    )
ON CONFLICT (station_code, source_code) DO UPDATE SET
    event_source_id = EXCLUDED.event_source_id,
    source_name = EXCLUDED.source_name,
    source_type = EXCLUDED.source_type,
    event_channel = EXCLUDED.event_channel,
    mqtt_topic = EXCLUDED.mqtt_topic,
    active = EXCLUDED.active,
    metadata = EXCLUDED.metadata,
    updated_at = now();

INSERT INTO mes.operation_steps (
    operation_step_id,
    route_operation_id,
    operation_code,
    step_no,
    step_code,
    step_name,
    start_mode,
    finish_mode,
    start_event_source_code,
    finish_event_source_code,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    actor_type,
    active,
    metadata
)
VALUES
    (
        'ROUTE_BOX_PACKAGING_V1_OP10_STEP10',
        'ROUTE_BOX_PACKAGING_V1_OP10',
        'OP10_ASSEMBLY_CLASSIFICATION',
        10,
        'COLOR_SENSOR_ENTRY_EVIDENCE',
        'Color Sensor Entry Evidence',
        'auto_start',
        'auto_finish',
        'COLOR_SENSOR_ENTRY',
        'COLOR_SENSOR_ENTRY',
        true,
        false,
        false,
        'sensor',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ROUTE_BOX_PACKAGING_V1_OP10_STEP20',
        'ROUTE_BOX_PACKAGING_V1_OP10',
        'OP10_ASSEMBLY_CLASSIFICATION',
        20,
        'ROBOT_ARM_DROP_COMPLETED',
        'Robot Arm Drop Completed',
        'implicit_start',
        'auto_finish',
        NULL,
        'ROBOT_ARM_DROP',
        true,
        false,
        false,
        'robot',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ROUTE_BOX_PACKAGING_V1_OP10_STEP30',
        'ROUTE_BOX_PACKAGING_V1_OP10',
        'OP10_ASSEMBLY_CLASSIFICATION',
        30,
        'OPERATOR_OBSERVATION_APPROVAL',
        'Operator Observation Approval',
        'implicit_start',
        'manual_finish',
        NULL,
        'KIOSK_OPERATOR',
        true,
        true,
        true,
        'operator',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ROUTE_BOX_PACKAGING_V1_OP20_STEP10',
        'ROUTE_BOX_PACKAGING_V1_OP20',
        'OP20_PACKAGING',
        10,
        'PACKAGING_START',
        'Packaging Start',
        'manual_start',
        'implicit_finish',
        'KIOSK_OPERATOR',
        NULL,
        true,
        true,
        false,
        'operator',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    ),
    (
        'ROUTE_BOX_PACKAGING_V1_OP20_STEP20',
        'ROUTE_BOX_PACKAGING_V1_OP20',
        'OP20_PACKAGING',
        20,
        'PACKAGING_FINAL_APPROVAL',
        'Packaging Final Approval',
        'implicit_start',
        'manual_finish',
        NULL,
        'KIOSK_OPERATOR',
        true,
        true,
        true,
        'operator',
        true,
        '{"seed":"005_station_execution_seed_minimal","scenario":"box_packaging_demo"}'::jsonb
    )
ON CONFLICT (route_operation_id, step_code) DO UPDATE SET
    operation_step_id = EXCLUDED.operation_step_id,
    operation_code = EXCLUDED.operation_code,
    step_no = EXCLUDED.step_no,
    step_name = EXCLUDED.step_name,
    start_mode = EXCLUDED.start_mode,
    finish_mode = EXCLUDED.finish_mode,
    start_event_source_code = EXCLUDED.start_event_source_code,
    finish_event_source_code = EXCLUDED.finish_event_source_code,
    required_for_completion = EXCLUDED.required_for_completion,
    records_duration = EXCLUDED.records_duration,
    approval_required_after_finish = EXCLUDED.approval_required_after_finish,
    actor_type = EXCLUDED.actor_type,
    active = EXCLUDED.active,
    metadata = EXCLUDED.metadata,
    updated_at = now();

COMMIT;
