--
-- PostgreSQL database dump
--

\restrict M6SpoTt2WMNM1aqwVuTsxImm1RmHMUPKwzMHpyfag1BoXPEjDZjoGZBaEQSj1Cf

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: mes; Type: SCHEMA; Schema: -; Owner: mes
--

CREATE SCHEMA mes;


ALTER SCHEMA mes OWNER TO mes;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: device_sessions; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.device_sessions (
    device_session_pk bigint NOT NULL,
    device_id text NOT NULL,
    device_role text,
    operator_id text,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.device_sessions OWNER TO mes;

--
-- Name: device_sessions_device_session_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.device_sessions_device_session_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.device_sessions_device_session_pk_seq OWNER TO mes;

--
-- Name: device_sessions_device_session_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.device_sessions_device_session_pk_seq OWNED BY mes.device_sessions.device_session_pk;


--
-- Name: downtime_events; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.downtime_events (
    downtime_pk bigint NOT NULL,
    fault_id text,
    status_code text,
    fault_type_code text,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.downtime_events OWNER TO mes;

--
-- Name: downtime_events_downtime_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.downtime_events_downtime_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.downtime_events_downtime_pk_seq OWNER TO mes;

--
-- Name: downtime_events_downtime_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.downtime_events_downtime_pk_seq OWNED BY mes.downtime_events.downtime_pk;


--
-- Name: error_types; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.error_types (
    error_type_pk bigint NOT NULL,
    error_type_id text,
    error_type_code text,
    error_category text,
    error_reason text,
    default_station_id text,
    active boolean DEFAULT true NOT NULL,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.error_types OWNER TO mes;

--
-- Name: error_types_error_type_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.error_types_error_type_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.error_types_error_type_pk_seq OWNER TO mes;

--
-- Name: error_types_error_type_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.error_types_error_type_pk_seq OWNED BY mes.error_types.error_type_pk;


--
-- Name: ferp_export_outbox; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.ferp_export_outbox (
    export_pk bigint NOT NULL,
    export_id text,
    order_id text,
    export_type text,
    status text DEFAULT 'pending'::text NOT NULL,
    artifact_path text,
    created_for_export_at timestamp with time zone,
    exported_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.ferp_export_outbox OWNER TO mes;

--
-- Name: ferp_export_outbox_export_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.ferp_export_outbox_export_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.ferp_export_outbox_export_pk_seq OWNER TO mes;

--
-- Name: ferp_export_outbox_export_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.ferp_export_outbox_export_pk_seq OWNED BY mes.ferp_export_outbox.export_pk;


--
-- Name: ferp_import_batches; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.ferp_import_batches (
    import_batch_pk bigint NOT NULL,
    batch_id text,
    source_file text,
    imported_at timestamp with time zone,
    status text,
    source_system text DEFAULT 'ferp'::text NOT NULL,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.ferp_import_batches OWNER TO mes;

--
-- Name: ferp_import_batches_import_batch_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.ferp_import_batches_import_batch_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.ferp_import_batches_import_batch_pk_seq OWNER TO mes;

--
-- Name: ferp_import_batches_import_batch_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.ferp_import_batches_import_batch_pk_seq OWNED BY mes.ferp_import_batches.import_batch_pk;


--
-- Name: maintenance_records; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.maintenance_records (
    maintenance_pk bigint NOT NULL,
    maintenance_row_key text,
    session_id text,
    phase_code text,
    step_code text,
    status text,
    recorded_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.maintenance_records OWNER TO mes;

--
-- Name: maintenance_records_maintenance_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.maintenance_records_maintenance_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.maintenance_records_maintenance_pk_seq OWNER TO mes;

--
-- Name: maintenance_records_maintenance_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.maintenance_records_maintenance_pk_seq OWNED BY mes.maintenance_records.maintenance_pk;


--
-- Name: maintenance_steps; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.maintenance_steps (
    maintenance_step_pk bigint NOT NULL,
    phase_code text,
    step_code text,
    step_label text,
    required boolean DEFAULT true NOT NULL,
    sort_order integer,
    active boolean DEFAULT true NOT NULL,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.maintenance_steps OWNER TO mes;

--
-- Name: maintenance_steps_maintenance_step_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.maintenance_steps_maintenance_step_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.maintenance_steps_maintenance_step_pk_seq OWNER TO mes;

--
-- Name: maintenance_steps_maintenance_step_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.maintenance_steps_maintenance_step_pk_seq OWNED BY mes.maintenance_steps.maintenance_step_pk;


--
-- Name: oee_snapshots; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.oee_snapshots (
    snapshot_pk bigint NOT NULL,
    snapshot_at timestamp with time zone NOT NULL,
    shift_id text,
    availability numeric(8,4),
    performance numeric(8,4),
    quality numeric(8,4),
    oee numeric(8,4),
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.oee_snapshots OWNER TO mes;

--
-- Name: oee_snapshots_snapshot_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.oee_snapshots_snapshot_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.oee_snapshots_snapshot_pk_seq OWNER TO mes;

--
-- Name: oee_snapshots_snapshot_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.oee_snapshots_snapshot_pk_seq OWNED BY mes.oee_snapshots.snapshot_pk;


--
-- Name: operators; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.operators (
    operator_pk bigint NOT NULL,
    operator_id text,
    operator_code text,
    operator_name text,
    active boolean DEFAULT true NOT NULL,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.operators OWNER TO mes;

--
-- Name: operators_operator_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.operators_operator_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.operators_operator_pk_seq OWNER TO mes;

--
-- Name: operators_operator_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.operators_operator_pk_seq OWNED BY mes.operators.operator_pk;


--
-- Name: production_completions; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.production_completions (
    completion_pk bigint NOT NULL,
    order_id text,
    item_id text,
    classification text,
    completed_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.production_completions OWNER TO mes;

--
-- Name: production_completions_completion_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.production_completions_completion_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.production_completions_completion_pk_seq OWNER TO mes;

--
-- Name: production_completions_completion_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.production_completions_completion_pk_seq OWNED BY mes.production_completions.completion_pk;


--
-- Name: quality_overrides; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.quality_overrides (
    quality_override_pk bigint NOT NULL,
    item_id text,
    classification text,
    operator_id text,
    recorded_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.quality_overrides OWNER TO mes;

--
-- Name: quality_overrides_quality_override_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.quality_overrides_quality_override_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.quality_overrides_quality_override_pk_seq OWNER TO mes;

--
-- Name: quality_overrides_quality_override_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.quality_overrides_quality_override_pk_seq OWNED BY mes.quality_overrides.quality_override_pk;


--
-- Name: stations; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.stations (
    station_pk bigint NOT NULL,
    station_id text,
    station_code text,
    station_name text,
    line_id text,
    active boolean DEFAULT true NOT NULL,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.stations OWNER TO mes;

--
-- Name: stations_station_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.stations_station_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.stations_station_pk_seq OWNER TO mes;

--
-- Name: stations_station_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.stations_station_pk_seq OWNED BY mes.stations.station_pk;


--
-- Name: vision_events; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.vision_events (
    vision_event_pk bigint NOT NULL,
    event_key text,
    item_id text,
    event_type text,
    detected_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.vision_events OWNER TO mes;

--
-- Name: vision_events_vision_event_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.vision_events_vision_event_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.vision_events_vision_event_pk_seq OWNER TO mes;

--
-- Name: vision_events_vision_event_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.vision_events_vision_event_pk_seq OWNED BY mes.vision_events.vision_event_pk;


--
-- Name: work_order_events; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.work_order_events (
    event_pk bigint NOT NULL,
    order_id text,
    event_type text NOT NULL,
    event_at timestamp with time zone,
    actor_id text,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.work_order_events OWNER TO mes;

--
-- Name: work_order_events_event_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.work_order_events_event_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.work_order_events_event_pk_seq OWNER TO mes;

--
-- Name: work_order_events_event_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.work_order_events_event_pk_seq OWNED BY mes.work_order_events.event_pk;


--
-- Name: work_orders; Type: TABLE; Schema: mes; Owner: mes
--

CREATE TABLE mes.work_orders (
    work_order_pk bigint NOT NULL,
    order_id text NOT NULL,
    erp_type text,
    status text,
    product_code text,
    target_quantity integer,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    source_system text DEFAULT 'mes_web'::text NOT NULL,
    source_file text,
    external_ref text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE mes.work_orders OWNER TO mes;

--
-- Name: work_orders_work_order_pk_seq; Type: SEQUENCE; Schema: mes; Owner: mes
--

CREATE SEQUENCE mes.work_orders_work_order_pk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE mes.work_orders_work_order_pk_seq OWNER TO mes;

--
-- Name: work_orders_work_order_pk_seq; Type: SEQUENCE OWNED BY; Schema: mes; Owner: mes
--

ALTER SEQUENCE mes.work_orders_work_order_pk_seq OWNED BY mes.work_orders.work_order_pk;


--
-- Name: device_sessions device_session_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.device_sessions ALTER COLUMN device_session_pk SET DEFAULT nextval('mes.device_sessions_device_session_pk_seq'::regclass);


--
-- Name: downtime_events downtime_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.downtime_events ALTER COLUMN downtime_pk SET DEFAULT nextval('mes.downtime_events_downtime_pk_seq'::regclass);


--
-- Name: error_types error_type_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.error_types ALTER COLUMN error_type_pk SET DEFAULT nextval('mes.error_types_error_type_pk_seq'::regclass);


--
-- Name: ferp_export_outbox export_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.ferp_export_outbox ALTER COLUMN export_pk SET DEFAULT nextval('mes.ferp_export_outbox_export_pk_seq'::regclass);


--
-- Name: ferp_import_batches import_batch_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.ferp_import_batches ALTER COLUMN import_batch_pk SET DEFAULT nextval('mes.ferp_import_batches_import_batch_pk_seq'::regclass);


--
-- Name: maintenance_records maintenance_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.maintenance_records ALTER COLUMN maintenance_pk SET DEFAULT nextval('mes.maintenance_records_maintenance_pk_seq'::regclass);


--
-- Name: maintenance_steps maintenance_step_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.maintenance_steps ALTER COLUMN maintenance_step_pk SET DEFAULT nextval('mes.maintenance_steps_maintenance_step_pk_seq'::regclass);


--
-- Name: oee_snapshots snapshot_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.oee_snapshots ALTER COLUMN snapshot_pk SET DEFAULT nextval('mes.oee_snapshots_snapshot_pk_seq'::regclass);


--
-- Name: operators operator_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.operators ALTER COLUMN operator_pk SET DEFAULT nextval('mes.operators_operator_pk_seq'::regclass);


--
-- Name: production_completions completion_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.production_completions ALTER COLUMN completion_pk SET DEFAULT nextval('mes.production_completions_completion_pk_seq'::regclass);


--
-- Name: quality_overrides quality_override_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.quality_overrides ALTER COLUMN quality_override_pk SET DEFAULT nextval('mes.quality_overrides_quality_override_pk_seq'::regclass);


--
-- Name: stations station_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.stations ALTER COLUMN station_pk SET DEFAULT nextval('mes.stations_station_pk_seq'::regclass);


--
-- Name: vision_events vision_event_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.vision_events ALTER COLUMN vision_event_pk SET DEFAULT nextval('mes.vision_events_vision_event_pk_seq'::regclass);


--
-- Name: work_order_events event_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.work_order_events ALTER COLUMN event_pk SET DEFAULT nextval('mes.work_order_events_event_pk_seq'::regclass);


--
-- Name: work_orders work_order_pk; Type: DEFAULT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.work_orders ALTER COLUMN work_order_pk SET DEFAULT nextval('mes.work_orders_work_order_pk_seq'::regclass);


--
-- Data for Name: device_sessions; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.device_sessions (device_session_pk, device_id, device_role, operator_id, started_at, ended_at, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: downtime_events; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.downtime_events (downtime_pk, fault_id, status_code, fault_type_code, started_at, ended_at, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: error_types; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.error_types (error_type_pk, error_type_id, error_type_code, error_category, error_reason, default_station_id, active, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ferp_export_outbox; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.ferp_export_outbox (export_pk, export_id, order_id, export_type, status, artifact_path, created_for_export_at, exported_at, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ferp_import_batches; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.ferp_import_batches (import_batch_pk, batch_id, source_file, imported_at, status, source_system, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: maintenance_records; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.maintenance_records (maintenance_pk, maintenance_row_key, session_id, phase_code, step_code, status, recorded_at, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: maintenance_steps; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.maintenance_steps (maintenance_step_pk, phase_code, step_code, step_label, required, sort_order, active, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: oee_snapshots; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.oee_snapshots (snapshot_pk, snapshot_at, shift_id, availability, performance, quality, oee, source_system, source_file, external_ref, payload, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: operators; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.operators (operator_pk, operator_id, operator_code, operator_name, active, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: production_completions; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.production_completions (completion_pk, order_id, item_id, classification, completed_at, source_system, source_file, external_ref, payload, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: quality_overrides; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.quality_overrides (quality_override_pk, item_id, classification, operator_id, recorded_at, source_system, source_file, external_ref, payload, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: stations; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.stations (station_pk, station_id, station_code, station_name, line_id, active, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: vision_events; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.vision_events (vision_event_pk, event_key, item_id, event_type, detected_at, source_system, source_file, external_ref, payload, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: work_order_events; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.work_order_events (event_pk, order_id, event_type, event_at, actor_id, source_system, source_file, external_ref, payload, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: work_orders; Type: TABLE DATA; Schema: mes; Owner: mes
--

COPY mes.work_orders (work_order_pk, order_id, erp_type, status, product_code, target_quantity, started_at, completed_at, source_system, source_file, external_ref, payload, metadata, created_at, updated_at) FROM stdin;
1	TEST-FERP-001	Is Emirleri	queued	BOX-RED	1	\N	\N	mes_web	ferp_work_orders.json	TEST-FERP-001	{"date": "2026-04-28", "unit": "ADET", "locked": false, "status": "queued", "cutCode": "", "erpType": "Is Emirleri", "lotCode": "", "orderId": "TEST-FERP-001", "partyNo": "", "routeId": "", "matchKey": "red", "quantity": 1, "queuedAt": "2026-06-05T11:40:21.088+00:00", "systemNo": "TEST-FERP-001", "materials": [], "productId": "BOX-RED", "shiftCode": "", "startedAt": "", "startedBy": "", "stockCode": "BOX-RED", "stockName": "Kirmizi Test Kutusu", "stockType": "Mamul", "ferpLabels": {}, "ferpObject": "mym4004", "ferpScreen": "Is Emirleri", "methodCode": "", "operations": [], "sequenceNo": 0, "completedAt": "", "cycleTimeMs": 15000, "description": "Fiziksel saha test is emri - kirmizi kutu", "productCode": "BOX-RED", "productName": "Kirmizi Test Kutusu", "projectCode": "FIELD-TEST", "setupTimeMs": 0, "stationPlan": [], "workerCount": 0, "completedQty": 0, "cycleTimeSec": 15.0, "ferpWarnings": [], "productColor": "red", "remainingQty": 1, "requirements": [{"color": "red", "lineId": "RED-BOX", "matchKey": "red", "quantity": 1, "stockCode": "BOX-RED", "stockName": "Kirmizi Test Kutusu", "productCode": "BOX-RED", "completedQty": 0, "remainingQty": 1, "productionQty": 0, "inventoryConsumedQty": 0}], "setupTimeSec": 0.0, "operationCode": "", "productionQty": 0, "startedByName": "", "workCenterCode": "", "autoCompletedAt": "", "workStationCode": "", "lastAllocationAt": "", "transitionReason": "", "idealCycleTimeSec": 15.0, "inventoryConsumedQty": 0}	{"priority": null, "state_file": "/work/logs/oee_runtime_state.json", "source_folder": "/app/mes_web/ferp_import", "planned_fields": {"queued_at": "2026-06-05T11:40:21.088+00:00", "planned_end_at": null, "planned_start_at": null}, "source_loaded_at": "2026-06-05T11:40:21.088+00:00", "runtime_order_key": "TEST-FERP-001", "completed_quantity": 0, "remaining_quantity": 1}	2026-06-08 08:52:19.331473+00	2026-06-08 09:13:28.073718+00
2	TEST-FERP-REWORK	Is Emirleri	queued	BOX-YEL	1	\N	\N	mes_web	ferp_work_orders.json	TEST-FERP-REWORK	{"date": "2026-04-28", "unit": "ADET", "locked": false, "status": "queued", "cutCode": "", "erpType": "Is Emirleri", "lotCode": "", "orderId": "TEST-FERP-REWORK", "partyNo": "", "routeId": "", "matchKey": "yellow", "quantity": 1, "queuedAt": "2026-06-05T11:40:21.088+00:00", "systemNo": "TEST-FERP-REWORK", "materials": [], "productId": "BOX-YEL", "shiftCode": "", "startedAt": "", "startedBy": "", "stockCode": "BOX-YEL", "stockName": "Sari Test Kutusu", "stockType": "Mamul", "ferpLabels": {}, "ferpObject": "mym4004", "ferpScreen": "Is Emirleri", "methodCode": "", "operations": [], "sequenceNo": 0, "completedAt": "", "cycleTimeMs": 15000, "description": "Fiziksel saha test is emri - sari kutu", "productCode": "BOX-YEL", "productName": "Sari Test Kutusu", "projectCode": "FIELD-TEST", "setupTimeMs": 0, "stationPlan": [], "workerCount": 0, "completedQty": 0, "cycleTimeSec": 15.0, "ferpWarnings": [], "productColor": "yellow", "remainingQty": 1, "requirements": [{"color": "yellow", "lineId": "YELLOW-BOX", "matchKey": "yellow", "quantity": 1, "stockCode": "BOX-YEL", "stockName": "Sari Test Kutusu", "productCode": "BOX-YEL", "completedQty": 0, "remainingQty": 1, "productionQty": 0, "inventoryConsumedQty": 0}], "setupTimeSec": 0.0, "operationCode": "", "productionQty": 0, "startedByName": "", "workCenterCode": "", "autoCompletedAt": "", "workStationCode": "", "lastAllocationAt": "", "transitionReason": "", "idealCycleTimeSec": 15.0, "inventoryConsumedQty": 0}	{"priority": null, "state_file": "/work/logs/oee_runtime_state.json", "source_folder": "/app/mes_web/ferp_import", "planned_fields": {"queued_at": "2026-06-05T11:40:21.088+00:00", "planned_end_at": null, "planned_start_at": null}, "source_loaded_at": "2026-06-05T11:40:21.088+00:00", "runtime_order_key": "TEST-FERP-REWORK", "completed_quantity": 0, "remaining_quantity": 1}	2026-06-08 08:52:19.331473+00	2026-06-08 09:13:28.077243+00
3	TEST-FERP-SCRAP	Is Emirleri	queued	BOX-BLUE	6	\N	\N	mes_web	ferp_work_orders.json	TEST-FERP-SCRAP	{"date": "2026-04-28", "unit": "ADET", "locked": false, "status": "queued", "cutCode": "", "erpType": "Is Emirleri", "lotCode": "", "orderId": "TEST-FERP-SCRAP", "partyNo": "", "routeId": "", "matchKey": "blue", "quantity": 6, "queuedAt": "2026-06-05T11:40:21.088+00:00", "systemNo": "TEST-FERP-SCRAP", "materials": [], "productId": "BOX-BLUE", "shiftCode": "", "startedAt": "", "startedBy": "", "stockCode": "BOX-BLUE", "stockName": "Mavi Test Kutusu", "stockType": "Mamul", "ferpLabels": {}, "ferpObject": "mym4004", "ferpScreen": "Is Emirleri", "methodCode": "", "operations": [], "sequenceNo": 0, "completedAt": "", "cycleTimeMs": 15000, "description": "Fiziksel saha test is emri - mavi kutu", "productCode": "BOX-BLUE", "productName": "Mavi Test Kutusu", "projectCode": "FIELD-TEST", "setupTimeMs": 0, "stationPlan": [], "workerCount": 0, "completedQty": 0, "cycleTimeSec": 15.0, "ferpWarnings": [], "productColor": "blue", "remainingQty": 6, "requirements": [{"color": "blue", "lineId": "BLUE-BOX", "matchKey": "blue", "quantity": 6, "stockCode": "BOX-BLUE", "stockName": "Mavi Test Kutusu", "productCode": "BOX-BLUE", "completedQty": 0, "remainingQty": 6, "productionQty": 0, "inventoryConsumedQty": 0}], "setupTimeSec": 0.0, "operationCode": "", "productionQty": 0, "startedByName": "", "workCenterCode": "", "autoCompletedAt": "", "workStationCode": "", "lastAllocationAt": "", "transitionReason": "", "idealCycleTimeSec": 15.0, "inventoryConsumedQty": 0}	{"priority": null, "state_file": "/work/logs/oee_runtime_state.json", "source_folder": "/app/mes_web/ferp_import", "planned_fields": {"queued_at": "2026-06-05T11:40:21.088+00:00", "planned_end_at": null, "planned_start_at": null}, "source_loaded_at": "2026-06-05T11:40:21.088+00:00", "runtime_order_key": "TEST-FERP-SCRAP", "completed_quantity": 0, "remaining_quantity": 6}	2026-06-08 08:52:19.331473+00	2026-06-08 09:13:28.07841+00
4	WO-PKT-BLUE-001	Paketleme Is Emirleri	queued	PKT-BLUE	3	\N	\N	mes_web	ferp_work_orders.json	WO-PKT-BLUE-001	{"date": "2026-04-28", "unit": "ADET", "locked": false, "status": "queued", "cutCode": "", "erpType": "Paketleme Is Emirleri", "lotCode": "", "orderId": "WO-PKT-BLUE-001", "partyNo": "", "routeId": "PKT-RENK-ROUTE-01", "matchKey": "blue", "quantity": 3, "queuedAt": "2026-06-05T11:40:21.088+00:00", "systemNo": "WO-PKT-BLUE-001", "materials": [{"color": "blue", "itemCode": "KUTU-MVI", "itemName": "Mavi Kutu", "itemType": "box", "qtyPerUnit": 2.0}, {"color": "blue", "itemCode": "PKT-MAVI", "itemName": "Mavi Paket", "itemType": "package", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "ETK-PKT-MAVI", "itemName": "Mavi Paket Etiketi", "itemType": "label", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "KLVZ-PKT-01", "itemName": "Kullanim Kilavuzu", "itemType": "consumable", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "BANT-PKT-01", "itemName": "Paket Bandi", "itemType": "consumable", "qtyPerUnit": 1.0}], "productId": "PKT-BLUE", "shiftCode": "", "startedAt": "", "startedBy": "", "stockCode": "PKT-BLUE", "stockName": "Mavi Paket", "stockType": "Mamul", "ferpLabels": {}, "ferpObject": "mym4004", "ferpScreen": "Paketleme Is Emirleri", "methodCode": "", "operations": [{"opNo": 10, "source": "time_study", "stationId": "station2", "operationName": "Kutu Koy", "standardTimeSec": 12.0}, {"opNo": 20, "source": "time_study", "stationId": "station2", "operationName": "Kullanim Kilavuzu Koy", "standardTimeSec": 8.0}, {"opNo": 30, "source": "time_study", "stationId": "station2", "operationName": "Paketi Kapat", "standardTimeSec": 15.0}, {"opNo": 40, "source": "time_study", "stationId": "station2", "operationName": "Bantla", "standardTimeSec": 10.0}], "sequenceNo": 0, "completedAt": "", "cycleTimeMs": 45000, "description": "Mavi paket demo is emri", "productCode": "PKT-BLUE", "productName": "Mavi Paket", "projectCode": "FIELD-TEST", "setupTimeMs": 0, "stationPlan": ["station1", "station2"], "workerCount": 0, "completedQty": 0, "cycleTimeSec": 45.0, "ferpWarnings": [], "productColor": "blue", "remainingQty": 3, "requirements": [], "setupTimeSec": 0.0, "operationCode": "", "productionQty": 0, "startedByName": "", "workCenterCode": "", "autoCompletedAt": "", "workStationCode": "", "lastAllocationAt": "", "transitionReason": "", "idealCycleTimeSec": 45.0, "inventoryConsumedQty": 0}	{"priority": null, "state_file": "/work/logs/oee_runtime_state.json", "source_folder": "/app/mes_web/ferp_import", "planned_fields": {"queued_at": "2026-06-05T11:40:21.088+00:00", "planned_end_at": null, "planned_start_at": null}, "source_loaded_at": "2026-06-05T11:40:21.088+00:00", "runtime_order_key": "WO-PKT-BLUE-001", "completed_quantity": 0, "remaining_quantity": 3}	2026-06-08 08:52:19.331473+00	2026-06-08 09:13:28.079647+00
5	WO-PKT-RED-001	Paketleme Is Emirleri	queued	PKT-RED	1	\N	\N	mes_web	ferp_work_orders.json	WO-PKT-RED-001	{"date": "2026-04-28", "unit": "ADET", "locked": false, "status": "queued", "cutCode": "", "erpType": "Paketleme Is Emirleri", "lotCode": "", "orderId": "WO-PKT-RED-001", "partyNo": "", "routeId": "PKT-RENK-ROUTE-01", "matchKey": "red", "quantity": 1, "queuedAt": "2026-06-05T11:40:21.088+00:00", "systemNo": "WO-PKT-RED-001", "materials": [{"color": "red", "itemCode": "KUTU-KRM", "itemName": "Kirmizi Kutu", "itemType": "box", "qtyPerUnit": 1.0}, {"color": "red", "itemCode": "PKT-KIRMIZI", "itemName": "Kirmizi Paket", "itemType": "package", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "ETK-PKT-KIRMIZI", "itemName": "Kirmizi Paket Etiketi", "itemType": "label", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "KLVZ-PKT-01", "itemName": "Kullanim Kilavuzu", "itemType": "consumable", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "BANT-PKT-01", "itemName": "Paket Bandi", "itemType": "consumable", "qtyPerUnit": 1.0}], "productId": "PKT-RED", "shiftCode": "", "startedAt": "", "startedBy": "", "stockCode": "PKT-RED", "stockName": "Kirmizi Paket", "stockType": "Mamul", "ferpLabels": {}, "ferpObject": "mym4004", "ferpScreen": "Paketleme Is Emirleri", "methodCode": "", "operations": [{"opNo": 10, "source": "time_study", "stationId": "station2", "operationName": "Kutu Koy", "standardTimeSec": 12.0}, {"opNo": 20, "source": "time_study", "stationId": "station2", "operationName": "Kullanim Kilavuzu Koy", "standardTimeSec": 8.0}, {"opNo": 30, "source": "time_study", "stationId": "station2", "operationName": "Paketi Kapat", "standardTimeSec": 15.0}, {"opNo": 40, "source": "time_study", "stationId": "station2", "operationName": "Bantla", "standardTimeSec": 10.0}], "sequenceNo": 0, "completedAt": "", "cycleTimeMs": 45000, "description": "Kirmizi paket demo is emri", "productCode": "PKT-RED", "productName": "Kirmizi Paket", "projectCode": "FIELD-TEST", "setupTimeMs": 0, "stationPlan": ["station1", "station2"], "workerCount": 0, "completedQty": 0, "cycleTimeSec": 45.0, "ferpWarnings": [], "productColor": "red", "remainingQty": 1, "requirements": [], "setupTimeSec": 0.0, "operationCode": "", "productionQty": 0, "startedByName": "", "workCenterCode": "", "autoCompletedAt": "", "workStationCode": "", "lastAllocationAt": "", "transitionReason": "", "idealCycleTimeSec": 45.0, "inventoryConsumedQty": 0}	{"priority": null, "state_file": "/work/logs/oee_runtime_state.json", "source_folder": "/app/mes_web/ferp_import", "planned_fields": {"queued_at": "2026-06-05T11:40:21.088+00:00", "planned_end_at": null, "planned_start_at": null}, "source_loaded_at": "2026-06-05T11:40:21.088+00:00", "runtime_order_key": "WO-PKT-RED-001", "completed_quantity": 0, "remaining_quantity": 1}	2026-06-08 08:52:19.331473+00	2026-06-08 09:13:28.080526+00
6	WO-PKT-YELLOW-001	Paketleme Is Emirleri	queued	PKT-YELLOW	1	\N	\N	mes_web	ferp_work_orders.json	WO-PKT-YELLOW-001	{"date": "2026-04-28", "unit": "ADET", "locked": false, "status": "queued", "cutCode": "", "erpType": "Paketleme Is Emirleri", "lotCode": "", "orderId": "WO-PKT-YELLOW-001", "partyNo": "", "routeId": "PKT-RENK-ROUTE-01", "matchKey": "yellow", "quantity": 1, "queuedAt": "2026-06-05T11:40:21.088+00:00", "systemNo": "WO-PKT-YELLOW-001", "materials": [{"color": "yellow", "itemCode": "KUTU-SRI", "itemName": "Sari Kutu", "itemType": "box", "qtyPerUnit": 1.0}, {"color": "yellow", "itemCode": "PKT-SARI", "itemName": "Sari Paket", "itemType": "package", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "ETK-PKT-SARI", "itemName": "Sari Paket Etiketi", "itemType": "label", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "KLVZ-PKT-01", "itemName": "Kullanim Kilavuzu", "itemType": "consumable", "qtyPerUnit": 1.0}, {"color": "", "itemCode": "BANT-PKT-01", "itemName": "Paket Bandi", "itemType": "consumable", "qtyPerUnit": 1.0}], "productId": "PKT-YELLOW", "shiftCode": "", "startedAt": "", "startedBy": "", "stockCode": "PKT-YELLOW", "stockName": "Sari Paket", "stockType": "Mamul", "ferpLabels": {}, "ferpObject": "mym4004", "ferpScreen": "Paketleme Is Emirleri", "methodCode": "", "operations": [{"opNo": 10, "source": "time_study", "stationId": "station2", "operationName": "Kutu Koy", "standardTimeSec": 12.0}, {"opNo": 20, "source": "time_study", "stationId": "station2", "operationName": "Kullanim Kilavuzu Koy", "standardTimeSec": 8.0}, {"opNo": 30, "source": "time_study", "stationId": "station2", "operationName": "Paketi Kapat", "standardTimeSec": 15.0}, {"opNo": 40, "source": "time_study", "stationId": "station2", "operationName": "Bantla", "standardTimeSec": 10.0}], "sequenceNo": 0, "completedAt": "", "cycleTimeMs": 45000, "description": "Sari paket demo is emri", "productCode": "PKT-YELLOW", "productName": "Sari Paket", "projectCode": "FIELD-TEST", "setupTimeMs": 0, "stationPlan": ["station1", "station2"], "workerCount": 0, "completedQty": 0, "cycleTimeSec": 45.0, "ferpWarnings": [], "productColor": "yellow", "remainingQty": 1, "requirements": [], "setupTimeSec": 0.0, "operationCode": "", "productionQty": 0, "startedByName": "", "workCenterCode": "", "autoCompletedAt": "", "workStationCode": "", "lastAllocationAt": "", "transitionReason": "", "idealCycleTimeSec": 45.0, "inventoryConsumedQty": 0}	{"priority": null, "state_file": "/work/logs/oee_runtime_state.json", "source_folder": "/app/mes_web/ferp_import", "planned_fields": {"queued_at": "2026-06-05T11:40:21.088+00:00", "planned_end_at": null, "planned_start_at": null}, "source_loaded_at": "2026-06-05T11:40:21.088+00:00", "runtime_order_key": "WO-PKT-YELLOW-001", "completed_quantity": 0, "remaining_quantity": 1}	2026-06-08 08:52:19.331473+00	2026-06-08 09:13:28.081601+00
\.


--
-- Name: device_sessions_device_session_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.device_sessions_device_session_pk_seq', 1, false);


--
-- Name: downtime_events_downtime_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.downtime_events_downtime_pk_seq', 1, false);


--
-- Name: error_types_error_type_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.error_types_error_type_pk_seq', 1, false);


--
-- Name: ferp_export_outbox_export_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.ferp_export_outbox_export_pk_seq', 1, false);


--
-- Name: ferp_import_batches_import_batch_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.ferp_import_batches_import_batch_pk_seq', 1, false);


--
-- Name: maintenance_records_maintenance_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.maintenance_records_maintenance_pk_seq', 1, false);


--
-- Name: maintenance_steps_maintenance_step_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.maintenance_steps_maintenance_step_pk_seq', 1, false);


--
-- Name: oee_snapshots_snapshot_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.oee_snapshots_snapshot_pk_seq', 1, false);


--
-- Name: operators_operator_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.operators_operator_pk_seq', 1, false);


--
-- Name: production_completions_completion_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.production_completions_completion_pk_seq', 1, false);


--
-- Name: quality_overrides_quality_override_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.quality_overrides_quality_override_pk_seq', 1, false);


--
-- Name: stations_station_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.stations_station_pk_seq', 1, false);


--
-- Name: vision_events_vision_event_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.vision_events_vision_event_pk_seq', 1, false);


--
-- Name: work_order_events_event_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.work_order_events_event_pk_seq', 1, false);


--
-- Name: work_orders_work_order_pk_seq; Type: SEQUENCE SET; Schema: mes; Owner: mes
--

SELECT pg_catalog.setval('mes.work_orders_work_order_pk_seq', 12, true);


--
-- Name: device_sessions device_sessions_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.device_sessions
    ADD CONSTRAINT device_sessions_pkey PRIMARY KEY (device_session_pk);


--
-- Name: downtime_events downtime_events_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.downtime_events
    ADD CONSTRAINT downtime_events_pkey PRIMARY KEY (downtime_pk);


--
-- Name: error_types error_types_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.error_types
    ADD CONSTRAINT error_types_pkey PRIMARY KEY (error_type_pk);


--
-- Name: ferp_export_outbox ferp_export_outbox_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.ferp_export_outbox
    ADD CONSTRAINT ferp_export_outbox_pkey PRIMARY KEY (export_pk);


--
-- Name: ferp_import_batches ferp_import_batches_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.ferp_import_batches
    ADD CONSTRAINT ferp_import_batches_pkey PRIMARY KEY (import_batch_pk);


--
-- Name: maintenance_records maintenance_records_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.maintenance_records
    ADD CONSTRAINT maintenance_records_pkey PRIMARY KEY (maintenance_pk);


--
-- Name: maintenance_steps maintenance_steps_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.maintenance_steps
    ADD CONSTRAINT maintenance_steps_pkey PRIMARY KEY (maintenance_step_pk);


--
-- Name: oee_snapshots oee_snapshots_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.oee_snapshots
    ADD CONSTRAINT oee_snapshots_pkey PRIMARY KEY (snapshot_pk);


--
-- Name: operators operators_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.operators
    ADD CONSTRAINT operators_pkey PRIMARY KEY (operator_pk);


--
-- Name: production_completions production_completions_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.production_completions
    ADD CONSTRAINT production_completions_pkey PRIMARY KEY (completion_pk);


--
-- Name: quality_overrides quality_overrides_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.quality_overrides
    ADD CONSTRAINT quality_overrides_pkey PRIMARY KEY (quality_override_pk);


--
-- Name: stations stations_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.stations
    ADD CONSTRAINT stations_pkey PRIMARY KEY (station_pk);


--
-- Name: vision_events vision_events_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.vision_events
    ADD CONSTRAINT vision_events_pkey PRIMARY KEY (vision_event_pk);


--
-- Name: work_order_events work_order_events_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.work_order_events
    ADD CONSTRAINT work_order_events_pkey PRIMARY KEY (event_pk);


--
-- Name: work_orders work_orders_pkey; Type: CONSTRAINT; Schema: mes; Owner: mes
--

ALTER TABLE ONLY mes.work_orders
    ADD CONSTRAINT work_orders_pkey PRIMARY KEY (work_order_pk);


--
-- Name: ix_mes_device_sessions_device_id; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_device_sessions_device_id ON mes.device_sessions USING btree (device_id);


--
-- Name: ix_mes_downtime_events_started_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_downtime_events_started_at ON mes.downtime_events USING btree (started_at);


--
-- Name: ix_mes_ferp_export_outbox_status; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_ferp_export_outbox_status ON mes.ferp_export_outbox USING btree (status, created_at);


--
-- Name: ix_mes_ferp_import_batches_imported_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_ferp_import_batches_imported_at ON mes.ferp_import_batches USING btree (imported_at);


--
-- Name: ix_mes_maintenance_records_session_id; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_maintenance_records_session_id ON mes.maintenance_records USING btree (session_id);


--
-- Name: ix_mes_oee_snapshots_snapshot_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_oee_snapshots_snapshot_at ON mes.oee_snapshots USING btree (snapshot_at);


--
-- Name: ix_mes_production_completions_completed_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_production_completions_completed_at ON mes.production_completions USING btree (completed_at);


--
-- Name: ix_mes_quality_overrides_recorded_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_quality_overrides_recorded_at ON mes.quality_overrides USING btree (recorded_at);


--
-- Name: ix_mes_vision_events_detected_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_vision_events_detected_at ON mes.vision_events USING btree (detected_at);


--
-- Name: ix_mes_work_order_events_order_id_event_at; Type: INDEX; Schema: mes; Owner: mes
--

CREATE INDEX ix_mes_work_order_events_order_id_event_at ON mes.work_order_events USING btree (order_id, event_at);


--
-- Name: ux_mes_error_types_error_type_code; Type: INDEX; Schema: mes; Owner: mes
--

CREATE UNIQUE INDEX ux_mes_error_types_error_type_code ON mes.error_types USING btree (error_type_code) WHERE (error_type_code IS NOT NULL);


--
-- Name: ux_mes_maintenance_steps_phase_step; Type: INDEX; Schema: mes; Owner: mes
--

CREATE UNIQUE INDEX ux_mes_maintenance_steps_phase_step ON mes.maintenance_steps USING btree (phase_code, step_code) WHERE ((phase_code IS NOT NULL) AND (step_code IS NOT NULL));


--
-- Name: ux_mes_operators_operator_code; Type: INDEX; Schema: mes; Owner: mes
--

CREATE UNIQUE INDEX ux_mes_operators_operator_code ON mes.operators USING btree (operator_code) WHERE (operator_code IS NOT NULL);


--
-- Name: ux_mes_stations_station_code; Type: INDEX; Schema: mes; Owner: mes
--

CREATE UNIQUE INDEX ux_mes_stations_station_code ON mes.stations USING btree (station_code) WHERE (station_code IS NOT NULL);


--
-- Name: ux_mes_work_orders_order_id; Type: INDEX; Schema: mes; Owner: mes
--

CREATE UNIQUE INDEX ux_mes_work_orders_order_id ON mes.work_orders USING btree (order_id);


--
-- PostgreSQL database dump complete
--

\unrestrict M6SpoTt2WMNM1aqwVuTsxImm1RmHMUPKwzMHpyfag1BoXPEjDZjoGZBaEQSj1Cf

