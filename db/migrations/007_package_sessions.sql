CREATE TABLE IF NOT EXISTS mes.package_sessions (
    session_id text PRIMARY KEY,
    package_order_id text NOT NULL,
    station_code text NOT NULL,
    status text NOT NULL,
    started_at timestamptz,
    finished_at timestamptz,
    duration_seconds numeric,
    source text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_package_sessions_package_order_id
    ON mes.package_sessions (package_order_id);

CREATE INDEX IF NOT EXISTS ix_mes_package_sessions_station_status
    ON mes.package_sessions (station_code, status);
