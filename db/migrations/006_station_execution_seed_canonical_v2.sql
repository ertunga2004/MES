-- 006_station_execution_seed_canonical_v2.sql
-- Additive, versioned canonical V2 station-execution config draft.
-- This draft is intentionally not applied by its creation task.
-- Repository artifact status and inserted config identity are separate:
-- the artifact is a reviewed, unapplied draft; inserted rows identify the
-- canonical V2 configuration through configuration_status metadata.
-- It reuses existing items, stations, event sources, locations, and bindings.
-- It inserts only new V2 process-route, route-operation, and operation-step rows.

BEGIN;

DO $$
BEGIN
    IF (
        SELECT count(*)
        FROM mes.process_routes
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
          AND version = 1
    ) <> 1 THEN
        RAISE EXCEPTION 'V1 process-route baseline mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.route_operations
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
          AND route_version = 1
    ) <> 2 THEN
        RAISE EXCEPTION 'V1 route-operation baseline mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.operation_steps s
        JOIN mes.route_operations ro
          ON ro.route_operation_id = s.route_operation_id
        WHERE ro.route_code = 'ROUTE_BOX_PACKAGING_V1'
          AND ro.route_version = 1
    ) <> 5 THEN
        RAISE EXCEPTION 'V1 operation-step baseline mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.items
        WHERE item_code IN (
            'RAW_BOX',
            'COLOR_CLASSIFIED_BOX',
            'PACKAGED_PRODUCT'
        )
          AND active = true
    ) <> 3 THEN
        RAISE EXCEPTION 'Canonical V2 item prerequisites are missing';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.stations
        WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
          AND active = true
    ) <> 2 THEN
        RAISE EXCEPTION 'Canonical V2 station prerequisites are missing';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.station_event_sources
        WHERE active = true
          AND (
              (station_code = 'ASSEMBLY_01' AND source_code IN (
                  'COLOR_SENSOR_ENTRY',
                  'ROBOT_ARM_DROP',
                  'KIOSK_OPERATOR'
              ))
              OR
              (station_code = 'PACKAGING_01' AND source_code = 'KIOSK_OPERATOR')
          )
    ) <> 4 THEN
        RAISE EXCEPTION 'Canonical V2 event-source prerequisites are missing';
    END IF;
END
$$;

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
SELECT
    'ROUTE_BOX_PACKAGING_V2',
    'ROUTE_BOX_PACKAGING_V2',
    'Box Packaging Canonical Route V2',
    'PACKAGED_PRODUCT',
    2,
    true,
    'local_seed',
    'seed:006:process_routes:ROUTE_BOX_PACKAGING_V2',
    '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM mes.process_routes existing
    WHERE existing.route_id = 'ROUTE_BOX_PACKAGING_V2'
       OR (
           existing.route_code = 'ROUTE_BOX_PACKAGING_V2'
           AND existing.version = 2
       )
       OR existing.external_ref =
          'seed:006:process_routes:ROUTE_BOX_PACKAGING_V2'
);

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
SELECT
    candidate.route_operation_id,
    candidate.route_code,
    candidate.route_version,
    candidate.sequence_no,
    candidate.operation_code,
    candidate.operation_name,
    candidate.station_code,
    candidate.input_item_code,
    candidate.output_item_code,
    candidate.input_qty_per_cycle,
    candidate.output_qty_per_cycle,
    candidate.input_location_role,
    candidate.output_location_role,
    candidate.scrap_location_role,
    candidate.operation_completion_policy,
    candidate.planned_cycle_time_sec,
    candidate.active,
    candidate.metadata
FROM (
    VALUES
        (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2',
            2,
            10,
            'ASSEMBLY_COLOR_CLASSIFY',
            'Assembly / Classification',
            'ASSEMBLY_01',
            'RAW_BOX',
            'COLOR_CLASSIFIED_BOX',
            1::numeric,
            1::numeric,
            'input',
            'output_buffer',
            NULL::text,
            'auto_close_on_required_steps',
            NULL::integer,
            true,
            '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
        ),
        (
            'ROUTE_BOX_PACKAGING_V2_OP20',
            'ROUTE_BOX_PACKAGING_V2',
            2,
            20,
            'PACKAGING_FINAL',
            'Packaging',
            'PACKAGING_01',
            'COLOR_CLASSIFIED_BOX',
            'PACKAGED_PRODUCT',
            1::numeric,
            1::numeric,
            'input',
            'output_good',
            'output_scrap',
            'auto_close_on_required_steps',
            NULL::integer,
            true,
            '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
        )
) AS candidate (
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
WHERE NOT EXISTS (
    SELECT 1
    FROM mes.route_operations existing
    WHERE existing.route_operation_id = candidate.route_operation_id
       OR (
           existing.route_code = candidate.route_code
           AND existing.route_version = candidate.route_version
           AND existing.sequence_no = candidate.sequence_no
       )
       OR (
           existing.route_code = candidate.route_code
           AND existing.route_version = candidate.route_version
           AND existing.operation_code = candidate.operation_code
       )
);

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
SELECT
    candidate.operation_step_id,
    candidate.route_operation_id,
    candidate.operation_code,
    candidate.step_no,
    candidate.step_code,
    candidate.step_name,
    candidate.start_mode,
    candidate.finish_mode,
    candidate.start_event_source_code,
    candidate.finish_event_source_code,
    candidate.required_for_completion,
    candidate.records_duration,
    candidate.approval_required_after_finish,
    candidate.actor_type,
    candidate.active,
    candidate.metadata
FROM (
    VALUES
        (
            'ROUTE_BOX_PACKAGING_V2_OP10_STEP10',
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ASSEMBLY_COLOR_CLASSIFY',
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
            '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
        ),
        (
            'ROUTE_BOX_PACKAGING_V2_OP10_STEP20',
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ASSEMBLY_COLOR_CLASSIFY',
            20,
            'ROBOT_ARM_DROP_COMPLETED',
            'Robot Arm Drop Completed',
            'implicit_start',
            'auto_finish',
            NULL,
            'ROBOT_ARM_DROP',
            true,
            true,
            false,
            'robot',
            true,
            '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
        ),
        (
            'ROUTE_BOX_PACKAGING_V2_OP10_STEP30',
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ASSEMBLY_COLOR_CLASSIFY',
            30,
            'PROCESS_END_OBSERVATION',
            'Proses Sonu Gözlem',
            'manual_start',
            'manual_finish',
            'KIOSK_OPERATOR',
            'KIOSK_OPERATOR',
            true,
            true,
            false,
            'operator',
            true,
            '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
        ),
        (
            'ROUTE_BOX_PACKAGING_V2_OP20_STEP10',
            'ROUTE_BOX_PACKAGING_V2_OP20',
            'PACKAGING_FINAL',
            10,
            'PACKAGING_EXECUTION',
            'Paketleme İşlemi',
            'manual_start',
            'manual_finish',
            'KIOSK_OPERATOR',
            'KIOSK_OPERATOR',
            true,
            true,
            false,
            'operator',
            true,
            '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
        )
) AS candidate (
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
WHERE NOT EXISTS (
    SELECT 1
    FROM mes.operation_steps existing
    WHERE existing.operation_step_id = candidate.operation_step_id
       OR (
           existing.route_operation_id = candidate.route_operation_id
           AND existing.step_no = candidate.step_no
       )
       OR (
           existing.route_operation_id = candidate.route_operation_id
           AND existing.step_code = candidate.step_code
       )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mes.process_routes
        WHERE route_id = 'ROUTE_BOX_PACKAGING_V2'
          AND route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND route_name = 'Box Packaging Canonical Route V2'
          AND item_code = 'PACKAGED_PRODUCT'
          AND version = 2
          AND active = true
          AND source_system = 'local_seed'
          AND external_ref =
              'seed:006:process_routes:ROUTE_BOX_PACKAGING_V2'
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 process route verification failed';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.route_operations
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND route_version = 2
    ) <> 2 THEN
        RAISE EXCEPTION 'Canonical V2 route-operation count mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM mes.route_operations
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
          AND route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND route_version = 2
          AND sequence_no = 10
          AND operation_code = 'ASSEMBLY_COLOR_CLASSIFY'
          AND operation_name = 'Assembly / Classification'
          AND station_code = 'ASSEMBLY_01'
          AND input_item_code = 'RAW_BOX'
          AND output_item_code = 'COLOR_CLASSIFIED_BOX'
          AND input_qty_per_cycle = 1
          AND output_qty_per_cycle = 1
          AND input_location_role = 'input'
          AND output_location_role = 'output_buffer'
          AND scrap_location_role IS NULL
          AND operation_completion_policy =
              'auto_close_on_required_steps'
          AND planned_cycle_time_sec IS NULL
          AND active = true
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 OP10 verification failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM mes.route_operations
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP20'
          AND route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND route_version = 2
          AND sequence_no = 20
          AND operation_code = 'PACKAGING_FINAL'
          AND operation_name = 'Packaging'
          AND station_code = 'PACKAGING_01'
          AND input_item_code = 'COLOR_CLASSIFIED_BOX'
          AND output_item_code = 'PACKAGED_PRODUCT'
          AND input_qty_per_cycle = 1
          AND output_qty_per_cycle = 1
          AND input_location_role = 'input'
          AND output_location_role = 'output_good'
          AND scrap_location_role = 'output_scrap'
          AND operation_completion_policy =
              'auto_close_on_required_steps'
          AND planned_cycle_time_sec IS NULL
          AND active = true
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 OP20 verification failed';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
    ) <> 4 THEN
        RAISE EXCEPTION 'Canonical V2 operation-step count mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
    ) <> 3 THEN
        RAISE EXCEPTION 'Canonical V2 OP10 step count mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP20'
    ) <> 1 THEN
        RAISE EXCEPTION 'Canonical V2 OP20 step count mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
          AND operation_step_id =
              'ROUTE_BOX_PACKAGING_V2_OP10_STEP10'
          AND operation_code = 'ASSEMBLY_COLOR_CLASSIFY'
          AND step_no = 10
          AND step_code = 'COLOR_SENSOR_ENTRY_EVIDENCE'
          AND step_name = 'Color Sensor Entry Evidence'
          AND start_mode = 'auto_start'
          AND finish_mode = 'auto_finish'
          AND start_event_source_code = 'COLOR_SENSOR_ENTRY'
          AND finish_event_source_code = 'COLOR_SENSOR_ENTRY'
          AND required_for_completion = true
          AND records_duration = false
          AND approval_required_after_finish = false
          AND actor_type = 'sensor'
          AND active = true
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 OP10 step 10 verification failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
          AND operation_step_id =
              'ROUTE_BOX_PACKAGING_V2_OP10_STEP20'
          AND operation_code = 'ASSEMBLY_COLOR_CLASSIFY'
          AND step_no = 20
          AND step_code = 'ROBOT_ARM_DROP_COMPLETED'
          AND step_name = 'Robot Arm Drop Completed'
          AND start_mode = 'implicit_start'
          AND finish_mode = 'auto_finish'
          AND start_event_source_code IS NULL
          AND finish_event_source_code = 'ROBOT_ARM_DROP'
          AND required_for_completion = true
          AND records_duration = true
          AND approval_required_after_finish = false
          AND actor_type = 'robot'
          AND active = true
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 OP10 step 20 verification failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
          AND operation_step_id =
              'ROUTE_BOX_PACKAGING_V2_OP10_STEP30'
          AND operation_code = 'ASSEMBLY_COLOR_CLASSIFY'
          AND step_no = 30
          AND step_code = 'PROCESS_END_OBSERVATION'
          AND step_name = 'Proses Sonu Gözlem'
          AND start_mode = 'manual_start'
          AND finish_mode = 'manual_finish'
          AND start_event_source_code = 'KIOSK_OPERATOR'
          AND finish_event_source_code = 'KIOSK_OPERATOR'
          AND required_for_completion = true
          AND records_duration = true
          AND approval_required_after_finish = false
          AND actor_type = 'operator'
          AND active = true
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 OP10 step 30 verification failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP20'
          AND operation_step_id =
              'ROUTE_BOX_PACKAGING_V2_OP20_STEP10'
          AND operation_code = 'PACKAGING_FINAL'
          AND step_no = 10
          AND step_code = 'PACKAGING_EXECUTION'
          AND step_name = 'Paketleme İşlemi'
          AND start_mode = 'manual_start'
          AND finish_mode = 'manual_finish'
          AND start_event_source_code = 'KIOSK_OPERATOR'
          AND finish_event_source_code = 'KIOSK_OPERATOR'
          AND required_for_completion = true
          AND records_duration = true
          AND approval_required_after_finish = false
          AND actor_type = 'operator'
          AND active = true
          AND metadata @>
              '{"seed":"006_station_execution_seed_canonical_v2","scenario":"box_packaging_canonical_v2","configuration_status":"canonical_v2"}'::jsonb
    ) THEN
        RAISE EXCEPTION 'Canonical V2 OP20 step 10 verification failed';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
          AND approval_required_after_finish IS TRUE
    ) <> 0 THEN
        RAISE EXCEPTION 'Canonical V2 embedded approval verification failed';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
          AND step_code IN (
              concat_ws('_', 'OPERATOR', 'OBSERVATION', 'APPROVAL'),
              concat_ws('_', 'PACKAGING', 'FINAL', 'APPROVAL')
          )
    ) <> 0 THEN
        RAISE EXCEPTION 'Canonical V2 legacy step-code verification failed';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mes.route_operations
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND route_version = 2
        GROUP BY sequence_no
        HAVING count(*) <> 1
    ) THEN
        RAISE EXCEPTION 'Canonical V2 route sequence uniqueness failed';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
        GROUP BY route_operation_id, step_no
        HAVING count(*) <> 1
    ) OR EXISTS (
        SELECT 1
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
        GROUP BY route_operation_id, step_code
        HAVING count(*) <> 1
    ) THEN
        RAISE EXCEPTION 'Canonical V2 step uniqueness failed';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.station_event_sources
        WHERE active = true
          AND (
              (station_code = 'ASSEMBLY_01' AND source_code IN (
                  'COLOR_SENSOR_ENTRY',
                  'ROBOT_ARM_DROP',
                  'KIOSK_OPERATOR'
              ))
              OR
              (station_code = 'PACKAGING_01' AND source_code = 'KIOSK_OPERATOR')
          )
    ) <> 4 THEN
        RAISE EXCEPTION 'Canonical V2 active event-source verification failed';
    END IF;

    IF (
        SELECT count(*)
        FROM mes.route_operations route_operation
        CROSS JOIN LATERAL (
            VALUES
                (
                    route_operation.input_location_role,
                    route_operation.input_item_code
                ),
                (
                    route_operation.output_location_role,
                    route_operation.output_item_code
                ),
                (
                    route_operation.scrap_location_role,
                    route_operation.output_item_code
                )
        ) AS configured_role (role, item_code)
        WHERE route_operation.route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
          AND configured_role.role IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM mes.station_location_bindings b
            JOIN mes.locations l
              ON l.location_code = b.location_code
            WHERE b.station_code = route_operation.station_code
              AND b.role = configured_role.role
              AND b.active = true
              AND l.active = true
              AND (
                  b.item_scope IS NULL
                  OR b.item_scope = configured_role.item_code
              )
              AND (
                  b.operation_scope IS NULL
                  OR b.operation_scope = route_operation.operation_code
              )
        )
    ) <> 5 THEN
        RAISE EXCEPTION 'Canonical V2 location-role verification failed';
    END IF;
END
$$;

SELECT
    'v1_counts' AS verification,
    (
        SELECT count(*)
        FROM mes.process_routes
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
          AND version = 1
    ) AS route_count,
    (
        SELECT count(*)
        FROM mes.route_operations
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
          AND route_version = 1
    ) AS route_operation_count,
    (
        SELECT count(*)
        FROM mes.operation_steps s
        JOIN mes.route_operations ro
          ON ro.route_operation_id = s.route_operation_id
        WHERE ro.route_code = 'ROUTE_BOX_PACKAGING_V1'
          AND ro.route_version = 1
    ) AS step_count;

SELECT
    'v2_counts' AS verification,
    (
        SELECT count(*)
        FROM mes.process_routes
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND version = 2
    ) AS route_count,
    (
        SELECT count(*)
        FROM mes.route_operations
        WHERE route_code = 'ROUTE_BOX_PACKAGING_V2'
          AND route_version = 2
    ) AS route_operation_count,
    (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
    ) AS step_count,
    (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
    ) AS op10_step_count,
    (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP20'
    ) AS op20_step_count,
    (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id = 'ROUTE_BOX_PACKAGING_V2_OP10'
          AND step_code = 'PROCESS_END_OBSERVATION'
    ) AS process_end_observation_count,
    (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
          AND step_code IN (
              concat_ws('_', 'OPERATOR', 'OBSERVATION', 'APPROVAL'),
              concat_ws('_', 'PACKAGING', 'FINAL', 'APPROVAL')
          )
    ) AS legacy_step_count,
    (
        SELECT count(*)
        FROM mes.operation_steps
        WHERE route_operation_id IN (
            'ROUTE_BOX_PACKAGING_V2_OP10',
            'ROUTE_BOX_PACKAGING_V2_OP20'
        )
          AND approval_required_after_finish IS TRUE
    ) AS embedded_approval_count;

SELECT
    route_operation_id,
    operation_code,
    station_code,
    sequence_no,
    operation_completion_policy,
    active
FROM mes.route_operations
WHERE route_code = 'ROUTE_BOX_PACKAGING_V2'
  AND route_version = 2
ORDER BY sequence_no;

SELECT
    route_operation_id,
    step_no,
    step_code,
    start_mode,
    finish_mode,
    start_event_source_code,
    finish_event_source_code,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    actor_type,
    active
FROM mes.operation_steps
WHERE route_operation_id IN (
    'ROUTE_BOX_PACKAGING_V2_OP10',
    'ROUTE_BOX_PACKAGING_V2_OP20'
)
ORDER BY route_operation_id, step_no;

COMMIT;
