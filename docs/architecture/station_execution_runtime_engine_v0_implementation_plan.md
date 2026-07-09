# Station Execution Runtime Engine V0 Implementation Plan

## 1. Amac

Bu dokuman, station execution runtime engine V0 implementation fazi icin
sinirlari, DB write kapsamini, state transition kurallarini, idempotency
yaklasimini, rollback/smoke planini ve risk checkpointlerini tanimlar.

Bu dokuman implementation degildir. Bu turda kod yazilmaz, DB'ye baglanilmaz,
psql calistirilmaz, Docker/compose/container islemi yapilmaz, migration/seed
apply edilmez ve operation lifecycle smoke calistirilmaz.

## 2. Baseline

Mevcut dogrulanmis durum:

```text
Station execution schema: applied
Minimal station execution seed: applied
Config helpers: implemented and smoke verified
Config read API: implemented and HTTP smoke verified
Feature flag wiring: verified on normal mes_web:8080
Runtime/event/flow tables: empty
Kiosk dynamic action: not started
Runtime engine: not started
IoT adapter: not started
OEE/KPI: not started
Inventory movement/balance: not started
MESQL: frozen
```

V0 hedefi:

```text
Seedlenmis route operation + operation steps config'ine gore,
bir work_order_operation icin sidecar execution state ve step state uretmek,
manual/auto step start-finish olaylarini kontrollu sekilde islemek,
operation completion policy'ye gore execution state'i ilerletmek,
ama mevcut work_order_operations.status ve station_queue davranisini ilk fazda
bozmamak.
```

## 3. V0 Write Scope

V0 yalnizca su yeni station execution tablolarina write yapabilir:

```text
mes.work_order_operation_execution_state
mes.work_order_operation_steps
mes.operation_events
mes.operation_approvals
```

Tablo rolleri:

- `mes.work_order_operation_execution_state`: operation-level sidecar state.
- `mes.work_order_operation_steps`: work order operation'a instantiate edilen
  step state.
- `mes.operation_events`: append-only event/audit ledger.
- `mes.operation_approvals`: final/supervisor/quality approval audit.

`mes.production_flow_events` V0'da kapali kalmalidir. Bu tablo inventory ledger
degildir; fiziksel flow kaniti ve inventory movement icin ayrica karar gerekir.

## 4. Forbidden Mutation Scope

V0 runtime engine su tablolara write yapmamalidir:

```text
mes.work_orders
mes.work_order_operations
mes.station_queue
mes.items
mes.process_routes
mes.route_operations
mes.operation_steps
mes.station_event_sources
mes.locations
mes.station_location_bindings
mes.production_flow_events
```

Kurallar:

- Config tablolar read-only kalir.
- Work order, work order operation ve queue mevcut lifecycle helper'lariyla
  ayrilir.
- Runtime engine V0 sidecar proof-of-control katmanidir.
- Existing successor activation davranisi bu fazda degistirilmez.

## 5. Runtime Helper Tasarimi

Implementation sonraki fazda `mes_web/db/mesql_v2.py` icinde veya ayrik bir
runtime module siniri icinde yapilabilir. Bu dokuman sadece fonksiyon
sozlesmesi onerir.

Onerilen helperlar:

```text
get_execution_state(config, work_order_operation_id)
initialize_execution_state(config, work_order_operation_id, route_operation_id, station_code, actor_id=None)
list_execution_steps(config, work_order_operation_id)
start_execution_step(config, work_order_operation_id, step_code, event_source=None, external_event_id=None, actor_id=None)
finish_execution_step(config, work_order_operation_id, step_code, event_source=None, external_event_id=None, actor_id=None)
record_operation_event(config, ...)
evaluate_operation_completion(config, work_order_operation_id)
submit_operation_approval(config, work_order_operation_id, approval_status, actor_id, note=None)
```

Separation:

- `initialize_execution_state` sadece sidecar state ve step instance uretir.
- `record_operation_event` append-only ledger kaydi olusturur.
- `start_execution_step` / `finish_execution_step` state transition uygular.
- `evaluate_operation_completion` policy uygular, mevcut lifecycle tablolarina
  write yapmaz.
- `submit_operation_approval` approval audit ve sidecar final transition yapar.

## 6. State Model

### `execution_state.execution_status`

Plan-level semantic states:

```text
not_started
active
evidence_completed
pending_final_approval
closed
cancelled
```

Schema compatibility:

`004_station_execution_schema.sql` icindeki gercek CHECK constraint su status
setini kabul eder:

```text
queued
ready
active
evidence_completed
pending_final_approval
closed
cancelled
failed
```

V0 implementation mapping:

```text
not_started -> ready
active -> active
evidence_completed -> evidence_completed
pending_final_approval -> pending_final_approval
closed -> closed
cancelled -> cancelled
```

`queued` existing lifecycle compatibility icin sakli kalir. `failed` V0'da
explicit failure/rejection policy netlesmeden kullanilmamalidir.

### `work_order_operation_steps.status`

Plan-level semantic states:

```text
pending
active
finished
skipped
cancelled
```

Schema compatibility:

Gercek CHECK constraint:

```text
pending
active
completed
skipped
failed
cancelled
```

V0 implementation mapping:

```text
finished -> completed
```

Bu dokumanda `finished` kullanildiginda DB yaziminda `completed` olarak
uygulanmalidir.

## 7. Transition Matrix

### Initialize

| Current execution state | Trigger | Next execution state | Step effect |
| --- | --- | --- | --- |
| no state | initialize | `ready` | active config steps instantiate as `pending` |
| existing state | initialize again | unchanged | no duplicate step state |

Rules:

- `work_order_operation_id` icin sadece bir execution state olabilir.
- `work_order_operation_steps` unique keys: `(work_order_operation_id, step_code)`
  and `(work_order_operation_id, step_no)`.
- Initialize idempotent olmalidir.

### Manual / Auto Start

| Execution status | Step status | Trigger | Next execution status | Next step status |
| --- | --- | --- | --- | --- |
| `ready` | `pending` | manual start | `active` | `active` |
| `ready` | `pending` | auto start | `active` | `active` |
| `active` | `pending` | manual start | `active` | `active` |
| `active` | `pending` | auto start | `active` | `active` |
| `active` | `active` | duplicate start | unchanged | unchanged |
| `closed` | any | start | reject event | unchanged |

### Manual / Auto Finish

| Execution status | Step status | Trigger | Next step status | Follow-up |
| --- | --- | --- | --- | --- |
| `ready` | `pending` | implicit/auto finish | `completed` | set execution `active`, evaluate |
| `active` | `pending` | implicit/auto finish | `completed` | evaluate |
| `active` | `active` | manual finish | `completed` | evaluate |
| `active` | `active` | auto finish | `completed` | evaluate |
| any | `completed` | duplicate finish | unchanged | no duplicate mutation |
| `closed` | any | finish | reject event | unchanged |

### Completion Policy

| Policy | Required steps complete | Next execution status |
| --- | --- | --- |
| `manual_close` | yes | `evidence_completed` |
| `auto_close_on_required_steps` | yes | `closed` |
| `auto_complete_pending_approval` | yes | `pending_final_approval` |

Approval transition:

| Execution status | Approval result | Next execution status |
| --- | --- | --- |
| `pending_final_approval` | approved | `closed` |
| `pending_final_approval` | rejected | remain `pending_final_approval` or future `failed` policy |
| `pending_final_approval` | hold | remain `pending_final_approval` |

Rejected/hold behavior must be finalized before write implementation. V0 should
prefer preserving state and recording audit over moving to `failed` implicitly.

## 8. Event and Idempotency Model

Primary idempotency fields:

```text
operation_events.idempotency_key
operation_events.station_code + event_source + external_event_id
```

Existing unique indexes:

```text
ux_mes_operation_events_station_source_external
ux_mes_operation_events_idempotency_key
```

Rules:

- Same external event must not write a duplicate accepted event.
- Same station/source/external_event_id replay must not mutate step state again.
- Same idempotency_key replay must return the existing event/result behavior.
- Same step finish replay keeps the step `completed` and does not corrupt
  timestamps or current state.
- Initialize replay must not create duplicate execution state or step rows.
- If an IoT adapter cannot provide `external_event_id`, it must produce a
  deterministic idempotency key before calling runtime engine.

Suggested idempotency key shape:

```text
station_code:event_source:external_event_id
```

or for manual Kiosk action:

```text
work_order_operation_id:step_code:action:client_request_id
```

## 9. Event Ledger Rules

`operation_events` is append-only audit.

Allowed event types from schema:

```text
step_start
step_finish
evidence
approval
reject
system_transition
```

Recommended V0 behavior:

- Accepted event writes `accepted = true`.
- Rejected event writes `accepted = false` with `rejection_reason` when the
  event is meaningful enough to audit.
- Duplicate event should be handled idempotently. It may return existing event
  metadata instead of inserting a new rejected event.
- State mutation must occur only after event validation and idempotency check.
- State mutation and event insert should be inside one DB transaction.

## 10. Config Validation Dependency

Runtime init must call:

```text
get_route_operation_config(route_operation_id)
```

If validation contains critical warnings, runtime init must fail before any
state mutation.

Critical warning classes:

```text
missing input item
missing output item
missing station
missing event source referenced by auto_start/auto_finish
auto_start without start_event_source_code
auto_finish without finish_event_source_code
```

Current aggregate validation already reports:

```text
missing_items
missing_station
missing_event_sources
invalid_step_source_refs
invalid_auto_mode_refs
```

V0 implementation should convert non-empty entries in those lists into a
deterministic runtime init failure such as:

```text
ROUTE_OPERATION_CONFIG_INVALID
```

## 11. Current Seed Scenario Expectations

Minimal seed:

```text
ROUTE_BOX_PACKAGING_V1_OP10 / ASSEMBLY_01
  COLOR_SENSOR_ENTRY_EVIDENCE: auto_start + auto_finish via COLOR_SENSOR_ENTRY
  ROBOT_ARM_DROP_COMPLETED: implicit_start + auto_finish via ROBOT_ARM_DROP
  OPERATOR_OBSERVATION_APPROVAL: implicit_start + manual_finish via KIOSK_OPERATOR

ROUTE_BOX_PACKAGING_V1_OP20 / PACKAGING_01
  PACKAGING_START: manual_start + implicit_finish via KIOSK_OPERATOR
  PACKAGING_FINAL_APPROVAL: implicit_start + manual_finish via KIOSK_OPERATOR
```

Both route operations currently use:

```text
operation_completion_policy = auto_complete_pending_approval
```

Expected V0 completion after all required steps:

```text
execution_status = pending_final_approval
```

Expected final approval accepted:

```text
execution_status = closed
```

## 12. API and Kiosk Scope

This V0 plan is not an API route implementation.

This V0 plan is not Kiosk dynamic action implementation.

Future Kiosk integration should call runtime engine helpers through separate
POST endpoints, for example:

```text
POST /api/v2/station-execution/runtime/{work_order_operation_id}/initialize
POST /api/v2/station-execution/runtime/{work_order_operation_id}/steps/{step_code}/start
POST /api/v2/station-execution/runtime/{work_order_operation_id}/steps/{step_code}/finish
POST /api/v2/station-execution/runtime/{work_order_operation_id}/approval
```

Those endpoints are out of scope for this document's implementation turn. The
existing GET config API must not change in V0 helper implementation.

Kiosk init/register POST behavior is existing behavior and must not be mixed
with runtime step actions without explicit route design.

## 13. IoT / Observer Scope

IoT adapter may eventually send normalized events into the runtime engine.

Out of scope for V0 implementation plan:

```text
MQTT subscriber implementation
observer event normalization implementation
sensor replay handling in the adapter
robot control integration
PLC integration
```

Runtime engine should accept already-normalized event fields:

```text
station_code
event_source
event_type
external_event_id or idempotency_key
payload
event_time
```

## 14. MESQL Scope

MESQL push/pull remains frozen.

Runtime engine V0 runs only inside local MES DB.

Out of scope:

```text
MESQL outbox
ERP sync
MESQL pull/push side effects
external operation completion sync
```

## 15. Inventory Scope

Inventory movement/balance is out of scope.

`production_flow_events` is not an inventory ledger and remains out of V0 write
scope.

Sensor evidence can become a future source for inventory movement, but V0 must
not mutate stock, balances, locations, or material ledger data.

## 16. Transaction and Rollback Strategy

Runtime helper writes should be transaction-scoped:

```text
BEGIN
  validate config
  check idempotency
  insert operation_event
  update step state
  update execution state
COMMIT
```

On validation failure:

```text
no state mutation
optional rejected event only if enough station/source context is valid
```

On DB exception:

```text
ROLLBACK
surface deterministic runtime error
do not partially update step/execution state
```

Real DB smoke rollback options:

1. Use a dedicated smoke work order operation and clean only allowed V0 tables
   by explicit key after backup and review.
2. Use a transaction wrapper in a manual smoke script and roll back before
   commit, if the code path allows it.
3. Restore from backup only as last resort; never use Docker volume deletion.

## 17. Unit Test Plan

DB-free unit tests should use fake cursor/connection patterns similar to
`tests/test_mes_web_mesql_v2.py`.

Required tests:

```text
fake cursor initialize_execution_state SQL order
duplicate initialize idempotency
start step transition
finish required step transition
all required steps finished -> policy evaluation
auto_complete_pending_approval -> pending_final_approval
auto_close_on_required_steps -> closed
manual_close -> evidence_completed
missing config validation -> fail
duplicate external event idempotency
duplicate idempotency_key idempotency
rejected event records rejection_reason when audited
no writes to work_orders/work_order_operations/station_queue
no writes to items/process_routes/route_operations/operation_steps/station_event_sources
no writes to production_flow_events in V0
```

Test assertions should check:

- SQL order for event insert before state mutation where required.
- `MesqlV2Error` or future runtime error detail/status mapping.
- `work_order_operation_id`, `step_code`, `station_code` normalization.
- Duplicate finish does not create duplicate event or state mutation.
- Approval accepted moves `pending_final_approval` to `closed`.

## 18. Real DB Smoke Plan

Preconditions:

```text
backup taken
mes_postgres healthy
mes_web health ok
runtime/event/flow baseline counts recorded
MESQL frozen
no Docker volume deletion
```

Smoke outline:

```text
1. Choose a dedicated test work_order_operation.
2. Verify route_operation_id mapping.
3. Verify get_route_operation_config has no critical warnings.
4. initialize sidecar state.
5. Verify execution_state row exists.
6. Verify work_order_operation_steps rows match active config steps.
7. Start/finish OP10 steps.
8. Verify operation_events accepted rows.
9. Verify step state statuses.
10. Verify execution_status reaches pending_final_approval for current seed.
11. Submit final approval accepted.
12. Verify execution_status becomes closed.
13. Verify work_order_operations.status untouched.
14. Verify station_queue untouched.
15. Verify allowed V0 table counts increased only as expected.
16. Verify production_flow_events unchanged at 0.
17. Cleanup/rollback dedicated smoke records only after explicit reviewed plan.
```

Expected no-write to existing lifecycle:

```text
mes.work_orders unchanged
mes.work_order_operations unchanged
mes.station_queue unchanged
```

Allowed increased counts:

```text
mes.work_order_operation_execution_state
mes.work_order_operation_steps
mes.operation_events
mes.operation_approvals, only if approval smoke is included
```

## 19. Risks

Key risks:

- Existing `complete_operation_v2` lifecycle helper and new sidecar runtime
  state can diverge.
- `work_order_operation_id` to `route_operation_id` mapping is not yet a
  proven runtime contract.
- Kiosk POST actions can conflict with existing init/register behavior if route
  design is not explicit.
- IoT duplicate event or MQTT replay can cause double finish if idempotency is
  weak.
- Manual approval policy requires operator UX and clear audit display.
- `production_flow_events` can be mistaken for inventory movement.
- Schema uses `completed` while planning language may say `finished`; mapping
  must be explicit in implementation.
- Rejected event audit can create noisy ledger rows if duplicate handling is
  not carefully separated from invalid event handling.
- Cleanup of real DB smoke data can become unsafe unless records use dedicated
  smoke IDs and allowed V0 tables only.

## 20. Implementation Sequencing

Recommended implementation phases:

1. Add read-only selectors for existing sidecar state and step state.
2. Add `initialize_execution_state` with idempotent state/step insert.
3. Add event idempotency lookup and `record_operation_event`.
4. Add start/finish step transitions for manual sources.
5. Add auto source handling and event source validation.
6. Add completion policy evaluation.
7. Add final approval helper.
8. Add DB-free unit tests after each helper group.
9. Only then design POST API and Kiosk dynamic action integration.

## 21. Acceptance Criteria

This plan is ready to feed the next implementation prompt when:

```text
- V0 write scope is clear.
- Forbidden table mutation list is clear.
- State transition matrix is clear.
- Idempotency approach is clear.
- Config validation dependency is clear.
- Kiosk/API/IoT/MESQL/inventory out-of-scope boundaries are clear.
- Unit test plan is clear.
- Real DB smoke plan includes backup and rollback.
- The next implementation prompt can be deterministic and narrowly scoped.
```

## 22. Guardrails

For this documentation turn:

```text
code change: no
DB connection: no
psql: no
Docker/compose/container: no
seed/migration apply: no
runtime implementation: no
Kiosk implementation: no
IoT/OEE/MESQL: no
inventory movement: no
commit/push: no
.agents access: no
```
