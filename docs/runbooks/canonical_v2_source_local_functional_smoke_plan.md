# Canonical V2 Source-Local Functional Smoke Plan

## Status

`PLANNED_REQUIRES_PHASE_5H_B_PASS_AND_SEPARATE_APPROVAL`

Last updated: `2026-07-15`.

This Phase 5H-C plan is not executed by Phase 5H-A or Phase 5H-B. It becomes
eligible only after a documented Phase 5H-B PASS and a new explicit approval
for one persisted source-local nonproduction validation fixture.

## Safety Boundary

- Exact target: source container/database/user `mes_postgres / mes / mes`.
- Phase 5H-B schema/seed evidence must already prove binding `9/9/4`, release
  `14/15/5`, V2 `1/2/4`, OP10/OP20 `3/1`, and roles `5/5`.
- Use one unique work order and one release only.
- Direct SQL is permitted only for inserting the clean candidate work order.
- All release/runtime/bridge transitions use existing internal Python helpers.
- Do not use API, feature flags, Kiosk endpoints, FERP/MESQL import, automatic
  route selection, legacy operation completion, or inventory helpers.
- Do not delete, disguise, recycle, or silently repair the fixture.
- Do not rebuild/recreate/restart/down Docker or alter volumes.

## Test-Data Policy

The selected policy is a persisted source-local nonproduction audit fixture.
A rollback-only outer transaction is invalid because public helpers own and
commit their transactions. A dedicated validation database does not prove the
runtime chain on actual source `mes`.

Successful evidence remains in source. If the chain fails after a committed
step, the partial fixture also remains as failed validation evidence. Cleanup,
resume, compensation, or restore requires a new explicit decision. No automatic
delete or backup restore is permitted.

## Source-Local Test Identity

Generate one UTC run timestamp in `yyyyMMdd-HHmmss` format and fix these values
for the entire run:

```text
order_id   = PHASE5HC-SOURCE-SMOKE-<yyyyMMdd-HHmmss>
release_id = PHASE5HC-SOURCE-RELEASE-<yyyyMMdd-HHmmss>
actor      = PHASE5HC_SOURCE_SMOKE
route      = ROUTE_BOX_PACKAGING_V2
version    = 2
mode       = route_generated
source     = local_planning
product    = PACKAGED_PRODUCT
quantity   = 1
```

Both the work-order marker and release request must contain these exact required
keys. Any identity fields added to either object are fixed before the candidate
insert and must not change during replay:

```json
{
  "disposable_test": true,
  "exclude_from_analytics": true,
  "phase": "5H-C",
  "production_release": false,
  "purpose": "canonical_v2_source_local_functional_smoke",
  "retention_reason": "source_rollout_validation"
}
```

The work-order payload must independently mark the row as nonproduction and
record the same purpose, run timestamp, and retention reason. Never use an ID
without the `PHASE5HC-SOURCE-SMOKE-` prefix.

## Deferred Analytics and Export Exclusion

Every future OEE, KPI, dashboard, report, analytics, FERP, MESQL export, generic
export, or production aggregation must exclude this fixture when either:

- `order_id` starts with `PHASE5HC-SOURCE-SMOKE-`; or
- applicable payload/metadata contains `exclude_from_analytics=true`.

This is a mandatory deferred consumer requirement. Phase 5H-A/B/C does not add
an analytics filter, export rule, API flag, migration, trigger, or production
query branch. Until consumers implement and verify the exclusion, this fixture
must not be treated as production/OEE/KPI evidence.

## Preconditions

Before any source write:

1. obtain separate Phase 5H-C approval naming the exact order/release IDs;
2. verify Phase 5H-B PASS evidence and exact source identity;
3. verify the three SQL hashes still match the approved rollout artifacts;
4. verify binding/release/V2 shapes and policies read-only;
5. verify the exact order ID, release ID and event identity prefix do not exist;
6. capture established source, V1, audit, sidecar, runtime, queue, outbox,
   package and inventory-availability baselines;
7. verify no other work-order/runtime mutation is in progress for the test
   identity or its stations;
8. verify health `200 / ok` without a Docker lifecycle action.

Any mismatch is `BLOCKED`; do not choose a new identity ad hoc after writes
start.

## Candidate Work Order

Insert exactly one source work order in its own guarded transaction with:

- exact approved `order_id`;
- `status = planned`;
- `product_code = PACKAGED_PRODUCT`;
- `target_quantity = 1`;
- `started_at = NULL`, `completed_at = NULL`;
- `source_system = mes_web`;
- nonproduction payload/metadata from this plan;
- one captured `created_at/updated_at` pair;
- no lifecycle operation, binding, release, queue, runtime, event, approval,
  production-flow, outbox, package or inventory row.

The setup transaction must first assert `current_database() = 'mes'`, exact
identity nonexistence, and Phase 5H-B sidecar/V2 readiness. It may insert only
the one work-order row. Do not use a production import, API, FERP or MESQL path.

After commit, read the exact work order back and prove the clean release
eligibility shape before calling the writer.

## Route Release

Call existing `release_work_order_to_route` with:

```text
release_id=<approved release ID>
work_order_id=<approved order ID>
route_code=ROUTE_BOX_PACKAGING_V2
route_version=2
release_source=local_planning
released_by=PHASE5HC_SOURCE_SMOKE
mode=route_generated
operation_bindings=None
metadata=<exact approved metadata object>
```

Require `released=true` and exact readback:

- one immutable release with route-operation count `2` and valid digest;
- deterministic OP10/OP20 lifecycle UUIDs;
- OP10 `queued` at `ASSEMBLY_01`, OP20 `planned` at `PACKAGING_01`;
- planned quantity `1`, active route-item UOM, zero good/scrap quantities;
- two complete immutable lifecycle-UUID bindings;
- one OP10 initial queue with source `work_order_release`;
- work order `queued`;
- unchanged candidate payload/metadata;
- no runtime, step, event, approval, flow, outbox, package or inventory write.

Read through the five Phase 5C helpers and require exact agreement with the
writer response. Capture release/binding/static lifecycle digests, PKs,
timestamps and queue rank.

## Release Replay

Immediately call `release_work_order_to_route` again with byte/structurally
equal request values and metadata. Require:

- `released=false`;
- complete current authoritative snapshot;
- identical release, static lifecycle and binding artefacts;
- no timestamp, queue rank or row-count change;
- zero writes across every monitored table.

Later, after final work-order completion, replay the exact release once more.
Mutable operational progression must still return `released=false` without
rewind or conflict.

## OP10 Initialization

Use the deterministic OP10 lifecycle UUID and call:

```text
initialize_execution_state(
  work_order_operation_id=<OP10 UUID>,
  route_operation_id=ROUTE_BOX_PACKAGING_V2_OP10,
  station_code=ASSEMBLY_01,
  actor_id=PHASE5HC_SOURCE_SMOKE
)
```

Require one `ready` execution state, `current_step=null`, and exactly three
ordered pending steps. Release, lifecycle, binding and queue artefacts remain
unchanged; initialization creates no operation event, approval or flow row.

Replay initialization and require the existing state/steps without duplicate
rows or mutation.

## OP10 Execution

Use unique external event IDs and idempotency keys prefixed with the approved
order ID. Execute configured steps in order through existing helpers:

1. finish `COLOR_SENSOR_ENTRY_EVIDENCE` through event source
   `COLOR_SENSOR_ENTRY`, exercising its configured automatic start/finish path;
2. finish `ROBOT_ARM_DROP_COMPLETED` through `ROBOT_ARM_DROP`, exercising its
   configured implicit-start/automatic-finish path;
3. start then finish `PROCESS_END_OBSERVATION` through `KIOSK_OPERATOR`.

Each response must agree with direct runtime state/step/event readback. Before
the last finish, OP20 remains planned and has no queue/runtime row.

The final OP10 finish must close runtime and bridge in the same transaction:

- `completion_bridge.bridged=true`;
- OP10 lifecycle and its original queue become `completed` at runtime
  `closed_at` while immutable quantities/payload/metadata/rank remain intact;
- OP20 lifecycle becomes `queued`;
- exactly one OP20 queue is created at `PACKAGING_01` with source
  `runtime_completion_bridge` and no route/config ID in queue payload/metadata;
- work order is not yet completed;
- no extra system-transition event, approval, production-flow/completion,
  outbox, package or inventory effect occurs.

## OP10 Replay

Repeat the exact final OP10 finish using the same event identity. Require
`finished=false`, `event_inserted=false`, `completion_bridge.bridged=false`,
authoritative current readback, and zero writes. Original runtime/lifecycle/
queue timestamps and ranks must remain unchanged.

## OP20 Activation and Initialization

Verify OP20 activation is tied to the deterministic bound lifecycle UUID and
the exact successor queue. Then call:

```text
initialize_execution_state(
  work_order_operation_id=<OP20 UUID>,
  route_operation_id=ROUTE_BOX_PACKAGING_V2_OP20,
  station_code=PACKAGING_01,
  actor_id=PHASE5HC_SOURCE_SMOKE
)
```

Require one ready state and exactly one pending `PACKAGING_EXECUTION` step.
Replay initialization and require no duplicate state/step or side effect.

## OP20 Execution and Final Completion

Start and finish `PACKAGING_EXECUTION` through `KIOSK_OPERATOR` with unique,
fixed event identity. Require:

- runtime closes at the authoritative finish time;
- `completion_bridge.bridged=true`;
- OP20 lifecycle and current queue complete at runtime `closed_at`;
- no successor lifecycle or queue exists;
- both lifecycle operations are completed;
- work order becomes `completed` and `completed_at` equals OP20 `closed_at`;
- release, bindings, static snapshots, quantities, payload/metadata and queue
  ranks remain unchanged except contracted operational status/timestamps;
- no extra approval, flow, completion, outbox, package or inventory effect.

## Final Replays

1. Repeat the exact final OP20 finish: all finish/event/bridge flags false,
   zero writes, original completion timestamp preserved.
2. Replay the old OP10 finish after OP20/work-order completion: false replay,
   no conflict and zero writes.
3. Replay the exact route release: `released=false`, no rewind and zero writes.

Every replay response must match direct authoritative readback.

## Audit Boundary

The only permitted audit delta is the configured runtime start/finish events
created by the explicit OP10/OP20 helper calls. Require no bridge-added
`system_transition` event and zero delta in:

- operation approvals;
- production-flow events and production completions;
- work-order events beyond the existing helper contract;
- integration/FERP outbox;
- item-station/package WIP/session/traceability state;
- inventory movement/balance/stock tables, if present.

Record exact before/after counts and ordered row digests for the fixture scope
and all no-write tables.

## Retained V1 Boundary

Retained V1 route/operations/steps remain `1 / 2 / 5` and byte/digest-equal.
No V1 lifecycle, runtime, queue, event, approval or flow row may change as a
result of the V2 fixture. Any difference is `FAIL`.

## Health

After all readbacks and replays, require source/container health and
`GET /health = 200 / ok` without Docker lifecycle action. Health does not
override a data or audit mismatch.

## Retention and Failure Handling

- On PASS, retain all fixture rows permanently as named nonproduction source
  rollout evidence.
- On failure after any commit, stop immediately and retain the partial fixture.
- Do not delete, mutate into a passing shape, reuse the IDs for another run, or
  run automatic compensation.
- A transient retry may resume the same fixture only after exact read-only state
  classification and new explicit approval, using the existing helper replay
  contracts.
- Backup restore is a separate destructive decision and must account for every
  source change since the Phase 5H-B backup.

## Evidence

Future Phase 5H-C evidence must record:

```text
Result: PASS / FAIL / BLOCKED
Phase 5H-B evidence and approval:
Exact source identity and health:
Order/release/event identities:
Nonproduction and analytics-exclusion metadata:
Candidate insert and clean eligibility:
Release first call/replay/read-model:
Deterministic OP10/OP20 UUIDs and bindings:
OP10 init/steps/bridge/replay:
OP20 activation/init/finish/bridge/replays:
Final work-order state and timestamps:
Allowed event ledger delta:
No-extra-audit/outbox/package/inventory checks:
Retained V1 integrity:
Fixture retention or partial-failure state:
Deferred OEE/KPI/FERP/export exclusion requirement acknowledged:
No API/feature flag/automatic selection:
No cleanup/delete/restore:
```

PASS requires every invariant. An executed behavioral mismatch is `FAIL`.
Missing approval, identity, Phase 5H-B evidence, test-data policy acceptance, or
state certainty is `BLOCKED`. Phase 5H-C never silently repairs source data.
