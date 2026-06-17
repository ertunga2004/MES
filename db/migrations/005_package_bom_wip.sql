CREATE TABLE IF NOT EXISTS mes.package_bom_lines (
    bom_line_id bigserial PRIMARY KEY,
    package_stock_code text NOT NULL,
    component_stock_code text NOT NULL,
    required_qty integer NOT NULL CHECK (required_qty > 0),
    color_code text,
    active boolean NOT NULL DEFAULT true,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_to timestamptz,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT package_bom_lines_valid_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_package_bom_lines_active_component
    ON mes.package_bom_lines (package_stock_code, component_stock_code)
    WHERE active;

CREATE TABLE IF NOT EXISTS mes.package_component_wip (
    wip_item_pk bigserial PRIMARY KEY,
    component_stock_code text NOT NULL,
    color_code text,
    source_work_order_id text,
    source_item_id text,
    source_external_ref text,
    quality_status text NOT NULL DEFAULT 'GOOD',
    status text NOT NULL DEFAULT 'available',
    reserved_by_order_id text,
    reserved_by_session_id text,
    consumed_by_package_id text,
    completed_at timestamptz,
    reserved_at timestamptz,
    consumed_at timestamptz,
    source_system text NOT NULL DEFAULT 'mes_web',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT package_component_wip_status_check CHECK (status IN ('available', 'reserved', 'consumed', 'scrapped')),
    CONSTRAINT package_component_wip_quality_check CHECK (quality_status IN ('GOOD', 'REWORK', 'SCRAP', 'UNKNOWN'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_package_component_wip_source_external_ref
    ON mes.package_component_wip (source_external_ref)
    WHERE source_external_ref IS NOT NULL AND btrim(source_external_ref) <> '';

CREATE INDEX IF NOT EXISTS ix_package_component_wip_available
    ON mes.package_component_wip (component_stock_code, status, quality_status);

CREATE INDEX IF NOT EXISTS ix_package_component_wip_session
    ON mes.package_component_wip (reserved_by_session_id);

CREATE TABLE IF NOT EXISTS mes.package_traceability (
    package_trace_pk bigserial PRIMARY KEY,
    package_order_id text NOT NULL,
    package_item_id text,
    package_session_id text,
    package_stock_code text,
    component_stock_code text NOT NULL,
    component_qty integer NOT NULL CHECK (component_qty > 0),
    component_wip_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_item_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    external_ref text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_package_traceability_external_ref
    ON mes.package_traceability (external_ref)
    WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '';

INSERT INTO mes.package_bom_lines (
    package_stock_code,
    component_stock_code,
    required_qty,
    color_code,
    payload,
    metadata
) VALUES
    ('PKG_BLUE_3', 'BLUE_BOX', 3, 'blue', '{"description":"3 blue boxes make 1 blue package"}'::jsonb, '{"seed":"phase2a"}'::jsonb),
    ('PKG_RED_3', 'RED_BOX', 3, 'red', '{"description":"3 red boxes make 1 red package"}'::jsonb, '{"seed":"phase2a"}'::jsonb),
    ('PKG_YELLOW_3', 'YELLOW_BOX', 3, 'yellow', '{"description":"3 yellow boxes make 1 yellow package"}'::jsonb, '{"seed":"phase2a"}'::jsonb),
    ('PKT-BLUE', 'BLUE_BOX', 3, 'blue', '{"description":"Legacy blue package code compatibility"}'::jsonb, '{"seed":"phase2a","legacy":true}'::jsonb),
    ('PKT-RED', 'RED_BOX', 3, 'red', '{"description":"Legacy red package code compatibility"}'::jsonb, '{"seed":"phase2a","legacy":true}'::jsonb),
    ('PKT-YELLOW', 'YELLOW_BOX', 3, 'yellow', '{"description":"Legacy yellow package code compatibility"}'::jsonb, '{"seed":"phase2a","legacy":true}'::jsonb)
ON CONFLICT (package_stock_code, component_stock_code) WHERE active
DO UPDATE SET
    required_qty = EXCLUDED.required_qty,
    color_code = EXCLUDED.color_code,
    payload = EXCLUDED.payload,
    metadata = mes.package_bom_lines.metadata || EXCLUDED.metadata,
    updated_at = now();
