# Station Execution Schema Migration Evidence

## Summary

Result: `PASS`

`db/migrations/004_station_execution_schema.sql` was applied to the local
PostgreSQL database on 2026-07-09 after pre-apply checks, backup, and destructive
keyword review.

The migration created the station execution schema tables only. It did not seed
data, mutate existing operation lifecycle state, create inventory movement or
balance records, or run MESQL sync.

## Files

- Applied migration: `db/migrations/004_station_execution_schema.sql`
- Apply runbook:
  `docs/runbooks/station_execution_schema_migration_apply_runbook.md`
- Evidence file:
  `docs/runbooks/station_execution_schema_migration_evidence_20260709.md`
- Current state checkpoint:
  `docs/architecture/CURRENT_STATE.md`

## Backup

Backup path:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_004_station_execution_schema_20260709-111429.sql
```

Backup verification:

```text
Test-Path = True
Length = 5654876 bytes
LastWriteTime = 2026-07-09 11:14:29 Europe/Istanbul
```

## Pre-Apply Checks

Git status:

```text
## main...origin/main
```

Required files:

```text
db/migrations/004_station_execution_schema.sql = True
docs/runbooks/station_execution_schema_migration_apply_runbook.md = True
```

Container status:

```text
mes_adminer  Up
mes_postgres Up, healthy
mes_web      Up
```

Note: the local Docker CLI did not expose `docker compose`; `docker-compose -f
docker\mes\compose.portable.yaml ps` was used for the read-only status check.

Health before apply:

```json
{"status":"ok","time":"2026-07-09T08:13:33.430+00:00"}
```

Baseline prerequisite tables:

```text
locations
station_location_bindings
stations
work_order_operations
work_orders
```

Station/location baseline before apply:

```text
locations = 8
active_station_location_bindings = 8
```

## Destructive Keyword Check

Command checked for:

```text
DROP TABLE
DROP COLUMN
ALTER TABLE.*DROP
TRUNCATE
DELETE FROM
UPDATE mes.work_order_operations
UPDATE mes.station_queue
UPDATE mes.locations
UPDATE mes.station_location_bindings
```

Result:

```text
No matches
```

## Migration Apply Result

Apply command source:

```text
db/migrations/004_station_execution_schema.sql
```

Result:

```text
PASS
CREATE SCHEMA
CREATE TABLE / CREATE INDEX statements completed
NOTICE: schema "mes" already exists, skipping
```

No retry, rollback, drop, seed, or lifecycle operation was performed.

## Schema Verify

Expected 10 tables were verified:

```text
items
operation_approvals
operation_events
operation_steps
process_routes
production_flow_events
route_operations
station_event_sources
work_order_operation_execution_state
work_order_operation_steps
```

Result:

```text
10 rows
PASS
```

## Constraint Verify

The runbook query using `ORDER BY table_name::text` failed because the alias
cannot be cast in that `ORDER BY` form. A follow-up query using
`pg_class.relname` and `pg_namespace.nspname` verified constraints for the same
10 target tables.

Result:

```text
110 constraints verified across the target tables
PASS
```

Verified constraint types included:

```text
p = primary key
u = unique
f = foreign key
c = check
```

## Index Verify

Index verification returned indexes for all 10 target tables.

Result:

```text
70 indexes verified across the target tables
PASS
```

Representative indexes verified:

```text
ix_mes_items_active_item_code
ix_mes_process_routes_code_active
ix_mes_route_operations_route_sequence
ix_mes_operation_steps_route_active_step
ix_mes_station_event_sources_station_active
ix_mes_operation_execution_state_station_status
ix_mes_work_order_operation_steps_operation_status_step
ix_mes_operation_events_station_event_time
ix_mes_operation_approvals_operation_type_approved_at
ix_mes_production_flow_events_output_location_event_time
```

## Idempotency Index Verify

Required station/event idempotency indexes were verified:

```text
ux_mes_operation_events_idempotency_key
ux_mes_operation_events_station_source_external
```

Additional station event-time index also matched the broad station-code filter:

```text
ix_mes_operation_events_station_event_time
```

Result:

```text
PASS
```

## Location FK Check

Query:

```text
production_flow_events constraints whose definition contains locations
```

Result:

```text
0 rows
PASS
```

`production_flow_events.input_location_code` and
`production_flow_events.output_location_code` remain semantic references. They
are not DB-level foreign keys to `mes.locations(location_code)`.

## No-Seed / No-Data-Mutation Check

All new tables were empty after apply:

```text
items = 0
operation_approvals = 0
operation_events = 0
operation_steps = 0
process_routes = 0
production_flow_events = 0
route_operations = 0
station_event_sources = 0
work_order_operation_execution_state = 0
work_order_operation_steps = 0
```

Result:

```text
PASS
```

## Station/Location Baseline Check

Station/location baseline after apply:

```text
locations = 8
active_station_location_bindings = 8
```

Result:

```text
PASS
```

## Health / Limited Regression

Health after apply:

```json
{"status":"ok","time":"2026-07-09T08:16:14.320+00:00"}
```

Station/location read-only API default-disabled check:

```text
GET /api/v2/locations -> 503
```

Kiosk static HTTP GET smoke:

```text
GET /kiosk -> 200
GET /static/kiosk.js -> 200
GET /static/kiosk.css -> 200
```

Operation lifecycle smoke was not run. No Kiosk action POST, start/complete, or
queue mutation was performed.

Result:

```text
PASS
```

## Guardrails

- Seed SQL was not run.
- Seed data was not inserted.
- Python/API/JS/HTML/CSS code was not changed.
- Kiosk dynamic action was not implemented.
- Runtime engine was not implemented.
- IoT adapter was not implemented.
- OEE/KPI implementation was not added.
- Inventory movement/balance was not implemented.
- MESQL push/pull was not run.
- Operation lifecycle start/complete smoke was not run.
- `work_order_operations.status` was not mutated.
- `station_queue` was not mutated.
- `mes.locations` was not mutated.
- `mes.station_location_bindings` was not mutated.
- `docker compose down -v` was not run.
- Docker volumes were not removed.
- Commit/push was not performed.
- `.agents/` was not read, changed, moved, deleted, staged, or created under.

## Result

```text
PASS
```
