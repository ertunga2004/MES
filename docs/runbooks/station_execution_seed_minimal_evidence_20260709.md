# Station Execution Minimal Seed Evidence

## Summary

`db/migrations/005_station_execution_seed_minimal.sql` was applied to the local
PostgreSQL database on 2026-07-09 after a backup and pre-apply safety checks.

Result: PASS.

This was a SQL-driven master/config seed only. It did not create runtime
execution state, operation event rows, approval rows, production flow rows,
work orders, station queue rows, inventory movement data, or MESQL changes.

## Files

- Seed SQL: `db/migrations/005_station_execution_seed_minimal.sql`
- Apply runbook:
  `docs/runbooks/station_execution_seed_minimal_apply_runbook.md`
- Schema migration evidence:
  `docs/runbooks/station_execution_schema_migration_evidence_20260709.md`

## Backup

Backup was taken before apply:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_005_station_execution_seed_minimal_20260709-115906.sql
```

Backup verification:

```text
Test-Path = True
Length = 5764614 bytes
LastWriteTime = 2026-07-09 11:59:06 Europe/Istanbul
```

## Pre-Apply Checks

Git status before apply:

```text
## main...origin/main
?? db/migrations/005_station_execution_seed_minimal.sql
?? docs/runbooks/station_execution_seed_minimal_apply_runbook.md
```

Required files existed:

```text
db\migrations\005_station_execution_seed_minimal.sql = True
docs\runbooks\station_execution_seed_minimal_apply_runbook.md = True
docs\runbooks\station_execution_schema_migration_evidence_20260709.md = True
```

Docker compose status:

```text
mes_adminer    Up
mes_postgres   Up (healthy)
mes_web        Up
```

Health before apply:

```json
{
  "status": "ok",
  "time": "2026-07-09T08:58:58.243+00:00"
}
```

Schema precondition:

```text
13 required mes tables found:
items
locations
operation_approvals
operation_events
operation_steps
process_routes
production_flow_events
route_operations
station_event_sources
station_location_bindings
stations
work_order_operation_execution_state
work_order_operation_steps
```

Station precondition:

```text
ASSEMBLY_01  | Istasyon 1 - Kutu Uretim | active=true
PACKAGING_01 | Istasyon 2 - Paketleme   | active=true
```

Station/location baseline before apply:

```text
locations = 8
active_station_location_bindings = 8
```

## Destructive / Forbidden Table Check

The seed SQL was scanned for destructive or forbidden table writes.

Patterns checked:

```text
DROP TABLE
DROP COLUMN
ALTER TABLE
TRUNCATE
DELETE FROM
UPDATE mes.work_orders
UPDATE mes.work_order_operations
UPDATE mes.station_queue
UPDATE mes.locations
UPDATE mes.station_location_bindings
INSERT INTO mes.work_orders
INSERT INTO mes.work_order_operations
INSERT INTO mes.station_queue
INSERT INTO mes.locations
INSERT INTO mes.station_location_bindings
```

Result:

```text
No matches.
```

## Runtime/Event Insert Check

The seed SQL was scanned for runtime/event/flow inserts.

Patterns checked:

```text
INSERT INTO mes.work_order_operation_execution_state
INSERT INTO mes.work_order_operation_steps
INSERT INTO mes.operation_events
INSERT INTO mes.operation_approvals
INSERT INTO mes.production_flow_events
```

Result:

```text
No matches.
```

## Seed Apply Result

Apply command used `psql -v ON_ERROR_STOP=1` through the existing
`mes_postgres` container.

Result:

```text
BEGIN
INSERT 0 3
INSERT 0 1
INSERT 0 2
INSERT 0 4
INSERT 0 5
COMMIT
```

## Seed Verify

Items:

```text
ITEM_RAW_BOX              | RAW_BOX              | raw_material  | piece | active=true
ITEM_COLOR_CLASSIFIED_BOX | COLOR_CLASSIFIED_BOX | semi_finished | piece | active=true
ITEM_PACKAGED_PRODUCT     | PACKAGED_PRODUCT     | finished_good | piece | active=true
```

Process route:

```text
ROUTE_BOX_PACKAGING_V1 | version=1 | item_code=PACKAGED_PRODUCT | active=true
```

Route operations:

```text
ROUTE_BOX_PACKAGING_V1_OP10 | sequence_no=10 | OP10_ASSEMBLY_CLASSIFICATION | ASSEMBLY_01  | RAW_BOX              -> COLOR_CLASSIFIED_BOX | input -> output_buffer | scrap=output_scrap | auto_complete_pending_approval | active=true
ROUTE_BOX_PACKAGING_V1_OP20 | sequence_no=20 | OP20_PACKAGING               | PACKAGING_01 | COLOR_CLASSIFIED_BOX -> PACKAGED_PRODUCT     | input -> output_good   | scrap=output_scrap | auto_complete_pending_approval | active=true
```

Station event sources:

```text
ASSEMBLY_01  | COLOR_SENSOR_ENTRY | sensor | mqtt  | mes/stations/ASSEMBLY_01/sources/COLOR_SENSOR_ENTRY/events | active=true
ASSEMBLY_01  | KIOSK_OPERATOR     | kiosk  | kiosk |                                                         | active=true
ASSEMBLY_01  | ROBOT_ARM_DROP     | robot  | mqtt  | mes/stations/ASSEMBLY_01/sources/ROBOT_ARM_DROP/events  | active=true
PACKAGING_01 | KIOSK_OPERATOR     | kiosk  | kiosk |                                                         | active=true
```

Operation steps:

```text
ROUTE_BOX_PACKAGING_V1_OP10 | 10 | COLOR_SENSOR_ENTRY_EVIDENCE   | auto_start     | auto_finish     | sensor   | approval_required_after_finish=false | active=true
ROUTE_BOX_PACKAGING_V1_OP10 | 20 | ROBOT_ARM_DROP_COMPLETED      | implicit_start | auto_finish     | robot    | approval_required_after_finish=false | active=true
ROUTE_BOX_PACKAGING_V1_OP10 | 30 | OPERATOR_OBSERVATION_APPROVAL | implicit_start | manual_finish   | operator | approval_required_after_finish=true  | active=true
ROUTE_BOX_PACKAGING_V1_OP20 | 10 | PACKAGING_START               | manual_start   | implicit_finish | operator | approval_required_after_finish=false | active=true
ROUTE_BOX_PACKAGING_V1_OP20 | 20 | PACKAGING_FINAL_APPROVAL      | implicit_start | manual_finish   | operator | approval_required_after_finish=true  | active=true
```

Note: the item verification uses the actual seeded `item_code` values
`RAW_BOX`, `COLOR_CLASSIFIED_BOX`, and `PACKAGED_PRODUCT`. The `ITEM_*` values
are the corresponding `item_id` values.

## Expected Counts

```text
items = 3
process_routes = 1
route_operations = 2
station_event_sources = 4
operation_steps = 5
```

## No-Runtime / No-Event / No-Flow Data Check

```text
work_order_operation_execution_state = 0
work_order_operation_steps = 0
operation_events = 0
operation_approvals = 0
production_flow_events = 0
```

## Station/Location Baseline Check

Station/location baseline after apply:

```text
locations = 8
active_station_location_bindings = 8
```

## Health / Limited Regression

Health after apply:

```json
{
  "status": "ok",
  "time": "2026-07-09T09:00:59.076+00:00"
}
```

Feature-flag-disabled API behavior:

```text
GET /api/v2/locations -> 503
```

Kiosk static GET checks:

```text
GET /kiosk -> 200
GET /static/kiosk.js -> 200
GET /static/kiosk.css -> 200
```

No Kiosk POST, start, complete, queue, or operation lifecycle smoke was run.

## Guardrails

- No `docker compose down -v`.
- No Docker volume removal.
- No container destroy/recreate.
- No SQL migration file edit.
- No Python/API/CMD/Compose/Dockerfile change.
- No MESQL push/pull.
- No work order mutation.
- No station queue mutation.
- No operation lifecycle mutation.
- No runtime engine implementation.
- No Kiosk dynamic action implementation.
- No IoT adapter implementation.
- No OEE/KPI implementation.
- No inventory movement/balance implementation.
- No commit/push.

## Result

PASS.

`005_station_execution_seed_minimal.sql` was applied and verified on local
PostgreSQL. The seed populated only station execution master/config tables.
Runtime/event/flow tables remained empty, station/location baseline remained
8/8, and health/limited regression checks passed.
