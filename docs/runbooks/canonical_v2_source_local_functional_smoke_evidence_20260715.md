# Canonical V2 Source-Local Functional Smoke Evidence

## Result

`FAIL / FINAL_RELEASE_REPLAY_QUEUE_CARDINALITY_CONFLICT`

Execution date: `2026-07-15`.

The source-local fixture reached the intended final operational state, but the
required route-release replay after completion raised
`WORK_ORDER_RELEASE_QUEUE_CONFLICT` instead of returning `released=false`.
The Phase 5H-C failure policy therefore stopped execution immediately. The
fixture remains retained as nonproduction failed-validation evidence; no
delete, repair, compensation, restore, new identity, or automatic resume was
performed.

## Phase 5H-B Closure

The committed Phase 5H-B source schema/seed evidence was reviewed against the
live read-only baseline before the functional smoke. No P1/P2 contradiction was
found. The exact two documentation files were committed as:

```text
commit: 764eb3c84a4aebac9b9927bcec4dc0f7275b343c
subject: docs: record applied canonical v2 source schema and seed
files:
  docs/architecture/CURRENT_STATE.md
  docs/runbooks/canonical_v2_source_schema_seed_apply_evidence_20260715.md
```

There was no duplicate commit and no push. The committed Phase 5H-B result
remains `PASS / APPLIED_CANONICAL_V2_SOURCE_SCHEMA_AND_SEED`.

## Approval, Regression, and Source Readiness

This run used the separate Phase 5H-C approval for exactly one retained source
fixture. Before source mutation:

- targeted MESQL V2 tests passed: `600`, `OK`;
- combined station/config/location/MESQL V2 tests passed: `636`, `OK`;
- `mes_web/db/mesql_v2.py` compiled successfully;
- `git diff --check` passed;
- source identity was `mes_postgres / mes / mes`, PostgreSQL `16.14`, port
  `5433`;
- the container and HTTP health checks were healthy / `200`, `status=ok`;
- no other database session or concurrent candidate-table mutation was found;
- the `mes` base-table count was `40` and the exact Phase 5H-B sidecar, parent
  constraint, Canonical V2, role, V1, and audit readiness checks passed;
- binding/release rows and the fixed work-order, release, and event identities
  were absent.

The pre-write repeatable-read baseline captured ordered count/digest evidence
for all `40/40` base tables. Retained V1 was `1 / 2 / 5`; audit
events/approvals/flow was `4 / 0 / 0`.

## Fixed Identity and Nonproduction Markers

The identity was fixed once and was not changed:

```text
order_id:   PHASE5HC-SOURCE-SMOKE-20260715-181940
release_id: PHASE5HC-SOURCE-RELEASE-20260715-181940
actor:      PHASE5HC_SOURCE_SMOKE
route:      ROUTE_BOX_PACKAGING_V2
version:    2
mode:       route_generated
source:     local_planning
```

Release metadata was exactly:

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

The work-order payload and metadata contained the same markers plus
`"run_timestamp":"20260715-181940"`.

## Candidate Work Order

One guarded direct-SQL transaction inserted only the initial work-order row:

```text
status: planned
product_code: PACKAGED_PRODUCT
target_quantity: 1
started_at / completed_at: NULL / NULL
source_system: mes_web
created_at = updated_at: 2026-07-15 18:22:16.243866+00
```

The immediate readback found no lifecycle, binding, release, queue, runtime,
event, approval, flow, outbox, package, or inventory artefact.

## Route Release and Immediate Replay

The first call to the existing `release_work_order_to_route` helper returned
`released=true` at `2026-07-15T18:22:53.757944+00:00`.

```text
route-operation count: 2
operation-set digest:
  8cb642eb8c2db238adf59891fb30aac5b1673ec16de6da2a4a10a5d04338cba9

OP10 lifecycle UUID:
  52fb8cd4-005e-51f2-9557-a6ff31ce5063
OP20 lifecycle UUID:
  d78c3f30-9e49-51a3-ad58-a13e45f3705f

OP10 binding ID:
  BINDING-WORK-ORDER-RELEASE-B326B1A6-B14F-5B61-AC8B-8F1B6337B000
OP20 binding ID:
  BINDING-WORK-ORDER-RELEASE-FF853F0E-ACD8-5816-B0A0-BE930BE11B16

initial queue PK / rank / station:
  6853 / 5 / ASSEMBLY_01
initial queue source:
  work_order_release
```

The operation snapshots were OP10 sequence `10`, status `queued`, station
`ASSEMBLY_01`; and OP20 sequence `20`, status `planned`, station
`PACKAGING_01`. Both had planned quantity `1`, good/scrap `0/0`, and UOM
`piece`. Deterministic UUID/binding recomputation, the complete immutable
binding set, digest, writer response, and all five Phase 5C read helpers agreed.

The immediate exact release replay returned `released=false`. Its complete
`40/40` table snapshot was unchanged.

## OP10 Runtime and Bridge

Initialization created one ready execution state at
`2026-07-15T18:26:55.265162+00:00`, with no current step and three pending
steps. Initialization replay returned the existing state with zero writes.

The configured OP10 events were executed with fixed, order-prefixed external
event and idempotency identities:

1. `COLOR_SENSOR_ENTRY_EVIDENCE` automatic finish through
   `COLOR_SENSOR_ENTRY` at `2026-07-15T18:30:20.157784+00:00`;
2. `ROBOT_ARM_DROP_COMPLETED` implicit start and automatic finish through
   `ROBOT_ARM_DROP` at `2026-07-15T18:30:46.631571+00:00`;
3. `PROCESS_END_OBSERVATION` manual start through `KIOSK_OPERATOR` at
   `2026-07-15T18:31:11.795429+00:00`, then manual finish.

Immediately before the final OP10 finish, OP20 remained planned, had no queue
or runtime state, and the work order was not completed. The final finish
returned `finished=true`, `event_inserted=true`, and
`completion_bridge.bridged=true`.

```text
OP10 runtime/lifecycle/queue status: closed / completed / completed
authoritative closed/completed time: 2026-07-15T18:32:10.191997+00:00
OP20 lifecycle status: queued
OP20 queue PK / rank / station: 6854 / 3 / PACKAGING_01
OP20 queue source: runtime_completion_bridge
work-order status: queued
```

The release, bindings, static lifecycle identity, quantities, payload/metadata,
and original queue rank/source remained unchanged. The exact OP10 finish replay
returned all finish/event/bridge flags false and had a `40/40` zero-write
snapshot.

## OP20 Runtime and Final Completion

OP20 initialization created one ready execution state at
`2026-07-15T18:34:16.485188+00:00`, with one pending
`PACKAGING_EXECUTION` step. Initialization replay was zero-write.

The manual packaging start occurred at
`2026-07-15T18:35:21.320314+00:00`. The final finish returned
`finished=true`, `event_inserted=true`, and
`completion_bridge.bridged=true`.

```text
OP20 runtime/lifecycle/queue status: closed / completed / completed
authoritative closed/completed time: 2026-07-15T18:35:41.238660+00:00
successor lifecycle/queue: none / none
work-order status: completed
work-order completed_at: 2026-07-15T18:35:41.238660+00:00
```

The final direct readback showed one work order, one release, two lifecycle
operations, two bindings, two runtime states, two queue rows, four runtime-step
rows, and six explicit configured operation events. Work-order completion,
OP20 runtime close, OP20 lifecycle completion, and OP20 queue completion used
the same authoritative timestamp.

The exact OP20 final-finish replay returned all flags false with `40/40` zero
writes. Replaying the old OP10 finish after final completion also returned all
flags false, with no conflict and `40/40` zero writes.

## Final Route-Release Replay Failure

The final exact route-release replay was required to return
`released=false`, tolerate mutable operational progression, and perform zero
writes. Instead it raised:

```text
MesqlV2Error: WORK_ORDER_RELEASE_QUEUE_CONFLICT
```

The persisted completed route legitimately has two queue rows: the original
OP10 queue and the runtime-bridge-created OP20 successor queue. The replay
validator reads the work order's complete queue set and requires exactly one
row before comparing initial-queue immutable identity:

```text
mes_web/db/mesql_v2.py:4149
if len(existing_queue) != 1 or not _compare_initial_queue_identity(...):
    raise MesqlV2Error("WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409)
```

The identity comparator itself excludes mutable `status` and `rank`; the
failure is the whole-order queue cardinality requirement. It contradicts the
Phase 5H-C progressed replay contract because a valid two-operation completed
route necessarily retains both lifecycle-scoped queue rows.

The exception occurs on the existing-release validation branch before any
release insert/update statement, inside the helper-owned transaction context.
The context exits by exception and rolls back. An additional independent
post-error read-only source digest was requested, but the execution environment
rejected Docker access because its usage quota was exhausted. That readback was
not retried or bypassed. Consequently, this evidence does not claim a fresh
authoritative post-error digest; the last authoritative source snapshot is the
completed fixture immediately before this replay, following the already
verified OP20 and old-OP10 zero-write replays.

## Audit, Integrity, and Retention

At the last authoritative final snapshot:

```text
fixture operation events: 6
system-transition events: 0
operation approvals: 0
production-flow events: 0
production completions: 114 (baseline unchanged)
work-order events: 676 (baseline unchanged)
integration outbox: 9 (baseline unchanged)
FERP export outbox: 0 (baseline unchanged)
```

All base tables outside the eight expected fixture-owned tables retained their
pre-write counts and ordered digests. The expected fixture-owned deltas were:

```text
work_orders: +1
work_order_operations: +2
station_queue: +2
work_order_route_releases: +1
work_order_operation_route_bindings: +2
work_order_operation_execution_state: +2
work_order_operation_steps: +4
operation_events: +6
```

There was no bridge-added system-transition, approval, production flow or
completion, work-order event, integration/FERP outbox, package WIP/session/
traceability, or inventory effect at that snapshot. Locations and station
bindings remained unchanged. Retained V1 remained `1 / 2 / 5` with exact
scoped digests:

```text
route:      163f416bfdcf16ca469e43adbd47b324
operations: 92a859fc57182954c5070670928c89e6
steps:      3829d1b0a5185a4ac59a509532b4abc8
```

The failed-validation fixture is intentionally retained under the exact
`PHASE5HC-SOURCE-SMOKE-` prefix and required metadata. Future OEE, KPI,
analytics, reporting, FERP/MESQL export, and generic export consumers must
exclude it by prefix or `exclude_from_analytics=true`. That filter remains a
mandatory deferred requirement; no consumer implementation was added here.

No API, feature flag, Kiosk/IoT action, FERP/MESQL import, automatic route
selection, inventory/package helper, migration/seed apply, Docker lifecycle,
cleanup, delete, repair, compensation, restore, H-C commit, or push was
performed. Phase 5H-C must not resume without a separately reviewed replay fix
and a new explicit recovery/continuation approval for this retained identity.

## Acceptance

Result: `FAIL`.

The functional path through work-order completion succeeded, and the immediate
release replay plus all runtime initialization/finish replays were idempotent.
However, the mandatory final route-release replay acceptance criterion failed.
No verified Phase 5H-C closure is recorded.
