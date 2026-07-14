-- 009_work_order_operation_route_binding.sql
-- Additive immutable sidecar binding between lifecycle operation instances
-- and versioned station-execution route-operation definitions.
-- This migration creates no rows and does not alter existing tables.

BEGIN;

CREATE SCHEMA IF NOT EXISTS mes;

CREATE TABLE IF NOT EXISTS mes.work_order_operation_route_bindings (
    binding_pk BIGSERIAL PRIMARY KEY,
    binding_id TEXT NOT NULL,
    work_order_operation_id UUID NOT NULL,
    route_operation_id TEXT NOT NULL,
    binding_source TEXT NOT NULL,
    bound_by TEXT NOT NULL,
    bound_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mes_work_order_operation_route_bindings_binding_id
        UNIQUE (binding_id),
    CONSTRAINT uq_mes_work_order_operation_route_bindings_operation
        UNIQUE (work_order_operation_id),
    CONSTRAINT fk_mes_work_order_operation_route_bindings_operation
        FOREIGN KEY (work_order_operation_id)
        REFERENCES mes.work_order_operations (work_order_operation_id),
    CONSTRAINT fk_mes_work_order_operation_route_bindings_route_operation
        FOREIGN KEY (route_operation_id)
        REFERENCES mes.route_operations (route_operation_id),
    CONSTRAINT ck_mes_work_order_operation_route_bindings_binding_id_nonblank
        CHECK (btrim(binding_id) <> ''),
    CONSTRAINT ck_mes_work_order_operation_route_bindings_source
        CHECK (binding_source IN ('manual_setup', 'work_order_release')),
    CONSTRAINT ck_mes_work_order_operation_route_bindings_bound_by_nonblank
        CHECK (btrim(bound_by) <> ''),
    CONSTRAINT ck_mes_work_order_operation_route_bindings_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_operation_route_bindings_route_operation
    ON mes.work_order_operation_route_bindings (route_operation_id);

DO $$
DECLARE
    table_oid OID := to_regclass('mes.work_order_operation_route_bindings');
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'mes'
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: schema mes is missing';
    END IF;

    IF table_oid IS NULL THEN
        RAISE EXCEPTION 'Binding schema assertion failed: table is missing';
    END IF;

    IF (
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
    ) <> 9 THEN
        RAISE EXCEPTION 'Binding schema assertion failed: expected 9 columns';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            VALUES
                ('binding_pk', 'bigint', 'int8', 'NO'),
                ('binding_id', 'text', 'text', 'NO'),
                ('work_order_operation_id', 'uuid', 'uuid', 'NO'),
                ('route_operation_id', 'text', 'text', 'NO'),
                ('binding_source', 'text', 'text', 'NO'),
                ('bound_by', 'text', 'text', 'NO'),
                ('bound_at', 'timestamp with time zone', 'timestamptz', 'NO'),
                ('metadata', 'jsonb', 'jsonb', 'NO'),
                ('created_at', 'timestamp with time zone', 'timestamptz', 'NO')
        ) AS expected(column_name, data_type, udt_name, is_nullable)
        LEFT JOIN information_schema.columns actual
          ON actual.table_schema = 'mes'
         AND actual.table_name = 'work_order_operation_route_bindings'
         AND actual.column_name = expected.column_name
        WHERE actual.column_name IS NULL
           OR actual.data_type <> expected.data_type
           OR actual.udt_name <> expected.udt_name
           OR actual.is_nullable <> expected.is_nullable
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: column type or nullability mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
          AND column_name = 'binding_pk'
          AND column_default LIKE 'nextval(%'
          AND pg_get_serial_sequence(
              'mes.work_order_operation_route_bindings',
              'binding_pk'
          ) = 'mes.work_order_operation_route_bindings_binding_pk_seq'
    ) OR EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
          AND column_name IN (
              'binding_id',
              'work_order_operation_id',
              'route_operation_id',
              'binding_source',
              'bound_by'
          )
          AND column_default IS NOT NULL
    ) OR NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
          AND column_name = 'bound_at'
          AND column_default = 'now()'
    ) OR NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
          AND column_name = 'metadata'
          AND column_default = '''{}''::jsonb'
    ) OR NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
          AND column_name = 'created_at'
          AND column_default = 'now()'
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: column default mismatch';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_operation_route_bindings'
          AND column_name IN (
              'active',
              'updated_at',
              'deleted_at',
              'effective_from',
              'effective_to',
              'superseded_by'
          )
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: forbidden lifecycle column found';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid
         AND a.attname = 'binding_pk'
        WHERE c.conrelid = table_oid
          AND c.contype = 'p'
          AND c.conkey = ARRAY[a.attnum]::SMALLINT[]
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: primary key mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid
         AND a.attname = 'binding_id'
        WHERE c.conrelid = table_oid
          AND c.conname = 'uq_mes_work_order_operation_route_bindings_binding_id'
          AND c.contype = 'u'
          AND c.conkey = ARRAY[a.attnum]::SMALLINT[]
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid
         AND a.attname = 'work_order_operation_id'
        WHERE c.conrelid = table_oid
          AND c.conname = 'uq_mes_work_order_operation_route_bindings_operation'
          AND c.contype = 'u'
          AND c.conkey = ARRAY[a.attnum]::SMALLINT[]
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: unique constraint mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_attribute source_column
          ON source_column.attrelid = c.conrelid
         AND source_column.attname = 'work_order_operation_id'
        JOIN pg_attribute target_column
          ON target_column.attrelid = c.confrelid
         AND target_column.attname = 'work_order_operation_id'
        WHERE c.conrelid = table_oid
          AND c.conname = 'fk_mes_work_order_operation_route_bindings_operation'
          AND c.contype = 'f'
          AND c.confrelid = 'mes.work_order_operations'::regclass
          AND c.conkey = ARRAY[source_column.attnum]::SMALLINT[]
          AND c.confkey = ARRAY[target_column.attnum]::SMALLINT[]
          AND c.confdeltype = 'a'
          AND c.confupdtype = 'a'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_attribute source_column
          ON source_column.attrelid = c.conrelid
         AND source_column.attname = 'route_operation_id'
        JOIN pg_attribute target_column
          ON target_column.attrelid = c.confrelid
         AND target_column.attname = 'route_operation_id'
        WHERE c.conrelid = table_oid
          AND c.conname = 'fk_mes_work_order_operation_route_bindings_route_operation'
          AND c.contype = 'f'
          AND c.confrelid = 'mes.route_operations'::regclass
          AND c.conkey = ARRAY[source_column.attnum]::SMALLINT[]
          AND c.confkey = ARRAY[target_column.attnum]::SMALLINT[]
          AND c.confdeltype = 'a'
          AND c.confupdtype = 'a'
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: foreign key mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
    ) <> 9 THEN
        RAISE EXCEPTION 'Binding schema assertion failed: unexpected constraint count';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_operation_route_bindings_source'
          AND c.contype = 'c'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((binding_source=ANY(ARRAY[''manual_setup''::text,''work_order_release''::text])))'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_operation_route_bindings_metadata_object'
          AND c.contype = 'c'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((jsonb_typeof(metadata)=''object''::text))'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_operation_route_bindings_binding_id_nonblank'
          AND c.contype = 'c'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((btrim(binding_id)<>''''::text))'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_operation_route_bindings_bound_by_nonblank'
          AND c.contype = 'c'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((btrim(bound_by)<>''''::text))'
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: check constraint mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_class index_class
          ON index_class.oid = i.indexrelid
        JOIN pg_attribute route_column
          ON route_column.attrelid = i.indrelid
         AND route_column.attname = 'route_operation_id'
        WHERE i.indrelid = table_oid
          AND index_class.relname =
              'ix_mes_work_order_operation_route_bindings_route_operation'
          AND i.indisvalid
          AND NOT i.indisunique
          AND i.indnkeyatts = 1
          AND i.indnatts = 1
          AND route_column.attnum = ANY(i.indkey::SMALLINT[])
          AND i.indpred IS NULL
          AND i.indexprs IS NULL
    ) THEN
        RAISE EXCEPTION 'Binding schema assertion failed: route-operation index mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_index i
        WHERE i.indrelid = table_oid
    ) <> 4 THEN
        RAISE EXCEPTION 'Binding schema assertion failed: unexpected index count';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_index i
        JOIN pg_attribute operation_column
          ON operation_column.attrelid = i.indrelid
         AND operation_column.attname = 'work_order_operation_id'
        WHERE i.indrelid = table_oid
          AND i.indisvalid
          AND i.indnkeyatts = 1
          AND operation_column.attnum = ANY(i.indkey::SMALLINT[])
          AND i.indpred IS NULL
    ) <> 1 THEN
        RAISE EXCEPTION 'Binding schema assertion failed: duplicate lifecycle-operation index';
    END IF;
END
$$;

COMMIT;
