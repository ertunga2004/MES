-- DRAFT ONLY. DO NOT APPLY TO RUNTIME DATABASE.
-- This file is not a production migration.
-- It does not change the existing MES Web runtime, Docker setup, or mes schema.
-- Purpose: document the proposed MESQL shared schema for review.

CREATE SCHEMA IF NOT EXISTS mesql_master;
CREATE SCHEMA IF NOT EXISTS mesql_manufacturing;

CREATE TABLE IF NOT EXISTS mesql_master.products (
    product_id text PRIMARY KEY,
    product_code text NOT NULL,
    product_name text,
    product_type text,
    unit_code text,
    source_system text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_products_product_code UNIQUE (product_code),
    CONSTRAINT ck_mesql_products_product_code_not_blank CHECK (btrim(product_code) <> '')
);

COMMENT ON COLUMN mesql_master.products.product_code IS
    'Known F-ERP stock/product label context: lblMTM00_CODE.';
COMMENT ON COLUMN mesql_master.products.product_name IS
    'Known F-ERP stock/product label context: lblMTM00_NAME.';
COMMENT ON COLUMN mesql_master.products.product_type IS
    'Known F-ERP stock type label context: lblMTMT0_CODE.';
COMMENT ON COLUMN mesql_master.products.unit_code IS
    'Known F-ERP unit label context: lblMUNT0_CODE.';

CREATE TABLE IF NOT EXISTS mesql_master.product_revisions (
    product_revision_id text PRIMARY KEY,
    product_id text NOT NULL REFERENCES mesql_master.products (product_id),
    revision_code text NOT NULL,
    release_status text NOT NULL DEFAULT 'DRAFT',
    valid_from timestamptz,
    valid_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_product_revisions_product_revision
        UNIQUE (product_id, revision_code),
    CONSTRAINT ck_mesql_product_revisions_revision_not_blank
        CHECK (btrim(revision_code) <> ''),
    CONSTRAINT ck_mesql_product_revisions_release_status
        CHECK (release_status IN (
            'DRAFT',
            'IN_REVIEW',
            'APPROVED',
            'RELEASED',
            'ARCHIVED',
            'REJECTED',
            'PENDING'
        )),
    CONSTRAINT ck_mesql_product_revisions_valid_window
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from)
);

CREATE TABLE IF NOT EXISTS mesql_master.components (
    component_id text PRIMARY KEY,
    component_code text NOT NULL,
    component_name text,
    component_type text,
    unit_code text,
    source_system text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_components_component_code UNIQUE (component_code),
    CONSTRAINT ck_mesql_components_component_code_not_blank
        CHECK (btrim(component_code) <> '')
);

COMMENT ON COLUMN mesql_master.components.component_code IS
    'Known F-ERP stock/component label context: lblMTM00_CODE.';
COMMENT ON COLUMN mesql_master.components.component_name IS
    'Known F-ERP stock/component label context: lblMTM00_NAME.';
COMMENT ON COLUMN mesql_master.components.component_type IS
    'Known F-ERP stock type label context: lblMTMT0_CODE.';
COMMENT ON COLUMN mesql_master.components.unit_code IS
    'Known F-ERP unit label context: lblMUNT0_CODE.';

CREATE TABLE IF NOT EXISTS mesql_manufacturing.mbom_headers (
    mbom_id text PRIMARY KEY,
    product_revision_id text NOT NULL
        REFERENCES mesql_master.product_revisions (product_revision_id),
    mbom_revision text NOT NULL,
    plant_code text NOT NULL,
    release_status text NOT NULL DEFAULT 'DRAFT',
    valid_from timestamptz,
    valid_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_mbom_headers_revision
        UNIQUE (product_revision_id, mbom_revision, plant_code),
    CONSTRAINT ck_mesql_mbom_headers_release_status
        CHECK (release_status IN (
            'DRAFT',
            'IN_REVIEW',
            'APPROVED',
            'RELEASED',
            'ARCHIVED',
            'REJECTED',
            'PENDING'
        )),
    CONSTRAINT ck_mesql_mbom_headers_valid_window
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_mesql_mbom_headers_plant_not_blank
        CHECK (btrim(plant_code) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesql_mbom_headers_active_released
    ON mesql_manufacturing.mbom_headers (product_revision_id, plant_code)
    WHERE release_status = 'RELEASED' AND valid_to IS NULL;

CREATE TABLE IF NOT EXISTS mesql_manufacturing.mbom_lines (
    mbom_line_id text PRIMARY KEY,
    mbom_id text NOT NULL
        REFERENCES mesql_manufacturing.mbom_headers (mbom_id),
    component_id text NOT NULL
        REFERENCES mesql_master.components (component_id),
    required_quantity numeric NOT NULL,
    unit_code text,
    line_no integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_mesql_mbom_lines_required_quantity_positive
        CHECK (required_quantity > 0),
    CONSTRAINT ck_mesql_mbom_lines_line_no_positive
        CHECK (line_no IS NULL OR line_no > 0)
);

CREATE TABLE IF NOT EXISTS mesql_manufacturing.bop_headers (
    bop_id text PRIMARY KEY,
    product_revision_id text NOT NULL
        REFERENCES mesql_master.product_revisions (product_revision_id),
    bop_revision text NOT NULL,
    plant_code text NOT NULL,
    release_status text NOT NULL DEFAULT 'DRAFT',
    valid_from timestamptz,
    valid_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_bop_headers_revision
        UNIQUE (product_revision_id, bop_revision, plant_code),
    CONSTRAINT ck_mesql_bop_headers_release_status
        CHECK (release_status IN (
            'DRAFT',
            'IN_REVIEW',
            'APPROVED',
            'RELEASED',
            'ARCHIVED',
            'REJECTED',
            'PENDING'
        )),
    CONSTRAINT ck_mesql_bop_headers_valid_window
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_mesql_bop_headers_plant_not_blank
        CHECK (btrim(plant_code) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesql_bop_headers_active_released
    ON mesql_manufacturing.bop_headers (product_revision_id, plant_code)
    WHERE release_status = 'RELEASED' AND valid_to IS NULL;

CREATE TABLE IF NOT EXISTS mesql_manufacturing.bop_operations (
    bop_operation_id text PRIMARY KEY,
    bop_id text NOT NULL
        REFERENCES mesql_manufacturing.bop_headers (bop_id),
    operation_sequence integer NOT NULL,
    operation_code text,
    operation_name text,
    setup_time_seconds numeric,
    cycle_time_seconds numeric,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_bop_operations_sequence
        UNIQUE (bop_id, operation_sequence),
    CONSTRAINT ck_mesql_bop_operations_sequence_positive
        CHECK (operation_sequence > 0),
    CONSTRAINT ck_mesql_bop_operations_setup_non_negative
        CHECK (setup_time_seconds IS NULL OR setup_time_seconds >= 0),
    CONSTRAINT ck_mesql_bop_operations_cycle_positive
        CHECK (cycle_time_seconds IS NULL OR cycle_time_seconds > 0)
);

COMMENT ON COLUMN mesql_manufacturing.bop_operations.operation_code IS
    'Known F-ERP operation label context: lblMFWO0_CODE.';
COMMENT ON COLUMN mesql_manufacturing.bop_operations.setup_time_seconds IS
    'Known F-ERP setup time label context: lblMMFB4_SETUP_TIME.';
COMMENT ON COLUMN mesql_manufacturing.bop_operations.cycle_time_seconds IS
    'Known F-ERP cycle time label context: lblMMFB4_TIME.';

CREATE TABLE IF NOT EXISTS mesql_manufacturing.operation_station_mapping (
    mapping_id text PRIMARY KEY,
    bop_operation_id text NOT NULL
        REFERENCES mesql_manufacturing.bop_operations (bop_operation_id),
    station_code text,
    work_center_code text,
    mapping_status text NOT NULL DEFAULT 'DRAFT',
    validation_level text NOT NULL DEFAULT 'PASS',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_mesql_operation_station_mapping_status
        CHECK (mapping_status IN (
            'DRAFT',
            'IN_REVIEW',
            'APPROVED',
            'RELEASED',
            'ARCHIVED',
            'REJECTED',
            'PENDING'
        )),
    CONSTRAINT ck_mesql_operation_station_mapping_validation_level
        CHECK (validation_level IN ('WARN', 'HOLD', 'FAIL', 'PASS'))
);

COMMENT ON TABLE mesql_manufacturing.operation_station_mapping IS
    'Canonical source for operation/station mapping. mes.station_queue remains daily runtime queue, not master data.';
COMMENT ON COLUMN mesql_manufacturing.operation_station_mapping.work_center_code IS
    'Known F-ERP work center label context: lblMFW00_CODE.';
COMMENT ON COLUMN mesql_manufacturing.operation_station_mapping.validation_level IS
    'Missing mapping defaults: DRAFT/IN_REVIEW=WARN, APPROVED=HOLD, RELEASED=FAIL. Enforce released operation mapping with validation job/trigger, not SQL CHECK.';

CREATE TABLE IF NOT EXISTS mesql_manufacturing.package_bom_headers (
    package_bom_id text PRIMARY KEY,
    package_product_revision_id text NOT NULL
        REFERENCES mesql_master.product_revisions (product_revision_id),
    package_bom_revision text NOT NULL,
    plant_code text NOT NULL,
    release_status text NOT NULL DEFAULT 'DRAFT',
    valid_from timestamptz,
    valid_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesql_package_bom_headers_revision
        UNIQUE (
            package_product_revision_id,
            package_bom_revision,
            plant_code
        ),
    CONSTRAINT ck_mesql_package_bom_headers_release_status
        CHECK (release_status IN (
            'DRAFT',
            'IN_REVIEW',
            'APPROVED',
            'RELEASED',
            'ARCHIVED',
            'REJECTED',
            'PENDING'
        )),
    CONSTRAINT ck_mesql_package_bom_headers_valid_window
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_mesql_package_bom_headers_plant_not_blank
        CHECK (btrim(plant_code) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesql_package_bom_headers_active_released
    ON mesql_manufacturing.package_bom_headers (
        package_product_revision_id,
        plant_code
    )
    WHERE release_status = 'RELEASED' AND valid_to IS NULL;

CREATE TABLE IF NOT EXISTS mesql_manufacturing.package_bom_lines (
    package_bom_line_id text PRIMARY KEY,
    package_bom_id text NOT NULL
        REFERENCES mesql_manufacturing.package_bom_headers (package_bom_id),
    component_id text NOT NULL
        REFERENCES mesql_master.components (component_id),
    required_quantity numeric NOT NULL,
    unit_code text,
    line_no integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_mesql_package_bom_lines_required_quantity_positive
        CHECK (required_quantity > 0),
    CONSTRAINT ck_mesql_package_bom_lines_line_no_positive
        CHECK (line_no IS NULL OR line_no > 0)
);

-- Cross-table validation note:
-- RELEASED BOP operations must have a valid station mapping before MES
-- distribution. This cannot be expressed as a simple SQL CHECK constraint
-- because it spans bop_headers, bop_operations, and operation_station_mapping.
-- Use importer validation, a validation job, or a trigger in a future reviewed
-- production migration.
