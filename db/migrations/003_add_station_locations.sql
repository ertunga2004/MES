-- Local MES station/location/buffer Paket A additive static master data migration.
--
-- This migration is manual and additive. It is not executed automatically by
-- MES Web startup, does not require MESQL push/pull, does not change existing
-- operation lifecycle behavior, and does not create inventory movement or
-- balance records.

CREATE SCHEMA IF NOT EXISTS mes;

CREATE TABLE IF NOT EXISTS mes.locations (
    location_pk BIGSERIAL PRIMARY KEY,
    location_id TEXT,
    location_code TEXT NOT NULL,
    location_name TEXT,
    location_type TEXT NOT NULL,
    parent_location_code TEXT,
    station_code TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_locations_location_code
    ON mes.locations (location_code)
    WHERE location_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_mes_locations_location_type_active
    ON mes.locations (location_type, active);

CREATE INDEX IF NOT EXISTS ix_mes_locations_station_code
    ON mes.locations (station_code)
    WHERE station_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS mes.station_location_bindings (
    binding_pk BIGSERIAL PRIMARY KEY,
    binding_id TEXT,
    station_code TEXT NOT NULL,
    role TEXT NOT NULL,
    location_code TEXT NOT NULL,
    item_scope TEXT,
    operation_scope TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    active BOOLEAN NOT NULL DEFAULT true,
    source_system TEXT NOT NULL DEFAULT 'mes_web',
    source_file TEXT,
    external_ref TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_station_location_bindings_active_scope
    ON mes.station_location_bindings (
        station_code,
        role,
        location_code,
        (COALESCE(item_scope, '')),
        (COALESCE(operation_scope, ''))
    )
    WHERE active = true;

CREATE INDEX IF NOT EXISTS ix_mes_station_location_bindings_station_role
    ON mes.station_location_bindings (station_code, role)
    WHERE active = true;

CREATE INDEX IF NOT EXISTS ix_mes_station_location_bindings_location_code
    ON mes.station_location_bindings (location_code);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mes_locations_location_type'
          AND conrelid = 'mes.locations'::regclass
    ) THEN
        ALTER TABLE mes.locations
            ADD CONSTRAINT ck_mes_locations_location_type
            CHECK (
                location_type IN (
                    'raw_material',
                    'wip',
                    'buffer',
                    'finished_goods',
                    'scrap',
                    'hold',
                    'rework'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mes_station_location_bindings_role'
          AND conrelid = 'mes.station_location_bindings'::regclass
    ) THEN
        ALTER TABLE mes.station_location_bindings
            ADD CONSTRAINT ck_mes_station_location_bindings_role
            CHECK (
                role IN (
                    'input',
                    'active_wip',
                    'output_good',
                    'output_scrap',
                    'output_buffer'
                )
            );
    END IF;
END $$;

INSERT INTO mes.stations (
    station_id,
    station_code,
    station_name,
    line_id,
    active,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata
)
SELECT
    seed.station_code,
    seed.station_code,
    seed.station_name,
    'CONVEYOR_LINE_01',
    true,
    'mes_web',
    '003_add_station_locations',
    'seed:station:' || seed.station_code,
    '{}'::jsonb,
    jsonb_build_object('seed_batch', '003_add_station_locations')
FROM (
    VALUES
        ('ASSEMBLY_01', 'Assembly Station 01'),
        ('PACKAGING_01', 'Packaging Station 01')
) AS seed(station_code, station_name)
WHERE NOT EXISTS (
    SELECT 1
    FROM mes.stations existing
    WHERE existing.station_code = seed.station_code
);

INSERT INTO mes.locations (
    location_id,
    location_code,
    location_name,
    location_type,
    parent_location_code,
    station_code,
    active,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata
)
SELECT
    seed.location_code,
    seed.location_code,
    seed.location_name,
    seed.location_type,
    NULL,
    seed.station_code,
    seed.active,
    'mes_web',
    '003_add_station_locations',
    'seed:location:' || seed.location_code,
    '{}'::jsonb,
    jsonb_build_object(
        'seed_batch',
        '003_add_station_locations',
        'optional',
        seed.optional
    )
FROM (
    VALUES
        ('RAW_MATERIAL', 'Raw Material', 'raw_material', NULL, true, false),
        ('ASSEMBLY_WIP', 'Assembly WIP', 'wip', 'ASSEMBLY_01', true, false),
        ('BETWEEN_ASSEMBLY_PACKAGING', 'Between Assembly and Packaging Buffer', 'buffer', NULL, true, false),
        ('PACKAGING_WIP', 'Packaging WIP', 'wip', 'PACKAGING_01', true, false),
        ('FINISHED_GOODS', 'Finished Goods', 'finished_goods', NULL, true, false),
        ('SCRAP_AREA', 'Scrap Area', 'scrap', NULL, true, false),
        ('HOLD_AREA', 'Hold Area', 'hold', NULL, false, true),
        ('REWORK_AREA', 'Rework Area', 'rework', NULL, false, true)
) AS seed(location_code, location_name, location_type, station_code, active, optional)
WHERE NOT EXISTS (
    SELECT 1
    FROM mes.locations existing
    WHERE existing.location_code = seed.location_code
);

INSERT INTO mes.station_location_bindings (
    binding_id,
    station_code,
    role,
    location_code,
    item_scope,
    operation_scope,
    priority,
    active,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata
)
SELECT
    seed.station_code || ':' || seed.role || ':' || seed.location_code,
    seed.station_code,
    seed.role,
    seed.location_code,
    NULL,
    NULL,
    100,
    true,
    'mes_web',
    '003_add_station_locations',
    'seed:station_location_binding:' || seed.station_code || ':' || seed.role || ':' || seed.location_code,
    '{}'::jsonb,
    jsonb_build_object('seed_batch', '003_add_station_locations')
FROM (
    VALUES
        ('ASSEMBLY_01', 'input', 'RAW_MATERIAL'),
        ('ASSEMBLY_01', 'active_wip', 'ASSEMBLY_WIP'),
        ('ASSEMBLY_01', 'output_good', 'BETWEEN_ASSEMBLY_PACKAGING'),
        ('ASSEMBLY_01', 'output_buffer', 'BETWEEN_ASSEMBLY_PACKAGING'),
        ('PACKAGING_01', 'input', 'BETWEEN_ASSEMBLY_PACKAGING'),
        ('PACKAGING_01', 'active_wip', 'PACKAGING_WIP'),
        ('PACKAGING_01', 'output_good', 'FINISHED_GOODS'),
        ('PACKAGING_01', 'output_scrap', 'SCRAP_AREA')
) AS seed(station_code, role, location_code)
WHERE NOT EXISTS (
    SELECT 1
    FROM mes.station_location_bindings existing
    WHERE existing.station_code = seed.station_code
      AND existing.role = seed.role
      AND existing.location_code = seed.location_code
      AND COALESCE(existing.item_scope, '') = ''
      AND COALESCE(existing.operation_scope, '') = ''
      AND existing.active = true
);
