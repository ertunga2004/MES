-- 004_station_execution_schema.sql
-- Additive SQL-driven station execution schema.
-- This migration creates master data and runtime sidecar tables for operation-step execution.
-- It does not seed data, mutate existing lifecycle rows, create inventory balances, or run MESQL sync.
--
-- Some audit link columns intentionally start nullable to avoid circular
-- insert/FK ordering issues between execution state, step instances, event
-- ledger, approvals, and production flow events.

CREATE SCHEMA IF NOT EXISTS mes;

CREATE TABLE IF NOT EXISTS mes.items (
    item_pk BIGSERIAL PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE,
    item_code TEXT NOT NULL UNIQUE,
    item_name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    unit TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'local',
    external_ref TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_mes_items_item_code_nonblank
        CHECK (btrim(item_code) <> ''),
    CONSTRAINT ck_mes_items_item_name_nonblank
        CHECK (btrim(item_name) <> ''),
    CONSTRAINT ck_mes_items_unit_nonblank
        CHECK (btrim(unit) <> ''),
    CONSTRAINT ck_mes_items_item_type
        CHECK (
            item_type IN (
                'raw_material',
                'semi_finished',
                'finished_good',
                'card',
                'box',
                'package',
                'service'
            )
        )
);

CREATE INDEX IF NOT EXISTS ix_mes_items_item_type_active
    ON mes.items (item_type, active);

CREATE INDEX IF NOT EXISTS ix_mes_items_active_item_code
    ON mes.items (active, item_code);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_items_source_external_ref
    ON mes.items (source_system, external_ref)
    WHERE external_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.process_routes (
    route_pk BIGSERIAL PRIMARY KEY,
    route_id TEXT NOT NULL UNIQUE,
    route_code TEXT NOT NULL,
    route_name TEXT NOT NULL,
    item_code TEXT NOT NULL,
    version INTEGER NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'local',
    external_ref TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mes_process_routes_code_version
        UNIQUE (route_code, version),
    CONSTRAINT fk_mes_process_routes_item_code
        FOREIGN KEY (item_code)
        REFERENCES mes.items (item_code),
    CONSTRAINT ck_mes_process_routes_route_code_nonblank
        CHECK (btrim(route_code) <> ''),
    CONSTRAINT ck_mes_process_routes_route_name_nonblank
        CHECK (btrim(route_name) <> ''),
    CONSTRAINT ck_mes_process_routes_version_positive
        CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_mes_process_routes_item_active
    ON mes.process_routes (item_code, active);

CREATE INDEX IF NOT EXISTS ix_mes_process_routes_code_active
    ON mes.process_routes (route_code, active);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_process_routes_source_external_ref
    ON mes.process_routes (source_system, external_ref)
    WHERE external_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.route_operations (
    route_operation_pk BIGSERIAL PRIMARY KEY,
    route_operation_id TEXT NOT NULL UNIQUE,
    route_code TEXT NOT NULL,
    route_version INTEGER NOT NULL,
    sequence_no INTEGER NOT NULL,
    operation_code TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    station_code TEXT NOT NULL,
    input_item_code TEXT NOT NULL,
    output_item_code TEXT NOT NULL,
    input_qty_per_cycle NUMERIC(18,6) NOT NULL,
    output_qty_per_cycle NUMERIC(18,6) NOT NULL,
    input_location_role TEXT NOT NULL,
    output_location_role TEXT NOT NULL,
    scrap_location_role TEXT NULL,
    operation_completion_policy TEXT NOT NULL,
    planned_cycle_time_sec INTEGER NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mes_route_operations_route_sequence
        UNIQUE (route_code, route_version, sequence_no),
    CONSTRAINT uq_mes_route_operations_route_operation
        UNIQUE (route_code, route_version, operation_code),
    CONSTRAINT fk_mes_route_operations_route
        FOREIGN KEY (route_code, route_version)
        REFERENCES mes.process_routes (route_code, version),
    CONSTRAINT fk_mes_route_operations_station_code
        FOREIGN KEY (station_code)
        REFERENCES mes.stations (station_code),
    CONSTRAINT fk_mes_route_operations_input_item_code
        FOREIGN KEY (input_item_code)
        REFERENCES mes.items (item_code),
    CONSTRAINT fk_mes_route_operations_output_item_code
        FOREIGN KEY (output_item_code)
        REFERENCES mes.items (item_code),
    CONSTRAINT ck_mes_route_operations_sequence_positive
        CHECK (sequence_no > 0),
    CONSTRAINT ck_mes_route_operations_operation_code_nonblank
        CHECK (btrim(operation_code) <> ''),
    CONSTRAINT ck_mes_route_operations_operation_name_nonblank
        CHECK (btrim(operation_name) <> ''),
    CONSTRAINT ck_mes_route_operations_input_qty_positive
        CHECK (input_qty_per_cycle > 0),
    CONSTRAINT ck_mes_route_operations_output_qty_nonnegative
        CHECK (output_qty_per_cycle >= 0),
    CONSTRAINT ck_mes_route_operations_planned_cycle_positive
        CHECK (planned_cycle_time_sec IS NULL OR planned_cycle_time_sec > 0),
    CONSTRAINT ck_mes_route_operations_completion_policy
        CHECK (
            operation_completion_policy IN (
                'manual_close',
                'auto_close_on_required_steps',
                'auto_complete_pending_approval'
            )
        ),
    CONSTRAINT ck_mes_route_operations_input_location_role
        CHECK (input_location_role IN ('input', 'active_wip')),
    CONSTRAINT ck_mes_route_operations_output_location_role
        CHECK (output_location_role IN ('output_good', 'output_buffer')),
    CONSTRAINT ck_mes_route_operations_scrap_location_role
        CHECK (scrap_location_role IS NULL OR scrap_location_role = 'output_scrap')
);

CREATE INDEX IF NOT EXISTS ix_mes_route_operations_station_active
    ON mes.route_operations (station_code, active);

CREATE INDEX IF NOT EXISTS ix_mes_route_operations_route_sequence
    ON mes.route_operations (route_code, route_version, sequence_no);

CREATE INDEX IF NOT EXISTS ix_mes_route_operations_operation_active
    ON mes.route_operations (operation_code, active);

CREATE TABLE IF NOT EXISTS mes.station_event_sources (
    event_source_pk BIGSERIAL PRIMARY KEY,
    event_source_id TEXT NOT NULL UNIQUE,
    station_code TEXT NOT NULL,
    source_code TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    event_channel TEXT NOT NULL,
    mqtt_topic TEXT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mes_station_event_sources_station_source
        UNIQUE (station_code, source_code),
    CONSTRAINT fk_mes_station_event_sources_station_code
        FOREIGN KEY (station_code)
        REFERENCES mes.stations (station_code),
    CONSTRAINT ck_mes_station_event_sources_source_code_nonblank
        CHECK (btrim(source_code) <> ''),
    CONSTRAINT ck_mes_station_event_sources_source_name_nonblank
        CHECK (btrim(source_name) <> ''),
    CONSTRAINT ck_mes_station_event_sources_source_type
        CHECK (source_type IN ('kiosk', 'sensor', 'robot', 'observer', 'plc', 'system')),
    CONSTRAINT ck_mes_station_event_sources_event_channel
        CHECK (event_channel IN ('mqtt', 'http', 'kiosk', 'internal', 'manual')),
    CONSTRAINT ck_mes_station_event_sources_mqtt_topic
        CHECK (event_channel <> 'mqtt' OR mqtt_topic IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_mes_station_event_sources_station_active
    ON mes.station_event_sources (station_code, active);

CREATE INDEX IF NOT EXISTS ix_mes_station_event_sources_type_active
    ON mes.station_event_sources (source_type, active);

CREATE INDEX IF NOT EXISTS ix_mes_station_event_sources_channel_active
    ON mes.station_event_sources (event_channel, active);

CREATE TABLE IF NOT EXISTS mes.operation_steps (
    operation_step_pk BIGSERIAL PRIMARY KEY,
    operation_step_id TEXT NOT NULL UNIQUE,
    route_operation_id TEXT NOT NULL,
    operation_code TEXT NOT NULL,
    step_no INTEGER NOT NULL,
    step_code TEXT NOT NULL,
    step_name TEXT NOT NULL,
    start_mode TEXT NOT NULL,
    finish_mode TEXT NOT NULL,
    start_event_source_code TEXT NULL,
    finish_event_source_code TEXT NULL,
    required_for_completion BOOLEAN NOT NULL DEFAULT true,
    records_duration BOOLEAN NOT NULL DEFAULT true,
    approval_required_after_finish BOOLEAN NOT NULL DEFAULT false,
    actor_type TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mes_operation_steps_route_step_no
        UNIQUE (route_operation_id, step_no),
    CONSTRAINT uq_mes_operation_steps_route_step_code
        UNIQUE (route_operation_id, step_code),
    CONSTRAINT fk_mes_operation_steps_route_operation
        FOREIGN KEY (route_operation_id)
        REFERENCES mes.route_operations (route_operation_id),
    CONSTRAINT ck_mes_operation_steps_step_no_positive
        CHECK (step_no > 0),
    CONSTRAINT ck_mes_operation_steps_operation_code_nonblank
        CHECK (btrim(operation_code) <> ''),
    CONSTRAINT ck_mes_operation_steps_step_code_nonblank
        CHECK (btrim(step_code) <> ''),
    CONSTRAINT ck_mes_operation_steps_step_name_nonblank
        CHECK (btrim(step_name) <> ''),
    CONSTRAINT ck_mes_operation_steps_start_mode
        CHECK (start_mode IN ('none', 'manual_start', 'auto_start', 'implicit_start')),
    CONSTRAINT ck_mes_operation_steps_finish_mode
        CHECK (finish_mode IN ('none', 'manual_finish', 'auto_finish', 'implicit_finish')),
    CONSTRAINT ck_mes_operation_steps_actor_type
        CHECK (actor_type IN ('operator', 'system', 'sensor', 'robot', 'observer', 'plc')),
    CONSTRAINT ck_mes_operation_steps_auto_start_source
        CHECK (start_mode <> 'auto_start' OR start_event_source_code IS NOT NULL),
    CONSTRAINT ck_mes_operation_steps_auto_finish_source
        CHECK (finish_mode <> 'auto_finish' OR finish_event_source_code IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_mes_operation_steps_route_active_step
    ON mes.operation_steps (route_operation_id, active, step_no);

CREATE INDEX IF NOT EXISTS ix_mes_operation_steps_operation_active
    ON mes.operation_steps (operation_code, active);

CREATE INDEX IF NOT EXISTS ix_mes_operation_steps_start_event_source
    ON mes.operation_steps (start_event_source_code);

CREATE INDEX IF NOT EXISTS ix_mes_operation_steps_finish_event_source
    ON mes.operation_steps (finish_event_source_code);

CREATE TABLE IF NOT EXISTS mes.work_order_operation_execution_state (
    execution_state_pk BIGSERIAL PRIMARY KEY,
    execution_state_id TEXT NOT NULL UNIQUE,
    work_order_operation_id UUID NOT NULL UNIQUE,
    work_order_id TEXT NOT NULL,
    station_code TEXT NOT NULL,
    operation_code TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    operation_completion_policy TEXT NOT NULL,
    current_step_code TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    evidence_completed_at TIMESTAMPTZ NULL,
    pending_final_approval_at TIMESTAMPTZ NULL,
    closed_at TIMESTAMPTZ NULL,
    last_event_id TEXT NULL,
    last_approval_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_mes_operation_execution_state_operation
        FOREIGN KEY (work_order_operation_id)
        REFERENCES mes.work_order_operations (work_order_operation_id),
    CONSTRAINT fk_mes_operation_execution_state_work_order
        FOREIGN KEY (work_order_id)
        REFERENCES mes.work_orders (order_id),
    CONSTRAINT fk_mes_operation_execution_state_station
        FOREIGN KEY (station_code)
        REFERENCES mes.stations (station_code),
    CONSTRAINT ck_mes_operation_execution_state_operation_code_nonblank
        CHECK (btrim(operation_code) <> ''),
    CONSTRAINT ck_mes_operation_execution_state_status
        CHECK (
            execution_status IN (
                'queued',
                'ready',
                'active',
                'evidence_completed',
                'pending_final_approval',
                'closed',
                'cancelled',
                'failed'
            )
        ),
    CONSTRAINT ck_mes_operation_execution_state_completion_policy
        CHECK (
            operation_completion_policy IN (
                'manual_close',
                'auto_close_on_required_steps',
                'auto_complete_pending_approval'
            )
        ),
    CONSTRAINT ck_mes_operation_execution_state_closed_after_evidence
        CHECK (closed_at IS NULL OR evidence_completed_at IS NOT NULL),
    CONSTRAINT ck_mes_operation_execution_state_pending_after_evidence
        CHECK (pending_final_approval_at IS NULL OR evidence_completed_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_mes_operation_execution_state_station_status
    ON mes.work_order_operation_execution_state (station_code, execution_status);

CREATE INDEX IF NOT EXISTS ix_mes_operation_execution_state_work_order_status
    ON mes.work_order_operation_execution_state (work_order_id, execution_status);

CREATE INDEX IF NOT EXISTS ix_mes_operation_execution_state_updated_at
    ON mes.work_order_operation_execution_state (updated_at DESC);

CREATE TABLE IF NOT EXISTS mes.work_order_operation_steps (
    work_order_operation_step_pk BIGSERIAL PRIMARY KEY,
    work_order_operation_step_id TEXT NOT NULL UNIQUE,
    work_order_operation_id UUID NOT NULL,
    work_order_id TEXT NOT NULL,
    operation_code TEXT NOT NULL,
    step_code TEXT NOT NULL,
    step_no INTEGER NOT NULL,
    station_code TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    started_by_event_id TEXT NULL,
    completed_by_event_id TEXT NULL,
    required_for_completion BOOLEAN NOT NULL DEFAULT true,
    records_duration BOOLEAN NOT NULL DEFAULT true,
    approval_required_after_finish BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_mes_work_order_operation_steps_step_code
        UNIQUE (work_order_operation_id, step_code),
    CONSTRAINT uq_mes_work_order_operation_steps_step_no
        UNIQUE (work_order_operation_id, step_no),
    CONSTRAINT fk_mes_work_order_operation_steps_operation
        FOREIGN KEY (work_order_operation_id)
        REFERENCES mes.work_order_operations (work_order_operation_id),
    CONSTRAINT fk_mes_work_order_operation_steps_work_order
        FOREIGN KEY (work_order_id)
        REFERENCES mes.work_orders (order_id),
    CONSTRAINT fk_mes_work_order_operation_steps_station
        FOREIGN KEY (station_code)
        REFERENCES mes.stations (station_code),
    CONSTRAINT ck_mes_work_order_operation_steps_operation_code_nonblank
        CHECK (btrim(operation_code) <> ''),
    CONSTRAINT ck_mes_work_order_operation_steps_step_code_nonblank
        CHECK (btrim(step_code) <> ''),
    CONSTRAINT ck_mes_work_order_operation_steps_step_no_positive
        CHECK (step_no > 0),
    CONSTRAINT ck_mes_work_order_operation_steps_status
        CHECK (status IN ('pending', 'active', 'completed', 'skipped', 'failed', 'cancelled')),
    CONSTRAINT ck_mes_work_order_operation_steps_completed_after_started
        CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operation_steps_operation_status_step
    ON mes.work_order_operation_steps (work_order_operation_id, status, step_no);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operation_steps_station_status
    ON mes.work_order_operation_steps (station_code, status);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operation_steps_work_order_step
    ON mes.work_order_operation_steps (work_order_id, step_no);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operation_steps_required_status
    ON mes.work_order_operation_steps (required_for_completion, status);

CREATE TABLE IF NOT EXISTS mes.operation_events (
    event_pk BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_time TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    station_code TEXT NOT NULL,
    work_order_id TEXT NULL,
    work_order_operation_id UUID NULL,
    work_order_operation_step_id TEXT NULL,
    operation_code TEXT NULL,
    step_code TEXT NULL,
    event_source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    external_event_id TEXT NULL,
    idempotency_key TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    accepted BOOLEAN NOT NULL DEFAULT true,
    rejection_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_mes_operation_events_station
        FOREIGN KEY (station_code)
        REFERENCES mes.stations (station_code),
    CONSTRAINT fk_mes_operation_events_work_order
        FOREIGN KEY (work_order_id)
        REFERENCES mes.work_orders (order_id),
    CONSTRAINT fk_mes_operation_events_operation
        FOREIGN KEY (work_order_operation_id)
        REFERENCES mes.work_order_operations (work_order_operation_id),
    CONSTRAINT fk_mes_operation_events_step
        FOREIGN KEY (work_order_operation_step_id)
        REFERENCES mes.work_order_operation_steps (work_order_operation_step_id),
    CONSTRAINT ck_mes_operation_events_operation_code_nonblank
        CHECK (operation_code IS NULL OR btrim(operation_code) <> ''),
    CONSTRAINT ck_mes_operation_events_step_code_nonblank
        CHECK (step_code IS NULL OR btrim(step_code) <> ''),
    CONSTRAINT ck_mes_operation_events_source_nonblank
        CHECK (btrim(event_source) <> ''),
    CONSTRAINT ck_mes_operation_events_event_type
        CHECK (
            event_type IN (
                'step_start',
                'step_finish',
                'evidence',
                'approval',
                'reject',
                'system_transition'
            )
        ),
    CONSTRAINT ck_mes_operation_events_rejected_reason
        CHECK (accepted = true OR rejection_reason IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_operation_events_station_source_external
    ON mes.operation_events (station_code, event_source, external_event_id)
    WHERE external_event_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_operation_events_idempotency_key
    ON mes.operation_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_mes_operation_events_station_event_time
    ON mes.operation_events (station_code, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_operation_events_operation_event_time
    ON mes.operation_events (work_order_operation_id, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_operation_events_step_event_time
    ON mes.operation_events (work_order_operation_step_id, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_operation_events_accepted_event_time
    ON mes.operation_events (accepted, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_operation_events_source_event_time
    ON mes.operation_events (event_source, event_time DESC);

CREATE TABLE IF NOT EXISTS mes.operation_approvals (
    approval_pk BIGSERIAL PRIMARY KEY,
    approval_id TEXT NOT NULL UNIQUE,
    work_order_operation_id UUID NOT NULL,
    work_order_id TEXT NOT NULL,
    approval_type TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    result TEXT NOT NULL,
    note TEXT NULL,
    source_event_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_mes_operation_approvals_operation
        FOREIGN KEY (work_order_operation_id)
        REFERENCES mes.work_order_operations (work_order_operation_id),
    CONSTRAINT fk_mes_operation_approvals_work_order
        FOREIGN KEY (work_order_id)
        REFERENCES mes.work_orders (order_id),
    CONSTRAINT fk_mes_operation_approvals_source_event
        FOREIGN KEY (source_event_id)
        REFERENCES mes.operation_events (event_id),
    CONSTRAINT ck_mes_operation_approvals_type
        CHECK (approval_type IN ('final', 'supervisor', 'quality')),
    CONSTRAINT ck_mes_operation_approvals_result
        CHECK (result IN ('approved', 'rejected', 'hold')),
    CONSTRAINT ck_mes_operation_approvals_approved_by_nonblank
        CHECK (btrim(approved_by) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_operation_approvals_single_approved_type
    ON mes.operation_approvals (work_order_operation_id, approval_type)
    WHERE result = 'approved';

CREATE INDEX IF NOT EXISTS ix_mes_operation_approvals_operation_type_approved_at
    ON mes.operation_approvals (work_order_operation_id, approval_type, approved_at DESC);

CREATE INDEX IF NOT EXISTS ix_mes_operation_approvals_type_result_approved_at
    ON mes.operation_approvals (approval_type, result, approved_at DESC);

CREATE TABLE IF NOT EXISTS mes.production_flow_events (
    flow_event_pk BIGSERIAL PRIMARY KEY,
    flow_event_id TEXT NOT NULL UNIQUE,
    work_order_id TEXT NOT NULL,
    work_order_operation_id UUID NOT NULL,
    station_code TEXT NOT NULL,
    operation_code TEXT NOT NULL,
    input_location_code TEXT NOT NULL,
    output_location_code TEXT NOT NULL,
    input_item_code TEXT NOT NULL,
    output_item_code TEXT NOT NULL,
    input_qty NUMERIC(18,6) NOT NULL,
    output_qty NUMERIC(18,6) NOT NULL,
    result TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    source_operation_event_id TEXT NULL,
    source_approval_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_mes_production_flow_events_work_order
        FOREIGN KEY (work_order_id)
        REFERENCES mes.work_orders (order_id),
    CONSTRAINT fk_mes_production_flow_events_operation
        FOREIGN KEY (work_order_operation_id)
        REFERENCES mes.work_order_operations (work_order_operation_id),
    CONSTRAINT fk_mes_production_flow_events_station
        FOREIGN KEY (station_code)
        REFERENCES mes.stations (station_code),
    -- Location codes are stored as semantic references in this migration.
    -- They are validated through station/location setup or runtime validation
    -- because locations.location_code is not backed by a full unique constraint
    -- in all local baselines. This migration leaves existing location tables as-is.
    CONSTRAINT fk_mes_production_flow_events_input_item
        FOREIGN KEY (input_item_code)
        REFERENCES mes.items (item_code),
    CONSTRAINT fk_mes_production_flow_events_output_item
        FOREIGN KEY (output_item_code)
        REFERENCES mes.items (item_code),
    CONSTRAINT fk_mes_production_flow_events_source_event
        FOREIGN KEY (source_operation_event_id)
        REFERENCES mes.operation_events (event_id),
    CONSTRAINT fk_mes_production_flow_events_source_approval
        FOREIGN KEY (source_approval_id)
        REFERENCES mes.operation_approvals (approval_id),
    CONSTRAINT ck_mes_production_flow_events_operation_code_nonblank
        CHECK (btrim(operation_code) <> ''),
    CONSTRAINT ck_mes_production_flow_events_input_qty_nonnegative
        CHECK (input_qty >= 0),
    CONSTRAINT ck_mes_production_flow_events_output_qty_nonnegative
        CHECK (output_qty >= 0),
    CONSTRAINT ck_mes_production_flow_events_result
        CHECK (result IN ('good', 'scrap', 'rework', 'hold', 'cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_production_flow_events_operation_approval
    ON mes.production_flow_events (work_order_operation_id, source_approval_id)
    WHERE source_approval_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_production_flow_events_operation_event
    ON mes.production_flow_events (work_order_operation_id, source_operation_event_id)
    WHERE source_operation_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_mes_production_flow_events_work_order_event_time
    ON mes.production_flow_events (work_order_id, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_production_flow_events_operation_event_time
    ON mes.production_flow_events (work_order_operation_id, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_production_flow_events_station_event_time
    ON mes.production_flow_events (station_code, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_production_flow_events_output_location_event_time
    ON mes.production_flow_events (output_location_code, event_time DESC);

CREATE INDEX IF NOT EXISTS ix_mes_production_flow_events_result_event_time
    ON mes.production_flow_events (result, event_time DESC);
