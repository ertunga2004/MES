# Station Execution Config Read Smoke Evidence

## Summary

Result: PASS.

Station execution config read-only helpers were verified against the real local
PostgreSQL database on 2026-07-09. The smoke used only read-only helper calls
and SELECT count checks.

No write SQL, seed apply, migration apply, runtime engine action, Kiosk action,
MESQL push/pull, work order mutation, queue mutation, or operation lifecycle
mutation was performed.

## Files

- Helper implementation: `mes_web/db/mesql_v2.py`
- Unit tests: `tests/test_mes_web_mesql_v2.py`
- Seed evidence:
  `docs/runbooks/station_execution_seed_minimal_evidence_20260709.md`
- Current state checkpoint: `docs/architecture/CURRENT_STATE.md`

Latest helper commit observed before smoke:

```text
90a6528 "feat: add station execution config read helpers"
```

## Unit Regression

Command:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_mesql_v2
```

Result:

```text
Ran 41 tests in 0.086s
OK
```

Notes:

- FastAPI `on_event` deprecation warnings were printed.
- No test failure occurred.

## Container / Health Precheck

Docker compose status:

```text
mes_adminer    Up
mes_postgres   Up (healthy)
mes_web        Up
```

Health before smoke:

```json
{
  "status": "ok",
  "time": "2026-07-09T09:27:09.197+00:00"
}
```

## Read-Only SQL Guard

Checked SQL constants:

```text
SELECT_ITEMS_SQL
SELECT_ITEM_BY_CODE_SQL
SELECT_PROCESS_ROUTES_SQL
SELECT_PROCESS_ROUTE_SQL
SELECT_ROUTE_OPERATIONS_SQL
SELECT_ROUTE_OPERATION_BY_ID_SQL
SELECT_STATION_EVENT_SOURCES_SQL
SELECT_STATION_EVENT_SOURCE_SQL
SELECT_OPERATION_STEPS_SQL
SELECT_OPERATION_STEP_SQL
SELECT_STATION_EXISTS_SQL
```

Guard result:

```text
checked_sql_constants = 11
READ_ONLY_SQL_GUARD = PASS
```

All checked constants:

- start with `SELECT`
- do not contain `FOR UPDATE`
- do not contain `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, or
  `CREATE`
- do not read runtime/event/flow tables
- do not read lifecycle tables such as `mes.work_orders`,
  `mes.work_order_operations`, or `mes.station_queue`

`SELECT_STATION_EXISTS_SQL` reads only `mes.stations`.

## Real DB Helper Smoke

The smoke ran the current repo helper implementation against local PostgreSQL
through host port `127.0.0.1:5433`.

The DB password was read transiently from the running `mes_postgres` container
environment and was not printed or written to a file.

Helper coverage:

```text
list_items(active_only=True)
get_item_by_code("raw_box")
list_process_routes(item_code="PACKAGED_PRODUCT")
get_process_route("route_box_packaging_v1", version=1)
list_route_operations(station_code="ASSEMBLY_01")
list_route_operations(station_code="PACKAGING_01")
get_route_operation("route_box_packaging_v1_op10")
get_route_operation("route_box_packaging_v1_op20")
list_station_event_sources("ASSEMBLY_01")
list_station_event_sources("PACKAGING_01")
resolve_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY")
resolve_station_event_source("PACKAGING_01", "KIOSK_OPERATOR")
list_operation_steps("ROUTE_BOX_PACKAGING_V1_OP10")
list_operation_steps("ROUTE_BOX_PACKAGING_V1_OP20")
get_operation_step("ROUTE_BOX_PACKAGING_V1_OP10", "COLOR_SENSOR_ENTRY_EVIDENCE")
get_route_operation_config("ROUTE_BOX_PACKAGING_V1_OP10")
get_route_operation_config("ROUTE_BOX_PACKAGING_V1_OP20")
get_station_execution_config("ASSEMBLY_01")
get_station_execution_config("PACKAGING_01")
```

Smoke summary:

```text
seed_items_count = 3
RAW_BOX item exists = true
ROUTE_BOX_PACKAGING_V1 exists = true
routes_for_packaged_product = 1
ASSEMBLY_01 route operation count = 1
PACKAGING_01 route operation count = 1
OP10 exists = true
OP20 exists = true
ASSEMBLY_01 event source count = 3
PACKAGING_01 event source count = 1
COLOR_SENSOR_ENTRY resolves for ASSEMBLY_01 = true
KIOSK_OPERATOR resolves for PACKAGING_01 = true
OP10 step count = 3
OP20 step count = 2
OP10 COLOR_SENSOR_ENTRY_EVIDENCE step exists = true
ASSEMBLY_01 station config route_operations count = 1
PACKAGING_01 station config route_operations count = 1
```

Result:

```text
PASS
```

## Aggregate Validation

OP10 aggregate validation:

```text
missing_items = []
missing_station = []
missing_event_sources = []
invalid_step_source_refs = []
invalid_auto_mode_refs = []
```

OP20 aggregate validation:

```text
missing_items = []
missing_station = []
missing_event_sources = []
invalid_step_source_refs = []
invalid_auto_mode_refs = []
```

Result:

```text
PASS
```

No critical validation warnings were returned for the seeded OP10/OP20 config.

## No-Write Baseline Check

Counts before smoke:

```text
items = 3
process_routes = 1
route_operations = 2
station_event_sources = 4
operation_steps = 5
work_order_operation_execution_state = 0
work_order_operation_steps = 0
operation_events = 0
operation_approvals = 0
production_flow_events = 0
locations = 8
active_station_location_bindings = 8
```

Counts after smoke:

```text
items = 3
process_routes = 1
route_operations = 2
station_event_sources = 4
operation_steps = 5
work_order_operation_execution_state = 0
work_order_operation_steps = 0
operation_events = 0
operation_approvals = 0
production_flow_events = 0
locations = 8
active_station_location_bindings = 8
```

Result:

```text
PASS
```

All checked counts were unchanged before and after helper smoke.

## Health / Limited Regression

Health after smoke:

```json
{
  "status": "ok",
  "time": "2026-07-09T09:29:41.625+00:00"
}
```

Station/location read-only API default-disabled check:

```text
GET /api/v2/locations -> 503
```

Kiosk static GET checks:

```text
GET /kiosk -> 200
GET /static/kiosk.js -> 200
GET /static/kiosk.css -> 200
```

No POST request was made.

## Guardrails

- No write SQL.
- No `INSERT`.
- No `UPDATE`.
- No `DELETE`.
- No `DROP`.
- No `TRUNCATE`.
- No `ALTER`.
- No `CREATE`.
- No `FOR UPDATE`.
- No seed apply.
- No migration apply.
- No API route implementation.
- No Kiosk implementation.
- No Kiosk dynamic action implementation.
- No runtime engine implementation.
- No IoT adapter implementation.
- No OEE/KPI implementation.
- No inventory movement/balance implementation.
- No MESQL push/pull.
- No operation lifecycle mutation.
- No work order mutation.
- No queue mutation.
- No `docker compose down -v`.
- No Docker volume removal.
- No commit/push during smoke.
- `.agents/` was not read, changed, moved, deleted, staged, or created under.

## Result

PASS.

Station execution config read-only helpers successfully read the seeded local
PostgreSQL config. Aggregate validation returned no critical warnings. No-write
baseline counts were unchanged, runtime/event/flow tables remained empty, and
health / limited regression checks passed.
