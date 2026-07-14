# Work-Order Route-Operation Binding Read Helper Isolated Smoke Evidence

## Summary

- Date: `2026-07-14`.
- Result: `PASS`.
- Phase 4E's two binding read helpers were reviewed, regression-tested, and
  committed as the only implementation change.
- Real PostgreSQL behavior was verified only on disposable database
  `mes_binding_read_smoke_20260714_133559`.
- Source database `mes` received no migration, fixture, or helper call.

## Implementation Commit

- Commit: `6e7a880 feat: add work-order route-operation binding read helpers`.
- Committed files:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Public helpers:
  - `get_work_order_operation_route_binding`
  - `get_work_order_operation_route_binding_by_id`
- SQL constants:
  - `SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL`
  - `SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_BY_ID_SQL`
- UUID validator: `_required_uuid_text`.
- Acceptance review found exactly two public binding read helpers and no
  binding write/list/rebind helper, runtime resolver, API route, feature flag,
  or inference implementation.
- Both queries are parameterized `SELECT` statements over only
  `mes.work_order_operation_route_bindings`, select the explicit nine-column
  shape, and contain no star, join, lock, or write DDL/DML.
- Duplicate commit avoided: yes. Push: not performed.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `106` tests, `OK`.
- Combined station-execution-config API, station-location API, and MESQL V2:
  `142` tests, `OK`.
- `git diff --check` for the two implementation files: `PASS`.
- Only existing FastAPI `on_event` deprecation warnings were observed.

## Source Database

- Container: `mes_postgres`.
- Database: `mes`.
- Host port: `5433`.
- Target guard confirmed `current_database() = mes` before backup/baseline.
- `mes.work_order_operation_route_bindings` existed before smoke: `false`.
- No helper was called against source `mes`.

## Backup

- Logical dump:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_binding_read_helper_isolated_smoke_20260714-133559.sql`.
- Size: `2,881,697` bytes.
- PostgreSQL database-dump header: present.
- `--no-owner --no-privileges` was used; the password was not printed.
- The host backup was preserved after clone cleanup.

## Source Baseline

The source baseline was captured in a read-only transaction with the required
deterministic JSONB digest expression.

| Table | Count | MD5 digest |
|---|---:|---|
| `mes.items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `mes.process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` |
| `mes.route_operations` | 2 | `92a859fc57182954c5070670928c89e6` |
| `mes.operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` |
| `mes.station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `mes.work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `mes.work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `mes.operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` |
| `mes.operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` |
| `mes.work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` |
| `mes.station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` |
| `mes.locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `mes.station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` |

## Retained V1 Baseline

- Work-order operation:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Execution status: `active`.
- Current step: `OPERATOR_OBSERVATION_APPROVAL`.
- Final step status: `pending`.
- Event / approval / production-flow counts: `4 / 0 / 0`.

## Isolation Strategy

- Clone: `mes_binding_read_smoke_20260714_133559`.
- The exact lowercase ASCII name was guarded by the
  `mes_binding_read_smoke_` prefix and explicit `database != mes` checks.
- The clone was created empty from `template0`, then restored from the source
  logical dump. `CREATE DATABASE ... TEMPLATE mes` was not used.
- Migration, fixture insertion, and every real helper call targeted only this
  exact disposable clone.

## Clone Restore Verification

- Restore completed with `ON_ERROR_STOP=1`.
- Binding table before migration: absent.
- Existing-table count equality: `15/15`.
- Existing-table digest equality: `15/15`.

## Pre-Migration Missing-Table Test

- Valid clone operation UUID:
  `3dec8371-d01d-401e-a435-f441d7701e21`.
- Helper: `get_work_order_operation_route_binding`.
- Propagated exception: `psycopg.errors.UndefinedTable`.
- PostgreSQL SQLSTATE: `42P01`.
- The exception was not swallowed and was not converted to `None`.

## Migration Apply

- Apply database: `mes_binding_read_smoke_20260714_133559` only.
- Migration: `db/migrations/009_work_order_operation_route_binding.sql`.
- SHA-256:
  `B5DA1799A52147433E1DEA44BD989394D720416D352CC7906F8A1729BE1A0162`.
- Transaction commit and embedded exact-shape assertion: `PASS`.
- Table exists: `true`.
- Columns / constraints / indexes: `9 / 9 / 4`.
- Initial binding rows: `0`.

## Fixture Candidate

- Work order: `WO-LOCAL-SUCCESSOR-SMOKE-78d8c903`.
- Work-order operation:
  `3ebd0c44-bb62-4939-a9b5-2f3b2ce6ba1d`.
- Station: `ASSEMBLY_01`.
- Operation code: `OP-ASSEMBLY`.
- Sequence: `10`.
- Status: `completed`.
- The retained V1 target was excluded.
- The candidate had no binding, execution-state row, or operation event; no
  lifecycle fixture or status mutation was created.

## Clone-Only Binding Fixture

- Binding ID: `BINDING-READ-SMOKE-20260714-001`.
- Route operation: `ROUTE_BOX_PACKAGING_V1_OP10`.
- Binding source: `manual_setup`.
- Bound by: `SMOKE_TEST`.
- Metadata:
  `{"purpose":"binding_read_helper_smoke","production_mapping_asserted":false,"disposable_clone_only":true}`.
- Binding row count after the controlled insert: `1`.
- The fixture binding was created only to verify read-helper behavior.
  It is not accepted as a production semantic mapping.
- This was a clone-only read-helper fixture; production semantic mapping not
  asserted.

## Lifecycle-Operation Lookup

- Result: `PASS`, non-null.
- Exact field set (`9`): `binding_pk`, `binding_id`,
  `work_order_operation_id`, `route_operation_id`, `binding_source`,
  `bound_by`, `bound_at`, `metadata`, `created_at`.
- `work_order_operation_id` was the selected UUID serialized as a string.
- Route operation, source, bound-by value, and metadata exactly matched the
  fixture.
- `bound_at`: `2026-07-14T10:38:48.758625+00:00`.
- `created_at`: `2026-07-14T10:38:48.758625+00:00`.
- Both timestamps parsed as ISO strings; no extra fields were returned.

## Binding-ID Lookup

- Exact-ID lookup result: `PASS`, non-null.
- All nine fields equaled the lifecycle-operation lookup result.
- Returned binding ID preserved exact uppercase fixture case.

## Missing-Row Verification

- Missing lifecycle UUID:
  `00000000-0000-0000-0000-000000000001`.
- Pre-check counts in lifecycle operations / bindings: `0 / 0`.
- Lifecycle lookup result: `None`.
- Missing binding ID `BINDING-READ-SMOKE-NOT-FOUND`: `None`.

## Case-Preservation Verification

- Lowercase input `binding-read-smoke-20260714-001`: `None`.
- The helper did not normalize text binding IDs to uppercase or lowercase;
  PostgreSQL exact text equality was preserved.

## Repeated-Read Verification

- Both successful lookups were repeated at least once.
- Result shapes and values remained exactly equal.
- `bound_at` and `created_at` remained exactly equal.
- Binding count remained `1`.
- Binding digest remained `9cdfb87265f0ec7fec068ef34a233503`.

## No-Write Verification

- Pre/post binding count and digest: equal.
- Pre/post existing-table counts: `15/15` equal.
- Pre/post existing-table digests: `15/15` equal.
- Candidate execution-state / step / event / approval / production-flow rows:
  `0 / 0 / 0 / 0 / 0`.
- Fixture insert excluded, helper-created mutations: `0`.
- No lifecycle, queue, configuration, event, approval, production-flow, or
  location mutation was observed.

## Clone Cleanup

- Connections to exact clone were terminated.
- Clone `mes_binding_read_smoke_20260714_133559` was dropped.
- Exact clone existence after drop: `0`.
- Remaining databases matching `mes_binding_read_smoke_%`: none.
- Container `/tmp` dump was removed; host logical backup was preserved.

## Source Final Integrity

- Verification used a new read-only source transaction after clone cleanup.
- Source binding table exists: `false`.
- Baseline/final counts: `15/15` equal.
- Baseline/final digests: `15/15` equal.
- Retained V1 remained `active` at
  `OPERATOR_OBSERVATION_APPROVAL`, final step `pending`, with event / approval /
  production-flow counts `4 / 0 / 0`.
- Unintended source mutation: `0`.

## Health

- `GET http://127.0.0.1:8080/health`: `status=ok`.
- No container rebuild, recreate, restart, down, or volume operation was used.

## Guardrails

- No source migration, source fixture, or source helper call.
- No binding write/update/delete/rebind/list helper.
- No runtime-init or work-order-release integration.
- No route/station/operation/sequence/latest-active inference.
- No lifecycle fixture, step start/finish call, V2 seed apply, API, Kiosk,
  IoT/MQTT, Observer, OEE/KPI, approval, production-flow, inventory, MESQL, or
  FERP change.
- Evidence and `CURRENT_STATE.md` were not committed. No push was performed.
- `.agents/` was not read, listed, searched, or changed.

## Result

`PASS`
