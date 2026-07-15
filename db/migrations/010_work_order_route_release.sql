-- 010_work_order_route_release.sql
-- Additive immutable route-release snapshot for one work order.
-- This migration creates no release, lifecycle, binding, queue, or backfill row.

BEGIN;

CREATE SCHEMA IF NOT EXISTS mes;

DO $$
DECLARE
    parent_oid OID := to_regclass('mes.process_routes');
    route_id_attnum SMALLINT;
    route_code_attnum SMALLINT;
    version_attnum SMALLINT;
BEGIN
    IF parent_oid IS NULL THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: parent table mes.process_routes is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class
        WHERE oid = parent_oid
          AND relkind = 'r'
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: parent mes.process_routes is not an ordinary table';
    END IF;

    SELECT attnum
    INTO route_id_attnum
    FROM pg_attribute
    WHERE attrelid = parent_oid
      AND attname = 'route_id'
      AND NOT attisdropped;

    SELECT attnum
    INTO route_code_attnum
    FROM pg_attribute
    WHERE attrelid = parent_oid
      AND attname = 'route_code'
      AND NOT attisdropped;

    SELECT attnum
    INTO version_attnum
    FROM pg_attribute
    WHERE attrelid = parent_oid
      AND attname = 'version'
      AND NOT attisdropped;

    IF route_id_attnum IS NULL
       OR route_code_attnum IS NULL
       OR version_attnum IS NULL THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: parent route identity columns are missing';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = parent_oid
          AND conname = 'uq_mes_process_routes_identity_snapshot'
    ) THEN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            WHERE c.conrelid = parent_oid
              AND c.conname = 'uq_mes_process_routes_identity_snapshot'
              AND c.contype = 'u'
              AND c.conkey = ARRAY[
                  route_id_attnum,
                  route_code_attnum,
                  version_attnum
              ]::SMALLINT[]
              AND NOT c.condeferrable
              AND NOT c.condeferred
        ) THEN
            RAISE EXCEPTION
                'Work-order route release schema assertion failed: parent route identity constraint mismatch';
        END IF;
    ELSE
        IF to_regclass('mes.uq_mes_process_routes_identity_snapshot') IS NOT NULL THEN
            RAISE EXCEPTION
                'Work-order route release schema assertion failed: parent route identity constraint name is occupied';
        END IF;

        EXECUTE
            'ALTER TABLE mes.process_routes '
            'ADD CONSTRAINT uq_mes_process_routes_identity_snapshot '
            'UNIQUE (route_id, route_code, version)';
    END IF;
END
$$;

DO $$
DECLARE
    table_oid OID := to_regclass('mes.work_order_route_releases');
BEGIN
    IF table_oid IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_class
            WHERE oid = table_oid
              AND relkind = 'r'
        ) THEN
            RAISE EXCEPTION
                'Work-order route release schema assertion failed: existing release relation is not an ordinary table';
        END IF;

        IF (
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'mes'
              AND table_name = 'work_order_route_releases'
        ) <> 14 OR EXISTS (
            SELECT 1
            FROM (
                VALUES
                    ('release_pk'),
                    ('release_id'),
                    ('order_id'),
                    ('process_route_id'),
                    ('route_code'),
                    ('route_version'),
                    ('release_mode'),
                    ('release_source'),
                    ('released_by'),
                    ('released_at'),
                    ('route_operation_count'),
                    ('operation_set_digest'),
                    ('metadata'),
                    ('created_at')
            ) AS expected(column_name)
            LEFT JOIN information_schema.columns actual
              ON actual.table_schema = 'mes'
             AND actual.table_name = 'work_order_route_releases'
             AND actual.column_name = expected.column_name
            WHERE actual.column_name IS NULL
        ) THEN
            RAISE EXCEPTION
                'Work-order route release schema assertion failed: existing release column set mismatch';
        END IF;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS mes.work_order_route_releases (
    release_pk BIGSERIAL NOT NULL,
    release_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    process_route_id TEXT NOT NULL,
    route_code TEXT NOT NULL,
    route_version INTEGER NOT NULL,
    release_mode TEXT NOT NULL,
    release_source TEXT NOT NULL,
    released_by TEXT NOT NULL,
    released_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    route_operation_count INTEGER NOT NULL,
    operation_set_digest TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_mes_work_order_route_releases
        PRIMARY KEY (release_pk),
    CONSTRAINT uq_mes_work_order_route_releases_release_id
        UNIQUE (release_id),
    CONSTRAINT uq_mes_work_order_route_releases_order_id
        UNIQUE (order_id),
    CONSTRAINT fk_mes_work_order_route_releases_order
        FOREIGN KEY (order_id)
        REFERENCES mes.work_orders (order_id),
    CONSTRAINT fk_mes_work_order_route_releases_route_identity
        FOREIGN KEY (process_route_id, route_code, route_version)
        REFERENCES mes.process_routes (route_id, route_code, version),
    CONSTRAINT ck_mes_work_order_route_releases_release_id_nonblank
        CHECK (btrim(release_id) <> ''),
    CONSTRAINT ck_mes_work_order_route_releases_process_route_id_nonblank
        CHECK (btrim(process_route_id) <> ''),
    CONSTRAINT ck_mes_work_order_route_releases_route_code_nonblank
        CHECK (btrim(route_code) <> ''),
    CONSTRAINT ck_mes_work_order_route_releases_route_version_positive
        CHECK (route_version > 0),
    CONSTRAINT ck_mes_work_order_route_releases_mode
        CHECK (
            release_mode IN (
                'route_generated',
                'explicit_existing_operation_mapping'
            )
        ),
    CONSTRAINT ck_mes_work_order_route_releases_source
        CHECK (release_source = 'local_planning'),
    CONSTRAINT ck_mes_work_order_route_releases_released_by_nonblank
        CHECK (btrim(released_by) <> ''),
    CONSTRAINT ck_mes_work_order_route_releases_operation_count_positive
        CHECK (route_operation_count > 0),
    CONSTRAINT ck_mes_work_order_route_releases_digest
        CHECK (operation_set_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_mes_work_order_route_releases_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_mes_work_order_route_releases_route_version
    ON mes.work_order_route_releases (
        route_code,
        route_version,
        released_at DESC
    );

CREATE INDEX IF NOT EXISTS ix_mes_work_order_route_releases_released_at
    ON mes.work_order_route_releases (released_at DESC);

DO $$
DECLARE
    table_oid OID := to_regclass('mes.work_order_route_releases');
    parent_oid OID := to_regclass('mes.process_routes');
    work_orders_oid OID := to_regclass('mes.work_orders');
    release_pk_attnum SMALLINT;
    release_id_attnum SMALLINT;
    order_id_attnum SMALLINT;
    process_route_id_attnum SMALLINT;
    route_code_attnum SMALLINT;
    route_version_attnum SMALLINT;
    released_at_attnum SMALLINT;
    parent_route_id_attnum SMALLINT;
    parent_route_code_attnum SMALLINT;
    parent_version_attnum SMALLINT;
    parent_order_id_attnum SMALLINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'mes'
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: schema mes is missing';
    END IF;

    IF table_oid IS NULL THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: release table is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class
        WHERE oid = table_oid
          AND relkind = 'r'
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: release relation is not an ordinary table';
    END IF;

    IF parent_oid IS NULL OR work_orders_oid IS NULL THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: required parent table is missing';
    END IF;

    IF (
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
    ) <> 14 THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: expected 14 columns';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            VALUES
                (1, 'release_pk', 'bigint', 'int8', 'NO'),
                (2, 'release_id', 'text', 'text', 'NO'),
                (3, 'order_id', 'text', 'text', 'NO'),
                (4, 'process_route_id', 'text', 'text', 'NO'),
                (5, 'route_code', 'text', 'text', 'NO'),
                (6, 'route_version', 'integer', 'int4', 'NO'),
                (7, 'release_mode', 'text', 'text', 'NO'),
                (8, 'release_source', 'text', 'text', 'NO'),
                (9, 'released_by', 'text', 'text', 'NO'),
                (10, 'released_at', 'timestamp with time zone', 'timestamptz', 'NO'),
                (11, 'route_operation_count', 'integer', 'int4', 'NO'),
                (12, 'operation_set_digest', 'text', 'text', 'NO'),
                (13, 'metadata', 'jsonb', 'jsonb', 'NO'),
                (14, 'created_at', 'timestamp with time zone', 'timestamptz', 'NO')
        ) AS expected(
            ordinal_position,
            column_name,
            data_type,
            udt_name,
            is_nullable
        )
        LEFT JOIN information_schema.columns actual
          ON actual.table_schema = 'mes'
         AND actual.table_name = 'work_order_route_releases'
         AND actual.column_name = expected.column_name
        WHERE actual.column_name IS NULL
           OR actual.ordinal_position <> expected.ordinal_position
           OR actual.data_type <> expected.data_type
           OR actual.udt_name <> expected.udt_name
           OR actual.is_nullable <> expected.is_nullable
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: column order, type, or nullability mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
          AND column_name = 'release_pk'
          AND column_default LIKE 'nextval(%'
          AND pg_get_serial_sequence(
              'mes.work_order_route_releases',
              'release_pk'
          ) = 'mes.work_order_route_releases_release_pk_seq'
    ) OR EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
          AND column_name IN (
              'release_id',
              'order_id',
              'process_route_id',
              'route_code',
              'route_version',
              'release_mode',
              'release_source',
              'released_by',
              'route_operation_count',
              'operation_set_digest'
          )
          AND column_default IS NOT NULL
    ) OR NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
          AND column_name = 'released_at'
          AND column_default = 'now()'
    ) OR NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
          AND column_name = 'metadata'
          AND column_default = '''{}''::jsonb'
    ) OR NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
          AND column_name = 'created_at'
          AND column_default = 'now()'
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: column default mismatch';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'mes'
          AND table_name = 'work_order_route_releases'
          AND column_name IN (
              'active',
              'updated_at',
              'deleted_at',
              'effective_from',
              'effective_to',
              'superseded_by',
              'cancelled_at'
          )
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: forbidden mutable column found';
    END IF;

    SELECT attnum INTO release_pk_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'release_pk' AND NOT attisdropped;

    SELECT attnum INTO release_id_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'release_id' AND NOT attisdropped;

    SELECT attnum INTO order_id_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'order_id' AND NOT attisdropped;

    SELECT attnum INTO process_route_id_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'process_route_id' AND NOT attisdropped;

    SELECT attnum INTO route_code_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'route_code' AND NOT attisdropped;

    SELECT attnum INTO route_version_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'route_version' AND NOT attisdropped;

    SELECT attnum INTO released_at_attnum
    FROM pg_attribute
    WHERE attrelid = table_oid AND attname = 'released_at' AND NOT attisdropped;

    SELECT attnum INTO parent_route_id_attnum
    FROM pg_attribute
    WHERE attrelid = parent_oid AND attname = 'route_id' AND NOT attisdropped;

    SELECT attnum INTO parent_route_code_attnum
    FROM pg_attribute
    WHERE attrelid = parent_oid AND attname = 'route_code' AND NOT attisdropped;

    SELECT attnum INTO parent_version_attnum
    FROM pg_attribute
    WHERE attrelid = parent_oid AND attname = 'version' AND NOT attisdropped;

    SELECT attnum INTO parent_order_id_attnum
    FROM pg_attribute
    WHERE attrelid = work_orders_oid AND attname = 'order_id' AND NOT attisdropped;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = parent_oid
          AND c.conname = 'uq_mes_process_routes_identity_snapshot'
          AND c.contype = 'u'
          AND c.conkey = ARRAY[
              parent_route_id_attnum,
              parent_route_code_attnum,
              parent_version_attnum
          ]::SMALLINT[]
          AND NOT c.condeferrable
          AND NOT c.condeferred
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: parent route identity constraint mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
    ) <> 15 THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: expected 15 constraints';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            VALUES
                ('pk_mes_work_order_route_releases', 'p'),
                ('uq_mes_work_order_route_releases_release_id', 'u'),
                ('uq_mes_work_order_route_releases_order_id', 'u'),
                ('fk_mes_work_order_route_releases_order', 'f'),
                ('fk_mes_work_order_route_releases_route_identity', 'f'),
                ('ck_mes_work_order_route_releases_release_id_nonblank', 'c'),
                ('ck_mes_work_order_route_releases_process_route_id_nonblank', 'c'),
                ('ck_mes_work_order_route_releases_route_code_nonblank', 'c'),
                ('ck_mes_work_order_route_releases_route_version_positive', 'c'),
                ('ck_mes_work_order_route_releases_mode', 'c'),
                ('ck_mes_work_order_route_releases_source', 'c'),
                ('ck_mes_work_order_route_releases_released_by_nonblank', 'c'),
                ('ck_mes_work_order_route_releases_operation_count_positive', 'c'),
                ('ck_mes_work_order_route_releases_digest', 'c'),
                ('ck_mes_work_order_route_releases_metadata_object', 'c')
        ) AS expected(conname, contype)
        LEFT JOIN pg_constraint actual
          ON actual.conrelid = table_oid
         AND actual.conname = expected.conname
        WHERE actual.oid IS NULL
           OR actual.contype <> expected.contype::"char"
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: constraint name or type mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'pk_mes_work_order_route_releases'
          AND c.contype = 'p'
          AND c.conkey = ARRAY[release_pk_attnum]::SMALLINT[]
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'uq_mes_work_order_route_releases_release_id'
          AND c.contype = 'u'
          AND c.conkey = ARRAY[release_id_attnum]::SMALLINT[]
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'uq_mes_work_order_route_releases_order_id'
          AND c.contype = 'u'
          AND c.conkey = ARRAY[order_id_attnum]::SMALLINT[]
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: primary or unique key mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'fk_mes_work_order_route_releases_order'
          AND c.contype = 'f'
          AND c.confrelid = work_orders_oid
          AND c.conkey = ARRAY[order_id_attnum]::SMALLINT[]
          AND c.confkey = ARRAY[parent_order_id_attnum]::SMALLINT[]
          AND c.confupdtype = 'a'
          AND c.confdeltype = 'a'
          AND c.confmatchtype = 's'
          AND NOT c.condeferrable
          AND NOT c.condeferred
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'fk_mes_work_order_route_releases_route_identity'
          AND c.contype = 'f'
          AND c.confrelid = parent_oid
          AND c.conkey = ARRAY[
              process_route_id_attnum,
              route_code_attnum,
              route_version_attnum
          ]::SMALLINT[]
          AND c.confkey = ARRAY[
              parent_route_id_attnum,
              parent_route_code_attnum,
              parent_version_attnum
          ]::SMALLINT[]
          AND c.confupdtype = 'a'
          AND c.confdeltype = 'a'
          AND c.confmatchtype = 's'
          AND NOT c.condeferrable
          AND NOT c.condeferred
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: foreign key mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_release_id_nonblank'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((btrim(release_id)<>''''::text))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_process_route_id_nonblank'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((btrim(process_route_id)<>''''::text))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_route_code_nonblank'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((btrim(route_code)<>''''::text))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_route_version_positive'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((route_version>0))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_mode'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((release_mode=ANY(ARRAY[''route_generated''::text,''explicit_existing_operation_mapping''::text])))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_source'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((release_source=''local_planning''::text))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_released_by_nonblank'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((btrim(released_by)<>''''::text))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_operation_count_positive'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((route_operation_count>0))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_digest'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((operation_set_digest~''^[0-9a-f]{64}$''::text))'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = table_oid
          AND c.conname = 'ck_mes_work_order_route_releases_metadata_object'
          AND regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g') =
              'CHECK((jsonb_typeof(metadata)=''object''::text))'
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: check constraint mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_index i
        WHERE i.indrelid = table_oid
    ) <> 5 THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: expected 5 indexes';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            VALUES
                ('pk_mes_work_order_route_releases'),
                ('uq_mes_work_order_route_releases_release_id'),
                ('uq_mes_work_order_route_releases_order_id'),
                ('ix_mes_work_order_route_releases_route_version'),
                ('ix_mes_work_order_route_releases_released_at')
        ) AS expected(index_name)
        LEFT JOIN pg_class index_class
          ON index_class.relnamespace = 'mes'::regnamespace
         AND index_class.relname = expected.index_name
        LEFT JOIN pg_index i
          ON i.indexrelid = index_class.oid
         AND i.indrelid = table_oid
        WHERE i.indexrelid IS NULL
           OR NOT i.indisvalid
           OR NOT i.indisready
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: index name or validity mismatch';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_class index_class ON index_class.oid = i.indexrelid
        WHERE i.indrelid = table_oid
          AND index_class.relname = 'ix_mes_work_order_route_releases_route_version'
          AND NOT i.indisunique
          AND i.indnkeyatts = 3
          AND i.indnatts = 3
          AND i.indpred IS NULL
          AND i.indexprs IS NULL
          AND regexp_replace(pg_get_indexdef(i.indexrelid), '\s+', '', 'g') =
              'CREATEINDEXix_mes_work_order_route_releases_route_versionONmes.work_order_route_releasesUSINGbtree(route_code,route_version,released_atDESC)'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_class index_class ON index_class.oid = i.indexrelid
        WHERE i.indrelid = table_oid
          AND index_class.relname = 'ix_mes_work_order_route_releases_released_at'
          AND NOT i.indisunique
          AND i.indnkeyatts = 1
          AND i.indnatts = 1
          AND i.indpred IS NULL
          AND i.indexprs IS NULL
          AND regexp_replace(pg_get_indexdef(i.indexrelid), '\s+', '', 'g') =
              'CREATEINDEXix_mes_work_order_route_releases_released_atONmes.work_order_route_releasesUSINGbtree(released_atDESC)'
    ) THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: additional index definition mismatch';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_index i
        JOIN pg_attribute route_code_column
          ON route_code_column.attrelid = i.indrelid
         AND route_code_column.attname = 'route_code'
        JOIN pg_attribute route_version_column
          ON route_version_column.attrelid = i.indrelid
         AND route_version_column.attname = 'route_version'
        JOIN pg_attribute released_at_column
          ON released_at_column.attrelid = i.indrelid
         AND released_at_column.attname = 'released_at'
        WHERE i.indrelid = table_oid
          AND i.indkey::TEXT = concat_ws(
              ' ',
              route_code_column.attnum,
              route_version_column.attnum,
              released_at_column.attnum
          )
          AND i.indpred IS NULL
    ) <> 1 OR (
        SELECT count(*)
        FROM pg_index i
        WHERE i.indrelid = table_oid
          AND i.indkey::TEXT = released_at_attnum::TEXT
          AND i.indpred IS NULL
    ) <> 1 THEN
        RAISE EXCEPTION
            'Work-order route release schema assertion failed: duplicate or missing additional index';
    END IF;
END
$$;

COMMIT;
