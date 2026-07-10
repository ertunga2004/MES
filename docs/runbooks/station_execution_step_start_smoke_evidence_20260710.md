# Station Execution Step Start Smoke Evidence

## Summary

Runtime Engine V0 Phase 2B `start_execution_step` real local PostgreSQL smoke
PASS on 2026-07-10. The controlled call moved the selected sidecar execution
state and one runtime step from `ready + pending` to `active + active`.

The same external event was replayed once. The replay returned the original
event without inserting a duplicate or mutating state, step timestamps,
references, or `updated_at` values.

## Implementation Commit

- Commit: `1f9d3ee feat: add station execution step start helper`
- Push: not performed.

## Files

- `mes_web/db/mesql_v2.py`
- `tests/test_mes_web_mesql_v2.py`

## Backup

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_step_start_smoke_20260710-083943.sql
```

```text
5778370 bytes
```

The backup was created before the first DB write and was verified to contain a
PostgreSQL dump header.

## Unit Regression

```text
tests.test_mes_web_mesql_v2
Ran 77 tests ... OK

tests.test_mes_web_station_execution_config_api
tests.test_mes_web_station_location_api
tests.test_mes_web_mesql_v2
Ran 113 tests ... OK
```

`git diff --check` for the implementation and test files passed before commit.

## Baseline Counts

```text
execution_state        = 1
execution_steps        = 3
operation_events       = 1
operation_approvals    = 0
production_flow_events = 0
work_orders            = 12
work_order_operations  = 8
station_queue          = 13
```

## Forbidden Table Digests Before

```text
work_orders               | 12 | 283cf9b28e57bc5d6d398169f935473d
work_order_operations     |  8 | fb74f90dcb2460542ad6422609144b6f
station_queue             | 13 | 2760e411b756b4194df0f86e4987cb5a
operation_approvals       |  0 | d41d8cd98f00b204e9800998ecf8427e
production_flow_events    |  0 | d41d8cd98f00b204e9800998ecf8427e
items                     |  3 | c120ee7ee8808e4280bcb02895f76e8c
process_routes            |  1 | 163f416bfdcf16ca469e43adbd47b324
route_operations          |  2 | 92a859fc57182954c5070670928c89e6
operation_steps           |  5 | 3829d1b0a5185a4ac59a509532b4abc8
station_event_sources     |  4 | c70220808f91a8562d14377c47b2a698
locations                 |  8 | 03842ba4695966bbc65a4ec3eac438e9
station_location_bindings |  8 | f5274a415a5d1744af064a539693d0be
```

## Smoke Target

```text
work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808
station_code            = ASSEMBLY_01
route_operation_id      = ROUTE_BOX_PACKAGING_V1_OP10
step_code               = COLOR_SENSOR_ENTRY_EVIDENCE
event_source            = COLOR_SENSOR_ENTRY
external_event_id       = step-start-smoke-20260710-001
```

## Preconditions

Before the first call:

```text
execution_status = ready
current_step_code = null
execution started_at = null
execution last_event_id = null

COLOR_SENSOR_ENTRY_EVIDENCE   | pending
ROBOT_ARM_DROP_COMPLETED      | pending
OPERATOR_OBSERVATION_APPROVAL | pending

smoke_event_count = 0
```

## First Step-Start Call

The host `.venv` executed the committed helper with `actor_id = SMOKE` and a
payload identifying the Phase 2B smoke.

```text
status = ok
started = true
event_inserted = true
event_type = step_start
event_source = COLOR_SENSOR_ENTRY
accepted = true
```

Created event:

```text
event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001
idempotency_key = ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001
work_order_id = WO-E2E-MAVI-001
operation_code = OP10_ASSEMBLY_CLASSIFICATION
work_order_operation_step_id = EXEC_STEP_c8f0be13-9dc7-4e66-9fbb-43547a5f1808_COLOR_SENSOR_ENTRY_EVIDENCE
step_code = COLOR_SENSOR_ENTRY_EVIDENCE
```

## First DB Verification

```text
execution_status = active
current_step_code = COLOR_SENSOR_ENTRY_EVIDENCE
execution started_at = 2026-07-10 05:42:55.159836+00
execution updated_at = 2026-07-10 05:42:55.159836+00
execution last_event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001

target step status = active
step started_at = 2026-07-10 05:42:55.159836+00
step updated_at = 2026-07-10 05:42:55.159836+00
step started_by_event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001
completed_at = null
completed_by_event_id = null

evidence_completed_at = null
pending_final_approval_at = null
closed_at = null
last_approval_id = null
```

The other two runtime steps remained `pending`.

## Duplicate Replay

The identical `external_event_id` was replayed with a different actor and
payload.

```text
status = ok
started = false
event_inserted = false
event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001
```

The returned event retained the original `SMOKE` actor and original payload.

## Duplicate DB Verification

```text
smoke_event_count = 1
execution started_at = 2026-07-10 05:42:55.159836+00
execution updated_at = 2026-07-10 05:42:55.159836+00
execution current_step_code = COLOR_SENSOR_ENTRY_EVIDENCE
execution last_event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001
step started_at = 2026-07-10 05:42:55.159836+00
step updated_at = 2026-07-10 05:42:55.159836+00
step started_by_event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:step-start-smoke-20260710-001
```

All timestamp and first-event references matched the first DB verification.

## Final Counts

```text
execution_state        1 -> 1
execution_steps        3 -> 3
operation_events       1 -> 2
operation_approvals    0 -> 0
production_flow_events 0 -> 0
work_orders            12 -> 12
work_order_operations   8 -> 8
station_queue          13 -> 13
```

## Forbidden Mutation Verification

The row count and digest for every forbidden table exactly matched the baseline:

- `work_orders`, `work_order_operations`, and `station_queue`
- `operation_approvals` and `production_flow_events`
- `items`, `process_routes`, `route_operations`, and `operation_steps`
- `station_event_sources`, `locations`, and `station_location_bindings`

The only DB changes were the new `mes.operation_events` row and the selected
rows in `mes.work_order_operation_execution_state` and
`mes.work_order_operation_steps`.

## Health

```json
{"status":"ok","time":"2026-07-10T05:49:25.580+00:00"}
```

## Cleanup / Retention

No cleanup was performed. The smoke event is retained with
`external_event_id = step-start-smoke-20260710-001`. The target execution
state and `COLOR_SENSOR_ENTRY_EVIDENCE` step remain `active` as the real
baseline for the future finish-step phase.

## Guardrails

- Only the implementation and test files were committed.
- No push, migration, seed, schema change, rebuild, compose recreate, down,
  volume operation, API, Kiosk, IoT, OEE, MESQL, approval, production flow,
  inventory movement, or lifecycle helper action was performed.
- No cleanup was performed.
- `.agents/` was not accessed.

## Result

PASS.
