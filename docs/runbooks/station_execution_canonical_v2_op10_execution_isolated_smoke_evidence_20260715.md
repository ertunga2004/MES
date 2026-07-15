# Canonical V2 OP10 Execution Isolated Smoke Evidence

## Summary

- Date: `2026-07-15`.
- Result: `PASS`.
- Canonical V2 OP10 was initialized and its three configured steps were
  executed in order on a disposable PostgreSQL clone.
- Five unique primary events produced the expected state/step transitions; all
  five exact duplicate calls were idempotent no-ops.
- Final execution state was `closed`, `current_step_code=NULL`, with all three
  required steps `completed`.
- Source `mes` remained unchanged and the disposable clone was dropped.

## Runtime-Init Retry Documentation Commit

- Commit: `6f701b9 docs: record canonical v2 bound runtime init retry`.
- Committed files were exactly:
  - `docs/architecture/CURRENT_STATE.md`
  - `docs/runbooks/station_execution_canonical_v2_bound_runtime_init_retry_evidence_20260715.md`
- Retry evidence date/path and `CURRENT_STATE.md` dates/references were
  normalized to `2026-07-15` before commit.
- No duplicate commit or push was produced.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `181` tests, `OK`.
- Combined station-execution-config API, station-location API, and MESQL V2:
  `217` tests, `OK`.
- Existing FastAPI `on_event` deprecation warnings did not fail tests.
- No Python, test, migration, seed, API, Kiosk, or Docker code changed.

## Source Database

- Container / database / host port: `mes_postgres / mes / 5433`.
- Source binding table before and after: absent.
- Source Canonical V2 route count before and after: `0`.
- No source migration, seed, binding helper, runtime helper, or binding row
  operation occurred.

## Backup

- Logical dump:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_canonical_v2_op10_execution_smoke_20260715-101356.sql`.
- Size: `2,881,697` bytes.
- PostgreSQL database-dump header: present.
- Password was read from the existing secure local environment without being
  printed. The host backup was preserved.

## Source Baseline

The baseline used a read-only transaction and deterministic pipe-delimited
`to_jsonb(t)::text` MD5 digests.

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
- Execution status / current step / final step:
  `active / OPERATOR_OBSERVATION_APPROVAL / pending`.
- Event / approval / production-flow counts: `4 / 0 / 0`.

## Isolation Strategy

- Clone: `mes_canonical_v2_op10_flow_20260715_101356`.
- It was created empty from `template0` and restored from the new source dump.
- `TEMPLATE mes` was not used.
- Exact-name, required-prefix, and `database != mes` guards were applied before
  every clone write/helper stage.

## Clone Restore Verification

- Restore completed with `ON_ERROR_STOP=1`.
- Binding table absent and V2 route count `0` after restore.
- Source/clone count equality: `15/15`.
- Source/clone digest equality: `15/15`.

## Binding Migration Apply

- Applied only to the exact disposable clone.
- Migration: `db/migrations/009_work_order_operation_route_binding.sql`.
- Result: `PASS`.
- Table shape: `9` columns / `9` constraints / `4` indexes.
- Initial binding rows: `0`.

## Canonical V2 Seed Apply

- Applied only to the exact disposable clone.
- Seed: `db/migrations/006_station_execution_seed_canonical_v2.sql`.
- V2 route / operations / steps: `1 / 2 / 4`.
- OP10 / OP20 steps: `3 / 1`.
- Configured / resolved location roles: `5 / 5`.
- V1 config remained `1 / 2 / 5`.
- Seed introduced no runtime, audit, binding, lifecycle, or queue row.

## Runtime Candidate

- Work order: `WO-E2E-SARI-001`.
- Work-order operation: `7db278d4-2246-45d8-8d0f-18618113d7f7`.
- Station / operation code / sequence / status:
  `ASSEMBLY_01 / OP-ASSEMBLY / 10 / queued`.
- Deterministic status-priority and UUID ordering selected the candidate.
- Retained V1 was excluded. No lifecycle fixture, work-order/operation insert,
  or status mutation was made.

## Clone-Only Explicit Binding

- Binding ID: `BINDING-V2-OP10-FLOW-20260715-001`.
- Route: `ROUTE_BOX_PACKAGING_V2_OP10`.
- Source / actor: `manual_setup / SMOKE_TEST`.
- First create / exact replay: `true / false`.
- Binding PK: `1`.
- Binding count / digest: `1 / 33028956362e756054c394a0e097e4b9`.
- `bound_at` and `created_at` both remained
  `2026-07-15T07:17:08.232592+00:00` on replay.
- Metadata remained exactly:
  `{"purpose":"canonical_v2_op10_execution_flow","production_mapping_asserted":false,"disposable_clone_only":true}`.
- The clone-only binding verifies runtime execution behavior.
  It is not accepted as a production semantic mapping.
- The clone-only binding does not establish a production semantic mapping.

## Runtime Initialization

- `initialize_execution_state` returned `initialized=true`.
- Initial state: `ready`, `current_step_code=NULL`.
- Runtime step count: `3`; all three steps were `pending`.
- Exact duplicate init returned `initialized=false` and produced no mutation.

## Pre-Execution Snapshot

- Candidate state / runtime steps: `1 / 3`.
- Initial status / current step: `ready / NULL`.
- Initial step states: `pending / pending / pending`.
- Candidate events / approvals / production flow: `0 / 0 / 0`.
- Binding count/digest, lifecycle, queue, V1/V2 config, master/location rows,
  and all protected-table digests were captured before step execution.

## Canonical OP10 Step Configuration

- Route operation / station / operation code:
  `ROUTE_BOX_PACKAGING_V2_OP10 / ASSEMBLY_01 / ASSEMBLY_COLOR_CLASSIFY`.
- Completion policy: `auto_close_on_required_steps`.
- `COLOR_SENSOR_ENTRY_EVIDENCE`:
  `auto_start / auto_finish`, start/finish source `COLOR_SENSOR_ENTRY`, required.
- `ROBOT_ARM_DROP_COMPLETED`:
  `implicit_start / auto_finish`, finish source `ROBOT_ARM_DROP`, required.
- `PROCESS_END_OBSERVATION`:
  `manual_start / manual_finish`, start/finish source `KIOSK_OPERATOR`, records
  duration, required, no post-finish approval, actor type `operator`.
- Start/finish helpers do not accept an `occurred_at` parameter; event time is
  assigned by PostgreSQL `now()`. Real DB times were therefore used without an
  artificial wait.

## Color Sensor Start

- External event: `v2-op10-color-start-20260715-001`.
- Result: `started=true`, `event_inserted=true`.
- Event type/source: `step_start / COLOR_SENSOR_ENTRY`.
- Execution transitioned `ready -> active`; current step became
  `COLOR_SENSOR_ENTRY_EVIDENCE`.
- Color transitioned `pending -> active`; its start timestamp/reference were
  populated. Other steps remained pending. Event delta: `+1`.

## Color Sensor Start Replay

- Exact event replay returned `started=false`, `event_inserted=false`.
- State, steps, events, binding, audit, lifecycle, queue, and config digests
  were unchanged.

## Color Sensor Finish

- External event: `v2-op10-color-finish-20260715-001`.
- Result: `finished=true`, `event_inserted=true`, `implicit_started=false`.
- Event type/source: `step_finish / COLOR_SENSOR_ENTRY`.
- Color became completed with its first start timestamp/reference preserved.
- Execution remained active and current step advanced to
  `ROBOT_ARM_DROP_COMPLETED`. Event delta from pre-execution: `+2`.

## Color Sensor Finish Replay

- Exact event replay returned `finished=false`, `event_inserted=false`.
- All snapshots were unchanged.

## Robot Implicit-Start Finish

- External event: `v2-op10-robot-finish-20260715-001`.
- Result: `finished=true`, `event_inserted=true`, `implicit_started=true`.
- Event type/source: `step_finish / ROBOT_ARM_DROP`.
- Robot transitioned directly `pending -> completed`.
- Robot `started_at=completed_at` and start/completion event references were
  equal to the same finish event.
- Execution remained active and current step advanced to
  `PROCESS_END_OBSERVATION`. Event delta: `+3`.

## Robot Finish Replay

- Exact event replay returned `finished=false`, `event_inserted=false`.
- All snapshots were unchanged.

## Observation Start

- External event: `v2-op10-observation-start-20260715-001`.
- Actor: `SMOKE_OPERATOR`.
- Result: `started=true`, `event_inserted=true`.
- Event type/source: `step_start / KIOSK_OPERATOR`.
- Observation transitioned `pending -> active`; execution stayed active with
  observation as the current step. Event delta: `+4`.

## Observation Start Replay

- Exact event replay returned `started=false`, `event_inserted=false`.
- All snapshots were unchanged.

## Observation Finish

- External event: `v2-op10-observation-finish-20260715-001`.
- Actor: `SMOKE_OPERATOR`.
- Result: `finished=true`, `event_inserted=true`, `implicit_started=false`.
- Event type/source: `step_finish / KIOSK_OPERATOR`.
- Observation became completed with its first start timestamp/reference
  preserved.
- Real DB duration: `0.202385` seconds; `completed_at >= started_at`.
- All three required steps were completed. Event delta: `+5`.

## Observation Finish Replay

- Exact event replay returned `finished=false`, `event_inserted=false`.
- Closed execution, state/step/event/binding digests, approval/flow,
  lifecycle/queue, and config remained unchanged.

## Completion Policy Result

- Policy: `auto_close_on_required_steps`.
- Execution transition: `active -> closed`.
- Final `current_step_code=NULL`.
- All required steps were completed.
- Additional `system_transition` event count: `0`.

## Runtime State Timeline

| Stage | Status | Current step | Event count |
|---|---|---|---:|
| Initialized | `ready` | `NULL` | 0 |
| Color started | `active` | `COLOR_SENSOR_ENTRY_EVIDENCE` | 1 |
| Color finished | `active` | `ROBOT_ARM_DROP_COMPLETED` | 2 |
| Robot finished | `active` | `PROCESS_END_OBSERVATION` | 3 |
| Observation started | `active` | `PROCESS_END_OBSERVATION` | 4 |
| Observation finished | `closed` | `NULL` | 5 |

## Runtime Step Timeline

| Stage | Color | Robot | Observation |
|---|---|---|---|
| Initialized | `pending` | `pending` | `pending` |
| Color started | `active` | `pending` | `pending` |
| Color finished | `completed` | `pending` | `pending` |
| Robot finished | `completed` | `completed` | `pending` |
| Observation started | `completed` | `completed` | `active` |
| Observation finished | `completed` | `completed` | `completed` |

## Event Ledger Verification

| Event type | Step | Source | External event ID | Actor | Occurred at (UTC) |
|---|---|---|---|---|---|
| `step_start` | `COLOR_SENSOR_ENTRY_EVIDENCE` | `COLOR_SENSOR_ENTRY` | `v2-op10-color-start-20260715-001` | NULL | `2026-07-15T07:17:08.861411+00:00` |
| `step_finish` | `COLOR_SENSOR_ENTRY_EVIDENCE` | `COLOR_SENSOR_ENTRY` | `v2-op10-color-finish-20260715-001` | NULL | `2026-07-15T07:17:09.074049+00:00` |
| `step_finish` | `ROBOT_ARM_DROP_COMPLETED` | `ROBOT_ARM_DROP` | `v2-op10-robot-finish-20260715-001` | NULL | `2026-07-15T07:17:09.257347+00:00` |
| `step_start` | `PROCESS_END_OBSERVATION` | `KIOSK_OPERATOR` | `v2-op10-observation-start-20260715-001` | `SMOKE_OPERATOR` | `2026-07-15T07:17:09.464889+00:00` |
| `step_finish` | `PROCESS_END_OBSERVATION` | `KIOSK_OPERATOR` | `v2-op10-observation-finish-20260715-001` | `SMOKE_OPERATOR` | `2026-07-15T07:17:09.667274+00:00` |

- Event IDs and idempotency keys were derived as
  `OP_EVENT_<station:source:external>` and `<station:source:external>`.
- All five event IDs, external IDs, and idempotency keys were unique.
- Exact event count: `5`; duplicate external-event rows: `0`;
  additional system-transition events: `0`.

## Duplicate-Event Idempotency

- Color start replay: `false / false`.
- Color finish replay: `false / false`.
- Robot finish replay: `false / false`.
- Observation start replay: `false / false`.
- Observation finish replay: `false / false`.
- Each pair reports the transition flag and `event_inserted`; every replay
  preserved complete before/after snapshots.

## Mutation Scope

- After initialization, execution-state row count delta: `0`; the target row
  was updated through the timeline.
- After initialization, runtime-step row count delta: `0`; exactly three target
  rows were updated.
- Operation-event delta: `+5`.
- Only execution state, runtime steps, and operation events changed.
- Approval / production-flow delta: `0 / 0`.

## Binding and Config Integrity

- Binding count/digest remained
  `1 / 33028956362e756054c394a0e097e4b9` through the full flow.
- Items, process routes, route operations, operation steps, station event
  sources, locations, and station-location bindings retained their
  pre-execution counts and digests.

## Lifecycle and Queue Integrity

- Candidate work-order-operation lifecycle / station queue remained
  `queued / queued`.
- Work order, work-order operation, and station-queue counts/digests were
  unchanged.

## Clone Cleanup

- Exact clone was dropped with guarded `dropdb --force`.
- Remaining databases matching `mes_canonical_v2_op10_flow_%`: `0`.
- Container `/tmp` migration/seed copies were removed.
- Host logical backup was preserved.

## Source Final Integrity

- A new source read-only transaction confirmed binding table absent and V2
  route count `0`.
- Baseline/final counts: `15/15` equal.
- Baseline/final digests: `15/15` equal.
- Retained V1 remained `active / OPERATOR_OBSERVATION_APPROVAL / pending`, with
  events / approvals / production flow `4 / 0 / 0`.
- Unintended source mutation: `0`.

## Health

- `GET http://127.0.0.1:8080/health`: `status=ok`.
- No Docker rebuild, recreate, restart, down, or volume operation occurred.

## Guardrails

- Source `mes` remained unchanged.
- Migration, V2 seed, binding, initialization, and execution occurred only on
  the exact disposable clone.
- No automatic binding, inference, lifecycle fixture, work-order/operation
  insert, status mutation, approval helper, production-flow helper, inventory
  movement, work-order release, API/Kiosk/IoT/Observer/OEE, MESQL, or FERP
  operation occurred.
- The execution flow verified runtime-engine behavior only; no
  work-order lifecycle or inventory movement was performed.
- Execution evidence and the new `CURRENT_STATE.md` checkpoint were not
  committed. No push, reset, rebase, or amend was performed.
- `.agents/` was not intentionally read or changed.

## Result

`PASS`

All step transitions, event-ledger identities, duplicate-event idempotency,
completion-policy behavior, protected-table boundaries, clone cleanup, source
integrity, and health criteria passed.
