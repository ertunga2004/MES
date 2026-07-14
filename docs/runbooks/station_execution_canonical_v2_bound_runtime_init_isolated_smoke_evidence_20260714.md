# Canonical V2 Bound Runtime Initialization Isolated Smoke Evidence

## Result

`FAIL`

Two binding acceptance criteria were not satisfied:

1. A successful matching V2 initialization stored `current_step_code = NULL`
   instead of `COLOR_SENSOR_ENTRY_EVIDENCE`.
2. After that initialization, a request for
   `ROUTE_BOX_PACKAGING_V1_OP10` was accepted as an existing-state
   `initialized=false` replay instead of being rejected by a route-identity
   guard.

All other tested binding, isolation, mutation-scope, and source-integrity
checks passed. Because the result is not PASS, `CURRENT_STATE.md` was not
updated with a verified-state section.

## Repository Baseline

- Initial HEAD: `3e39682 docs: record work-order route-operation binding write smoke`.
- Initial branch: `main`, ahead of `origin/main` by 19 commits.
- Initial modifications were exactly:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- No staged or unexpected files existed.
- `.agents/` was not read, listed, searched, or changed.

## Implementation Closure

- Commit: `e39d32f feat: validate runtime init route-operation bindings`.
- Committed files were exactly the two implementation/test files above.
- A duplicate implementation commit was not present, so the required commit
  was created once.
- No amend, reset, rebase, or push was performed.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `169` tests, `OK`.
- Combined station-execution-config API, station-location API, and MESQL V2:
  `205` tests, `OK`.
- `git diff --check` on the two implementation paths: `PASS`.
- Existing FastAPI `on_event` deprecation warnings were observed; no test
  failed.
- Public signature remained:
  `initialize_execution_state(config, work_order_operation_id, route_operation_id, station_code, actor_id=None)`.
- Required and mismatch errors were both implemented as HTTP/domain status
  `409`; runtime initialization contained no binding insert/update/delete.

## Source Database

- Container/database/host port: `mes_postgres` / `mes` / `5433`.
- Binding table before smoke: absent.
- Canonical V2 route count before smoke: `0`.
- Source migration, seed, binding helper, and runtime-init calls: none.
- Logical backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_bound_runtime_init_isolated_smoke_20260714-142911.sql`.
- Backup size: `2,886,710` bytes.
- Header: PostgreSQL database dump.

The required `to_jsonb(t)::text`, pipe-delimited deterministic digest was used.

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

Retained V1 operation
`c8f0be13-9dc7-4e66-9fbb-43547a5f1808` was `active`, at
`OPERATOR_OBSERVATION_APPROVAL`, with final step `pending` and event / approval /
production-flow counts `4 / 0 / 0`. Its state metadata identified
`ROUTE_BOX_PACKAGING_V1_OP10`; this identity was read rather than inferred.

## Isolation

- Clone: `mes_bound_runtime_init_smoke_20260714_142911`.
- It was created empty from `template0`, not from `TEMPLATE mes`.
- The source logical dump was restored with `ON_ERROR_STOP=1`.
- Binding table after restore: absent; V2 route count: `0`.
- Existing-table count equality: `15/15`.
- Existing-table digest equality: `15/15`.
- Every migration, seed, binding write, and runtime-init/error call targeted
  the exact guarded clone name only.

## Historical Grandfathering

- Retained operation: `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Route operation: `ROUTE_BOX_PACKAGING_V1_OP10`.
- Result: `initialized=false`.
- No binding lookup was required: the binding table was absent and no
  `UndefinedTable` occurred.
- State, current step, three runtime steps and their timestamps/references,
  event/approval/flow rows, lifecycle row, and queue row were digest-equal
  before and after the call.

## Runtime Candidate

- Work order: `WO-E2E-SARI-001`.
- Operation: `7db278d4-2246-45d8-8d0f-18618113d7f7`.
- Station / operation code / sequence / status:
  `ASSEMBLY_01` / `OP-ASSEMBLY` / `10` / `queued`.
- The candidate was selected by the required status-priority and UUID order.
- The retained V1 target was excluded.
- No lifecycle/work-order/operation fixture was created and no status was
  changed.

## Pre-Migration New Initialization

- Requested route: `ROUTE_BOX_PACKAGING_V1_OP10`.
- Exception: `psycopg.errors.UndefinedTable`.
- SQLSTATE: `42P01`.
- It was not converted to `WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED`.
- Candidate state/step/event/approval/flow remained `0 / 0 / 0 / 0 / 0`;
  lifecycle and queue digests were unchanged.

## Binding Migration

- Apply database: `mes_bound_runtime_init_smoke_20260714_142911` only.
- Migration: `db/migrations/009_work_order_operation_route_binding.sql`.
- Result: committed successfully.
- Table shape: `9` columns / `9` constraints / `4` indexes.
- Initial binding rows: `0`.

## Canonical V2 Seed

- Seed: `db/migrations/006_station_execution_seed_canonical_v2.sql`.
- Apply database: disposable clone only.
- Result: committed successfully.
- V2 route / operations / steps: `1 / 2 / 4`.
- OP10 / OP20 steps: `3 / 1`.
- Configured / resolved location roles: `5 / 5`.
- Exact route-operation IDs:
  `ROUTE_BOX_PACKAGING_V2_OP10` and `ROUTE_BOX_PACKAGING_V2_OP20`.
- V1 config counts/digests remained `1 / 2 / 5` and exactly unchanged.
- Seed did not change runtime, audit, binding, lifecycle, or queue rows.

## Missing Binding

- Requested route: `ROUTE_BOX_PACKAGING_V2_OP10`.
- Result: `409 WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED`.
- Candidate state/step rows remained `0 / 0`.
- No event, approval, production-flow, inference, or automatic binding was
  produced; the full 16-table snapshot was unchanged.

## Explicit V2 Binding

- Binding ID: `BINDING-V2-OP10-RUNTIME-INIT-20260714-001`.
- Candidate / route:
  `7db278d4-2246-45d8-8d0f-18618113d7f7` /
  `ROUTE_BOX_PACKAGING_V2_OP10`.
- Source / actor: `manual_setup` / `SMOKE_TEST`.
- First create / exact replay: `true / false`.
- Row count: `1`.
- Binding PK: `1`.
- `bound_at` and `created_at` were both
  `2026-07-14T11:35:19.196484+00:00` and remained unchanged on replay.
- Metadata matched exactly:
  `{"purpose":"canonical_v2_runtime_init_smoke","production_mapping_asserted":false,"disposable_clone_only":true}`.
- Binding digest after creation and through initialization:
  `e8f2fc6d329bba14fa8ec4f8e1ea351d`.
- This clone-only row does not assert a production semantic mapping.

## Binding Mismatch

- Requested route / station:
  `ROUTE_BOX_PACKAGING_V1_OP10` / `ASSEMBLY_01`.
- Result: `409 WORK_ORDER_OPERATION_ROUTE_BINDING_MISMATCH`.
- Candidate state/step rows remained `0 / 0`.
- Binding, event, approval, flow, lifecycle, queue, and config snapshots were
  unchanged.

## Matching V2 Initialization

- Result: `initialized=true`.
- Execution status: `ready`.
- Completion policy: `auto_close_on_required_steps`.
- State metadata route: `ROUTE_BOX_PACKAGING_V2_OP10`.
- Runtime step count: `3`.
- Exact step order:
  - `COLOR_SENSOR_ENTRY_EVIDENCE`
  - `ROBOT_ARM_DROP_COMPLETED`
  - `PROCESS_END_OBSERVATION`
- All three steps were `pending`; started/completed timestamps and event
  references were null.
- Observation config was exactly `manual_start / manual_finish / true / true /
  false / operator`.
- Binding count/digest did not change.
- Acceptance failure: state `current_step_code` was `NULL`, not
  `COLOR_SENSOR_ENTRY_EVIDENCE`.

## Duplicate Initialization

- Exact V2 replay result: `initialized=false`.
- Candidate state / step counts remained `1 / 3`.
- State and step timestamps, status, policy, metadata, references, binding
  count/digest, lifecycle, queue, config, and audit snapshots were unchanged.

## Existing-State Wrong-Route Guard

- Requested route after correct initialization:
  `ROUTE_BOX_PACKAGING_V1_OP10` at `ASSEMBLY_01`.
- Actual result: `initialized=false`, `status=ok`; no error code was returned.
- Stored state and runtime-step metadata still identified V2, while the return
  envelope reported the requested V1 route.
- State, steps, and binding were not mutated.
- Phase 4I unit acceptance requires the existing-state grandfather path to
  avoid binding lookup, but it does not establish a route-identity comparison.
  Phase 4J explicitly requires an established runtime not to accept the wrong
  route as an idempotent replay. The implementation has no such guard, so this
  is an acceptance conflict and is recorded as `FAIL`.

## Mutation Scope

- Matching init changed only:
  - `mes.work_order_operation_execution_state`: `+1`
  - `mes.work_order_operation_steps`: `+3`
- Event / approval / production-flow deltas: `0 / 0 / 0`.
- Binding delta during init: `0`.
- Work order, operation lifecycle, station queue, config/master, locations,
  items, and station-location binding deltas during init: `0`.
- Candidate lifecycle and queue statuses remained `queued / queued`.
- No step start, finish, or event helper was called.

## Cleanup

- Exact clone connections were terminated by `dropdb --force` as needed.
- Clone dropped: yes.
- Remaining databases matching `mes_bound_runtime_init_smoke_%`: `0`.
- Container `/tmp` dump/migration/seed copies were removed.
- Host logical backup was preserved.

## Source Final Integrity

- Verification used a new source read-only transaction.
- Binding table exists: `false`.
- Canonical V2 route count: `0`.
- Baseline/final counts: `15/15` equal.
- Baseline/final digests: `15/15` equal.
- Retained V1 remained `active` at `OPERATOR_OBSERVATION_APPROVAL`, final step
  `pending`, with event / approval / production-flow counts `4 / 0 / 0`.
- Unintended source mutation: `0`.

## Health

- `GET http://127.0.0.1:8080/health`: `status=ok`.
- No Docker rebuild, recreate, restart, down, or volume operation occurred.

## Documentation

- Evidence: this uncommitted file.
- `docs/architecture/CURRENT_STATE.md`: intentionally unchanged because the
  isolated acceptance result is `FAIL`.
- Evidence commit: not created.
- Push: not performed.

## Guardrails

- Source `mes` remained unchanged.
- Migration, V2 seed, binding, and runtime initialization occurred only on the
  disposable clone.
- No lifecycle fixture, automatic binding, inference, step execution,
  work-order release, API/Kiosk/IoT/Observer/OEE, approval, production-flow,
  inventory, MESQL, or FERP operation occurred.
- The clone-only binding was not treated as a production mapping.
- `.agents/` was not touched.
