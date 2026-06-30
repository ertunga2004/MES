-- MESQL integration v2 edge schema.
--
-- This migration is intentionally additive and is not executed automatically by
-- MES Web. Apply it manually in a controlled local MES DB session.

CREATE SCHEMA IF NOT EXISTS mes;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS mes.work_order_operations (
    work_order_operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id text NOT NULL REFERENCES mes.work_orders(order_id) ON DELETE CASCADE,
    mesql_work_order_operation_id uuid NULL,
    operation_no integer NOT NULL,
    operation_code text NOT NULL,
    operation_name text NOT NULL,
    sequence_no integer NOT NULL,
    station_code text NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    planned_quantity numeric(18,6) NULL,
    good_quantity numeric(18,6) NOT NULL DEFAULT 0,
    scrap_quantity numeric(18,6) NOT NULL DEFAULT 0,
    uom_code text NULL,
    started_at timestamptz NULL,
    completed_at timestamptz NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mes_work_order_operations_order_operation UNIQUE (order_id, operation_no),
    CONSTRAINT uq_mes_work_order_operations_order_sequence UNIQUE (order_id, sequence_no)
);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operations_station_status_sequence
    ON mes.work_order_operations (station_code, status, sequence_no);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operations_order_status
    ON mes.work_order_operations (order_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_work_order_operations_mesql_id
    ON mes.work_order_operations (mesql_work_order_operation_id)
    WHERE mesql_work_order_operation_id IS NOT NULL;

ALTER TABLE mes.station_queue
    ADD COLUMN IF NOT EXISTS work_order_operation_id uuid NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_mes_station_queue_work_order_operation'
          AND conrelid = 'mes.station_queue'::regclass
    ) THEN
        ALTER TABLE mes.station_queue
            ADD CONSTRAINT fk_mes_station_queue_work_order_operation
            FOREIGN KEY (work_order_operation_id)
            REFERENCES mes.work_order_operations (work_order_operation_id)
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_mes_station_queue_work_order_operation_id
    ON mes.station_queue (work_order_operation_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mes_station_queue_station_operation
    ON mes.station_queue (station_code, work_order_operation_id)
    WHERE work_order_operation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.packaging_units (
    packaging_unit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    package_no text NOT NULL UNIQUE,
    order_id text NOT NULL REFERENCES mes.work_orders(order_id) ON DELETE CASCADE,
    work_order_operation_id uuid NULL REFERENCES mes.work_order_operations(work_order_operation_id) ON DELETE SET NULL,
    station_code text NULL,
    product_code text NULL,
    quantity numeric(18,6) NOT NULL,
    uom_code text NULL,
    status text NOT NULL DEFAULT 'planned',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_packaging_units_order_id
    ON mes.packaging_units (order_id);

CREATE INDEX IF NOT EXISTS ix_mes_packaging_units_work_order_operation_id
    ON mes.packaging_units (work_order_operation_id);

CREATE TABLE IF NOT EXISTS mes.integration_inbox (
    inbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL DEFAULT 'mesql',
    source_endpoint text NULL,
    source_id text NULL,
    message_type text NOT NULL,
    dedupe_key text NOT NULL UNIQUE,
    payload jsonb NOT NULL,
    processed_at timestamptz NULL,
    error_text text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mes.integration_outbox (
    outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    target_system text NOT NULL DEFAULT 'mesql',
    event_type text NOT NULL,
    order_id text NULL,
    work_order_operation_id uuid NULL,
    station_code text NULL,
    dedupe_key text NOT NULL UNIQUE,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    last_error text NULL,
    pushed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_integration_outbox_status_created
    ON mes.integration_outbox (status, created_at);

CREATE INDEX IF NOT EXISTS ix_mes_integration_outbox_order_id
    ON mes.integration_outbox (order_id);
