-- MES PostgreSQL transition - initial passive schema.
--
-- This migration is not executed automatically by MES Web. It is a manual
-- starting point for future mirror/outbox phases and is not a source-of-truth
-- migration.

CREATE SCHEMA IF NOT EXISTS mes;

CREATE TABLE IF NOT EXISTS mes.work_orders (
    work_order_pk BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL,
    erp_type TEXT,
    status TEXT,
    product_code TEXT,
    target_quantity INTEGER,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_work_orders_order_id
    ON mes.work_orders (order_id);

CREATE TABLE IF NOT EXISTS mes.work_order_events (
    event_pk BIGSERIAL PRIMARY KEY,
    order_id TEXT,
    event_type TEXT NOT NULL,
    event_at TIMESTAMPTZ,
    actor_id TEXT,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_events_order_id_event_at
    ON mes.work_order_events (order_id, event_at);

CREATE TABLE IF NOT EXISTS mes.production_completions (
    completion_pk BIGSERIAL PRIMARY KEY,
    order_id TEXT,
    item_id TEXT,
    classification TEXT,
    completed_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_production_completions_completed_at
    ON mes.production_completions (completed_at);

CREATE TABLE IF NOT EXISTS mes.oee_snapshots (
    snapshot_pk BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL,
    shift_id TEXT,
    availability NUMERIC(8,4),
    performance NUMERIC(8,4),
    quality NUMERIC(8,4),
    oee NUMERIC(8,4),
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_oee_snapshots_snapshot_at
    ON mes.oee_snapshots (snapshot_at);

CREATE TABLE IF NOT EXISTS mes.downtime_events (
    downtime_pk BIGSERIAL PRIMARY KEY,
    fault_id TEXT,
    status_code TEXT,
    fault_type_code TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_downtime_events_started_at
    ON mes.downtime_events (started_at);

CREATE TABLE IF NOT EXISTS mes.maintenance_records (
    maintenance_pk BIGSERIAL PRIMARY KEY,
    maintenance_row_key TEXT,
    session_id TEXT,
    phase_code TEXT,
    step_code TEXT,
    status TEXT,
    recorded_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_maintenance_records_session_id
    ON mes.maintenance_records (session_id);

CREATE TABLE IF NOT EXISTS mes.quality_overrides (
    quality_override_pk BIGSERIAL PRIMARY KEY,
    item_id TEXT,
    classification TEXT,
    operator_id TEXT,
    recorded_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_quality_overrides_recorded_at
    ON mes.quality_overrides (recorded_at);

CREATE TABLE IF NOT EXISTS mes.vision_events (
    vision_event_pk BIGSERIAL PRIMARY KEY,
    event_key TEXT,
    item_id TEXT,
    event_type TEXT,
    detected_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_vision_events_detected_at
    ON mes.vision_events (detected_at);

CREATE TABLE IF NOT EXISTS mes.device_sessions (
    device_session_pk BIGSERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    device_role TEXT,
    operator_id TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_device_sessions_device_id
    ON mes.device_sessions (device_id);

CREATE TABLE IF NOT EXISTS mes.ferp_import_batches (
    import_batch_pk BIGSERIAL PRIMARY KEY,
    batch_id TEXT,
    source_file TEXT,
    imported_at TIMESTAMPTZ,
    status TEXT,
    source_system TEXT NOT NULL DEFAULT 'ferp',
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_ferp_import_batches_imported_at
    ON mes.ferp_import_batches (imported_at);

CREATE TABLE IF NOT EXISTS mes.ferp_export_outbox (
    export_pk BIGSERIAL PRIMARY KEY,
    export_id TEXT,
    order_id TEXT,
    export_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    artifact_path TEXT,
    created_for_export_at TIMESTAMPTZ,
    exported_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_ferp_export_outbox_status
    ON mes.ferp_export_outbox (status, created_at);

CREATE TABLE IF NOT EXISTS mes.operators (
    operator_pk BIGSERIAL PRIMARY KEY,
    operator_id TEXT,
    operator_code TEXT,
    operator_name TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_operators_operator_code
    ON mes.operators (operator_code)
    WHERE operator_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.stations (
    station_pk BIGSERIAL PRIMARY KEY,
    station_id TEXT,
    station_code TEXT,
    station_name TEXT,
    line_id TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_stations_station_code
    ON mes.stations (station_code)
    WHERE station_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.error_types (
    error_type_pk BIGSERIAL PRIMARY KEY,
    error_type_id TEXT,
    error_type_code TEXT,
    error_category TEXT,
    error_reason TEXT,
    default_station_id TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_error_types_error_type_code
    ON mes.error_types (error_type_code)
    WHERE error_type_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.maintenance_steps (
    maintenance_step_pk BIGSERIAL PRIMARY KEY,
    phase_code TEXT,
    step_code TEXT,
    step_label TEXT,
    required BOOLEAN NOT NULL DEFAULT true,
    sort_order INTEGER,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_maintenance_steps_phase_step
    ON mes.maintenance_steps (phase_code, step_code)
    WHERE phase_code IS NOT NULL AND step_code IS NOT NULL;
