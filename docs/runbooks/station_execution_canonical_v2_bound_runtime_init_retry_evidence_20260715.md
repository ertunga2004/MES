# Canonical V2 Bound Runtime Initialization Retry Evidence

## Summary

- Date: `2026-07-15`.
- Result: `PASS`.
- Existing-state route identity is guarded before binding lookup.
- The accepted initialization state was verified as
  `ready + current_step_code=NULL + all steps pending`.
- Every migration, seed, binding write, and runtime helper call targeted only
  disposable clone `mes_bound_runtime_init_retry_20260715_094604`.
- Source `mes` remained unchanged and the clone was dropped.

## Prior Failure

- Prior FAIL evidence:
  `docs/runbooks/station_execution_canonical_v2_bound_runtime_init_isolated_smoke_evidence_20260714.md`.
- The prior run rejected `current_step_code=NULL` and found no existing-state
  wrong-route guard. The prior evidence file was not modified.

## Acceptance Reclassification

- `execution_status=ready`, `current_step_code=NULL`, and three pending runtime
  steps is the accepted initialization state.
- The first pending step remains discoverable through the ordered runtime-step
  read; initialization does not activate it or create start evidence.

## Route-Guard Fix Commit

- Base binding-validation commit: `e39d32f`.
- Route-identity guard fix:
  `6d3f827 fix: validate existing execution route identity`.
- Committed files were exactly:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Public `initialize_execution_state` signature remained unchanged.
- Stored route mismatch raises
  `409 EXECUTION_STATE_ROUTE_OPERATION_MISMATCH` before binding lookup.
- Matching stored identity and historical identity-absent replay behavior were
  preserved. No duplicate commit or push was produced.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `181` tests, `OK`.
- Combined station-execution-config API, station-location API, and MESQL V2:
  `217` tests, `OK`.
- `git diff --check` for the two implementation paths: `PASS`.
- Existing FastAPI `on_event` deprecation warnings did not fail tests.

## Source Database

- Container / database / host port: `mes_postgres` / `mes` / `5433`.
- Source binding table before and after: absent.
- Source Canonical V2 route count before and after: `0`.
- No source migration, seed, binding helper, runtime-init call, or binding row
  insert occurred.

## Backup

- Logical dump:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_bound_runtime_init_retry_smoke_20260715-094604.sql`.
- Size: `2,881,697` bytes.
- PostgreSQL database-dump header: present.
- Password was obtained from the existing local environment without terminal
  output. The host backup was preserved after cleanup.

## Source Baseline

The baseline used a read-only transaction and the required deterministic
`to_jsonb(t)::text`, pipe-delimited MD5 expression.

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

- Operation: `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Stored route: `ROUTE_BOX_PACKAGING_V1_OP10`.
- Execution status / current step / final step:
  `active / OPERATOR_OBSERVATION_APPROVAL / pending`.
- Event / approval / production-flow counts: `4 / 0 / 0`.

## Isolation Strategy

- Clone: `mes_bound_runtime_init_retry_20260715_094604`.
- It was created empty from `template0` and restored from the new logical dump.
- `TEMPLATE mes` was not used.
- Exact-name, required-prefix, and `database != mes` guards were applied before
  clone writes and helper calls.

## Clone Restore Verification

- Restore used `ON_ERROR_STOP=1` and completed successfully.
- Binding table absent and V2 route count `0` after restore.
- Source/clone count equality: `15/15`.
- Source/clone digest equality: `15/15`.

## Historical Grandfathering

- Retained operation requested stored route
  `ROUTE_BOX_PACKAGING_V1_OP10` at `ASSEMBLY_01` before migration.
- Result: `initialized=false`; response route remained V1.
- Binding table was absent, no `UndefinedTable` occurred, and therefore the
  existing-state path had no binding-table dependency.
- State, three runtime steps, timestamps/references, events, approvals, flow,
  lifecycle, and queue snapshots were unchanged.

## Runtime Candidate

- Work order: `WO-E2E-SARI-001`.
- Operation: `7db278d4-2246-45d8-8d0f-18618113d7f7`.
- Station / operation code / sequence / status:
  `ASSEMBLY_01 / OP-ASSEMBLY / 10 / queued`.
- Deterministic status-priority and UUID ordering selected the candidate.
- Retained V1 was excluded. No fixture, insert, or status change was made.

## Pre-Migration New-Init Missing-Table Test

- Requested route: `ROUTE_BOX_PACKAGING_V1_OP10`.
- Exception: `psycopg.errors.UndefinedTable`; SQLSTATE `42P01`.
- The error was not converted to a binding-required domain error.
- Candidate state / steps / events / approvals / flow remained
  `0 / 0 / 0 / 0 / 0`; lifecycle and queue were unchanged.

## Binding Migration Apply

- Apply database: `mes_bound_runtime_init_retry_20260715_094604` only.
- Migration: `db/migrations/009_work_order_operation_route_binding.sql`.
- Transaction and embedded assertions: `PASS`.
- Table exists; columns / constraints / indexes: `9 / 9 / 4`.
- Initial binding rows: `0`.

## Canonical V2 Seed Apply

- Apply database: the same disposable clone only.
- Seed: `db/migrations/006_station_execution_seed_canonical_v2.sql`.
- V2 route / operations / steps: `1 / 2 / 4`.
- OP10 / OP20 steps: `3 / 1`.
- Configured / resolved location roles: `5 / 5`.
- V1 config remained `1 / 2 / 5` with identical digests.
- Runtime, audit, binding, lifecycle, and queue snapshots were unchanged.

## Missing Binding Verification

- Unbound candidate requested `ROUTE_BOX_PACKAGING_V2_OP10`.
- Result: `409 WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED`.
- Candidate state / steps / binding / events / approvals / flow remained
  `0 / 0 / 0 / 0 / 0 / 0`.
- No route inference or automatic binding occurred.

## Clone-Only Explicit V2 Binding

- Binding ID: `BINDING-V2-OP10-RUNTIME-INIT-RETRY-20260714-001`.
- Route: `ROUTE_BOX_PACKAGING_V2_OP10`.
- Source / actor: `manual_setup / SMOKE_TEST`.
- First create / exact replay: `true / false`.
- Binding count / digest: `1 / 515ff550201fafe6b0b450d712d09f4f`.
- Binding PK: `1`; `bound_at` and `created_at` both remained
  `2026-07-15T06:51:23.876924+00:00` on replay.
- Metadata remained exactly:
  `{"purpose":"canonical_v2_runtime_init_retry_smoke","production_mapping_asserted":false,"disposable_clone_only":true}`.
- This clone-only binding verifies runtime initialization behavior.
  It is not accepted as a production semantic mapping.
- The clone-only binding does not establish a production semantic mapping.

## New-State Binding Mismatch

- V1 OP10 station was confirmed as `ASSEMBLY_01`.
- Bound route / requested route:
  `ROUTE_BOX_PACKAGING_V2_OP10 / ROUTE_BOX_PACKAGING_V1_OP10`.
- Result: `409 WORK_ORDER_OPERATION_ROUTE_BINDING_MISMATCH`.
- State/steps remained absent; binding, lifecycle, queue, config, and audit
  snapshots were unchanged.

## Matching V2 Initialization

- Result: `initialized=true`.
- Execution status / current step / completion policy:
  `ready / NULL / auto_close_on_required_steps`.
- Stored metadata route: `ROUTE_BOX_PACKAGING_V2_OP10`.
- Runtime steps, in order:
  - `COLOR_SENSOR_ENTRY_EVIDENCE`
  - `ROBOT_ARM_DROP_COMPLETED`
  - `PROCESS_END_OBSERVATION`
- All three were `pending`, with null start/completion timestamps and event
  references.
- Observation config read from the operation-step config was exactly
  `manual_start / manual_finish / true / true / false / operator`.
- An initial verifier looked for those config fields inside runtime-step
  metadata after the successful init and exited with `KeyError`; the follow-up
  verifier read the proper operation-step config, re-snapshotted the persisted
  state, and completed all remaining assertions. No helper or database error
  occurred in the initialization itself.

## Ready-State Semantics

- `ready + current_step_code=NULL + all steps pending` is the accepted
  initialization state.
- No step was activated and no start timestamp or event was written.

## First-Pending Step Read

- First ordered step: `COLOR_SENSOR_ENTRY_EVIDENCE`.
- Status: `pending`.
- State `current_step_code`: `NULL`.

## Exact Duplicate Initialization

- Exact V2 replay: `initialized=false`.
- Response route: `ROUTE_BOX_PACKAGING_V2_OP10`.
- Candidate state / step counts remained `1 / 3`.
- State, step, timestamp/reference, binding, lifecycle, queue, config, and
  audit snapshots were unchanged.

## Existing-State Wrong-Route Guard

- Stored / requested route:
  `ROUTE_BOX_PACKAGING_V2_OP10 / ROUTE_BOX_PACKAGING_V1_OP10`.
- Real PostgreSQL result:
  `409 EXECUTION_STATE_ROUTE_OPERATION_MISMATCH`.
- No `initialized=false` replay was returned.
- Candidate state/step and binding digests remained unchanged; audit remained
  `0 / 0 / 0`, and lifecycle/queue/config remained unchanged.
- Code review and unit regression verified that this existing-state path does
  not query the binding table.

## Post-Error Correct-Route Replay

- Correct V2 call after the wrong-route exception returned
  `initialized=false` and V2 response identity.
- State, steps, and binding were unchanged; no transaction/connection error
  leaked into the later call.

## Runtime Mutation Scope

- Matching init delta:
  - `mes.work_order_operation_execution_state`: `+1`
  - `mes.work_order_operation_steps`: `+3`
- Event / approval / production-flow delta: `0 / 0 / 0`.
- Binding / work-order / operation / queue / config / location delta:
  `0 / 0 / 0 / 0 / 0 / 0`.
- No step start, finish, or event helper was called.

## Binding and Config Integrity

- Binding count/digest stayed
  `1 / 515ff550201fafe6b0b450d712d09f4f` through initialization and replay/error
  calls.
- Final V2 config remained exactly `1 / 2 / 4`, OP10/OP20 `3 / 1`, with roles
  `5 / 5`; V1 remained unchanged.

## Lifecycle and Queue Integrity

- Candidate lifecycle / queue remained `queued / queued`.
- Work orders / operations / station queue retained source-restored counts and
  digests: `12 / 8 / 13`, all unchanged.

## Clone Cleanup

- Exact clone connections were terminated by guarded `dropdb --force`.
- Clone dropped: yes.
- Remaining databases matching `mes_bound_runtime_init_retry_%`: `0`.
- Container `/tmp` migration/seed copies were removed; host backup remains.

## Source Final Integrity

- A new source read-only transaction confirmed binding table absent and V2
  route count `0`.
- Baseline/final counts: `15/15` equal.
- Baseline/final digests: `15/15` equal.
- Retained V1 remained `active / OPERATOR_OBSERVATION_APPROVAL / pending`, with
  event / approval / production-flow counts `4 / 0 / 0`.
- Unintended source mutation: `0`.

## Health

- `GET http://127.0.0.1:8080/health`: `status=ok`.
- No Docker rebuild, recreate, restart, down, or volume operation occurred.

## Guardrails

- Source `mes` remained unchanged.
- Migration, V2 seed, explicit binding, and runtime calls occurred only on the
  exact disposable clone.
- The clone-only binding is not a production mapping.
- No lifecycle fixture, first-step activation, automatic binding, inference,
  step execution, work-order release, API/Kiosk/IoT/Observer/OEE, approval,
  production-flow, inventory, MESQL, or FERP operation occurred.
- No retry evidence or `CURRENT_STATE.md` commit was created.
- No push, reset, rebase, or amend was performed.
- `.agents/` was not intentionally read or changed.

## Result

`PASS`

All revised acceptance criteria, isolation boundaries, mutation-scope checks,
source final-integrity checks, cleanup checks, and health checks passed.
