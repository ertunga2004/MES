-- F-STA-B Station Tracking Migration Preparation.
--
-- This migration prepares station-level movement history for MESQL.
-- It does not make PostgreSQL the source-of-truth, does not touch runtime
-- JSON/Excel/FERP/MQTT flows, and intentionally keeps station events separate
-- from mes.production_completions.

CREATE SCHEMA IF NOT EXISTS mes;

-- mes.stations already exists in 001_initial_mes_schema.sql. Keep this
-- definition here so the station tracking migration is reviewable and can
-- safely prepare the master table when applied to an equivalent empty schema.
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

-- Existing 001 schema has a partial unique index on station_code. A foreign
-- key target needs a full unique key, so F-STA-B adds an explicit constraint
-- without changing existing station rows or forcing station_code NOT NULL.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_mes_stations_station_code'
          AND conrelid = 'mes.stations'::regclass
    ) THEN
        ALTER TABLE mes.stations
            ADD CONSTRAINT uq_mes_stations_station_code UNIQUE (station_code);
    END IF;
END $$;

INSERT INTO mes.stations (
    station_id,
    station_code,
    station_name,
    active,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata
) VALUES
    (
        'ASSEMBLY_01',
        'ASSEMBLY_01',
        'İstasyon 1 - Montaj',
        true,
        'mes_web',
        '003_station_tracking_schema',
        'station:ASSEMBLY_01',
        jsonb_build_object('phase', 'F-STA-B', 'seed', true, 'station_role', 'assembly'),
        jsonb_build_object('migration', '003_station_tracking_schema')
    ),
    (
        'PACKAGING_01',
        'PACKAGING_01',
        'İstasyon 2 - Paketleme',
        true,
        'mes_web',
        '003_station_tracking_schema',
        'station:PACKAGING_01',
        jsonb_build_object('phase', 'F-STA-B', 'seed', true, 'station_role', 'packaging'),
        jsonb_build_object('migration', '003_station_tracking_schema')
    )
ON CONFLICT (station_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS mes.item_station_events (
    item_station_event_pk BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    station_code TEXT NOT NULL,
    work_order_no TEXT,
    package_id TEXT,
    serial_no TEXT,
    event_time TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    source_file TEXT,
    external_ref TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mes_item_station_events_event_type'
          AND conrelid = 'mes.item_station_events'::regclass
    ) THEN
        ALTER TABLE mes.item_station_events
            ADD CONSTRAINT ck_mes_item_station_events_event_type
            CHECK (
                event_type IN (
                    'ENTER',
                    'EXIT',
                    'COMPLETE',
                    'BUFFER_IN',
                    'BUFFER_OUT',
                    'PACKAGE_START',
                    'PACKAGE_FINISH',
                    'QUALITY_LOCK'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mes_item_station_events_station_code_nonblank'
          AND conrelid = 'mes.item_station_events'::regclass
    ) THEN
        ALTER TABLE mes.item_station_events
            ADD CONSTRAINT ck_mes_item_station_events_station_code_nonblank
            CHECK (btrim(station_code) <> '');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mes_item_station_events_source_nonblank'
          AND conrelid = 'mes.item_station_events'::regclass
    ) THEN
        ALTER TABLE mes.item_station_events
            ADD CONSTRAINT ck_mes_item_station_events_source_nonblank
            CHECK (btrim(source) <> '');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mes_item_station_events_external_ref_nonblank'
          AND conrelid = 'mes.item_station_events'::regclass
    ) THEN
        ALTER TABLE mes.item_station_events
            ADD CONSTRAINT ck_mes_item_station_events_external_ref_nonblank
            CHECK (btrim(external_ref) <> '');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_mes_item_station_events_source_external_ref'
          AND conrelid = 'mes.item_station_events'::regclass
    ) THEN
        ALTER TABLE mes.item_station_events
            ADD CONSTRAINT uq_mes_item_station_events_source_external_ref
            UNIQUE (source, external_ref);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_mes_item_station_events_station_code'
          AND conrelid = 'mes.item_station_events'::regclass
    ) THEN
        ALTER TABLE mes.item_station_events
            ADD CONSTRAINT fk_mes_item_station_events_station_code
            FOREIGN KEY (station_code)
            REFERENCES mes.stations (station_code);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_station_code
    ON mes.item_station_events (station_code);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_event_time
    ON mes.item_station_events (event_time);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_work_order_no
    ON mes.item_station_events (work_order_no);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_package_id
    ON mes.item_station_events (package_id);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_external_ref
    ON mes.item_station_events (external_ref);
