-- MES work order transition live hook support.
--
-- Keeps the current-state table separate from the append/idempotent transition
-- log used by SQL read cutover diagnostics and rollback-safe sync.

CREATE SCHEMA IF NOT EXISTS mes;

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

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_work_order_events_external_ref
    ON mes.work_order_events (external_ref)
    WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '';
