CREATE TABLE IF NOT EXISTS mes.station_queue (
    station_queue_pk bigserial PRIMARY KEY,
    station_code text NOT NULL CHECK (btrim(station_code) <> ''),
    order_id text NOT NULL,
    queue_rank integer NOT NULL CHECK (queue_rank >= 0),
    status text NOT NULL DEFAULT 'queued',
    source text NOT NULL DEFAULT 'mes_web',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_mes_station_queue_work_order
        FOREIGN KEY (order_id)
        REFERENCES mes.work_orders (order_id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mes_station_queue_station_order
    ON mes.station_queue (station_code, order_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mes_station_queue_station_active_rank
    ON mes.station_queue (station_code, queue_rank)
    WHERE status IN ('queued', 'active', 'pending_approval');

CREATE INDEX IF NOT EXISTS ix_mes_station_queue_station_status_rank
    ON mes.station_queue (station_code, status, queue_rank);

CREATE INDEX IF NOT EXISTS ix_mes_station_queue_order_id
    ON mes.station_queue (order_id);
