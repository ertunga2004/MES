# Work-Order Release and Route-Binding Implementation Plan

## Objective

Implement the accepted controlled-hybrid work-order release architecture so
one explicit route version, the complete lifecycle operation set, immutable
operation bindings, and exactly one initial queue row are committed atomically
and replay safely.

This is a plan only. It performs no migration, source-database apply, Python or
test change, API change, binding/lifecycle/queue write, FERP action, or MESQL
action.

## Preconditions

- Approve
  `docs/architecture/work_order_release_route_binding_decision.md`.
- Preserve the existing explicit
  `work_order_operation_id -> route_operation_id` binding contract.
- Keep route code/version selection explicit; an active flag is validation,
  not selection.
- Preserve existing V1 runtime/history and all unbound legacy rows.
- Use additive migrations and disposable logical dump/restore clones.
- Keep release and runtime-to-lifecycle completion as separate deliverables.
- Require separate user approval before each commit, source apply, or external
  integration action.

## Repository Baseline

Verified at Phase 5A:

- `mes.work_orders` has no release or route identity.
- `mes.work_order_operations` has lifecycle snapshots but no config identity.
- `mes.work_order_operation_route_bindings` is the implemented immutable
  operation-level sidecar.
- JSON/FERP runtime import creates normalized work-order state and the mirror
  path can upsert work orders/legacy queue rows, but it does not generate the
  database lifecycle operation set.
- MESQL pull atomically upserts a work order, a payload-defined lifecycle
  operation, and a queue row; PostgreSQL supplies the local operation UUID on
  first insert.
- No production release helper or persistent work-order route/version exists.
- Current effective release status is `queued`; no distinct `released` status
  exists.
- Existing successor activation selects the next nonterminal lifecycle row by
  unique increasing sequence and queues it by `work_order_operation_id`.
- Canonical V2 OP10 runtime can reach `closed` without changing lifecycle or
  queue status from `queued`.

Phase 5A documentation commit: `34d89f1 docs: record canonical v2 op10
execution smoke`.

## Selected Architecture

Use one immutable work-order release sidecar plus the existing operation
binding sidecar.

Two release modes are explicit and mutually exclusive:

- `route_generated`: default for new local MES work; creates every lifecycle
  operation from the frozen route version.
- `explicit_existing_operation_mapping`: validates a caller-supplied complete
  mapping for lifecycle operations already created by a reviewed import path.

Phase 5D enables `route_generated` first. Explicit mapping is implemented only
after the same validation contract has focused unit coverage; it is not an
implicit fallback.

Queue identity remains `work_order_operation_id`. Config identity remains
`binding.route_operation_id`. Release sets/retains work-order status `queued`.

## Data-Model Changes

Draft an additive migration, provisionally
`db/migrations/010_work_order_route_release.sql`, for
`mes.work_order_route_releases`.

Required logical columns:

- surrogate `release_pk`;
- unique, nonblank `release_id`;
- unique `order_id` FK to `mes.work_orders(order_id)`;
- `process_route_id` FK to `mes.process_routes(route_id)`;
- route-code/version snapshots that are validated against the same parent;
- controlled `release_mode` and `release_source`;
- nonblank `released_by`;
- immutable `released_at` and `created_at`;
- positive `route_operation_count`;
- canonical `operation_set_digest`;
- object-only metadata.

Required constraints/indexes:

- one release per work order;
- one work order per release ID;
- positive version/count and nonblank identity/audit fields;
- mode allowlist containing the two selected modes;
- source allowlist enabling only `local_planning` initially;
- FK-safe route identity, including proof that ID/code/version refer to the
  same process-route row;
- indexes for route-version audit and released-at inspection.

Do not add route columns to `mes.work_orders`, route identity to
`mes.station_queue`, or mutable/update/delete fields to either release or
binding sidecar. Do not seed release rows or backfill existing work orders.

## Helper Contracts

Read helpers:

- `get_work_order_route_release(config, work_order_id)`;
- `get_work_order_route_release_by_id(config, release_id)`;
- `get_exact_process_route(config, route_code, route_version)`;
- `list_process_route_operations(config, process_route_id)` ordered by
  sequence;
- `get_work_order_release_snapshot(config, work_order_id)` returning release,
  operations, bindings, and initial queue;
- `validate_work_order_release_snapshot(...)` returning deterministic warnings
  and errors without writes.

Core write helper:

```text
release_work_order_to_route(
    config,
    *,
    release_id,
    work_order_id,
    route_code,
    route_version,
    release_source,
    released_by,
    mode,
    operation_bindings=None,
    metadata=None,
)
```

Return:

```text
released
release
work_order
operations
bindings
initial_queue
```

Internal transaction-scoped primitives must accept the same cursor/connection:

- lock work order and existing release scope;
- resolve exact route/config;
- generate deterministic lifecycle operation UUIDs;
- generate deterministic binding IDs;
- insert lifecycle snapshots;
- validate explicit mapping set equality;
- insert/replay binding pairs without an internal commit;
- allocate/insert the initial queue row;
- compute and verify count/digest;
- classify a concurrent unique violation by authoritative readback.

Standalone helper wrappers may own transactions; internal primitives used by
release must not.

## Validation Contracts

Request validation:

- nonblank release/work-order/source/actor/mode identities;
- positive integer route version;
- metadata is a JSON object;
- generated mode rejects mappings;
- explicit mode requires a nonempty mapping list with unique lifecycle and
  config operation IDs.

Work-order validation:

- row exists and is locked;
- normalized `product_code` equals selected route `item_code` in the MVP;
- status is release-eligible (`planned` or structurally clean `queued`);
- not active, completed, cancelled/canceled, or terminal;
- no execution state, event, approval, production-flow, or incompatible queue
  evidence for a first release.

Route validation:

- exact code/version resolves to exactly one process-route ID;
- route and selected route operations are active at selection time;
- operation set is nonempty, uniquely sequenced, and belongs wholly to the
  selected route;
- existing route-operation config validation succeeds;
- no config/master row is changed.

Generated-operation validation:

- deterministic UUIDv5 input uses the fixed namespace, release ID, and exact
  route-operation ID;
- UUID set, operation number, sequence, code, station, name, and status match
  the canonical generated snapshot;
- first operation is queued; successors are planned.

Explicit-mapping validation:

- every lifecycle operation belongs to the same work order;
- set cardinality equals selected route-operation cardinality;
- no missing, duplicate, or extra lifecycle/config operation;
- each route operation belongs to the frozen version;
- station, operation code, and sequence match exactly as validation fields;
- no lifecycle operation is terminal, active, or already executed;
- existing binding pairs are accepted only as replay of a matching complete
  release, not adopted into a first release.

Queue validation:

- initial operation is the smallest unique route sequence and nonterminal;
- no incompatible station/order, station/operation, or active-rank row exists;
- exact replay returns one unchanged queue row.

## Transaction Stages

First release transaction:

1. Normalize request and compute its canonical comparison form.
2. Begin local PostgreSQL transaction.
3. Lock the work order and any existing release by work order/release ID.
4. Resolve and validate exact route/config without a latest-version query.
5. Lock/read lifecycle operations, bindings, execution evidence, and relevant
   station queue rows.
6. Classify first call, exact replay, or deterministic conflict.
7. Compute the full deterministic lifecycle/binding pair set, count, and
   digest before the first write.
8. Insert the release sidecar row with that count/digest.
9. Generate all lifecycle operations or validate the explicit operation set.
10. Insert all binding rows with `binding_source=work_order_release`.
11. Allocate and insert exactly one initial queue row.
12. Set or retain the work-order `queued` status.
13. Re-read and validate count/digest and the full snapshot.
14. Commit and return `released=true`.

Replay returns from the classification path after a read-only invariant check
with `released=false`. No stage may commit independently.

## Idempotency

- `release_id` is the stable request identity; `order_id` has its own unique
  one-release constraint.
- Generated operation IDs are UUIDv5 values derived from a fixed namespace,
  release ID, and route-operation ID.
- Binding IDs use a separate fixed UUIDv5 namespace over the same stable
  release/config-operation inputs.
- Canonical pair ordering is route `sequence_no`, then route-operation ID as a
  defensive stable key; sequence ties are rejected.
- The digest includes every ordered config/lifecycle pair and release mode.
- Exact replay compares all identity/audit request fields, the complete pair
  set, count/digest, lifecycle snapshots, and initial queue identity.
- Exact replay returns persisted timestamps and rows unchanged.
- A retry after a rolled-back first attempt computes the same UUIDs but still
  creates rows only once when it eventually commits.

## Conflict Handling

Map domain conflicts to status `409`:

- `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT`: release ID belongs to another work
  order or immutable request.
- `WORK_ORDER_ROUTE_ALREADY_RELEASED`: work order has a different immutable
  release.
- `WORK_ORDER_ROUTE_VERSION_CONFLICT`: route code/version differs.
- `WORK_ORDER_RELEASE_MODE_CONFLICT`: replay changes mode.
- `WORK_ORDER_RELEASE_MAPPING_CONFLICT`: pair set differs or one operation is
  mapped twice.
- `WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT`: orphan/partial pre-existing
  binding set exists.
- `WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH`: missing/extra operation.
- `WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH`: station, code, or sequence
  validation fails.
- `WORK_ORDER_RELEASE_QUEUE_CONFLICT`: initial queue is missing, duplicated, or
  incompatible on replay/first call.
- `WORK_ORDER_RELEASE_NOT_RELEASABLE`: status/execution evidence forbids
  release.

Use specific `404` errors for missing work order/route/config/lifecycle parent
and `400`/`422` for malformed request data. Preserve PostgreSQL error cause in
internal logging without exposing SQL or secrets.

## Queue Integration

- Insert only the first ordered lifecycle operation at release.
- Allocate rank under a station-scope lock and respect both active-rank and
  existing legacy station/order uniqueness.
- Use status/source `queued / work_order_release`.
- Store lifecycle operation UUID in the queue; do not add config identity.
- Replay verifies the exact row without update, re-ranking, or timestamp
  change.
- Generated successors remain `planned` until existing lifecycle completion
  logic queues them.
- Before future successor activation, verify the new-release invariant that
  the successor has a binding, but resolve runtime config from that binding in
  the runtime boundary rather than the queue table.

## Lifecycle Boundaries

Phase 5B-5E owns only:

```text
work-order release
-> lifecycle operation set
-> complete bindings
-> initial queue
```

It does not own:

```text
runtime closed
-> lifecycle operation completed
-> successor operation queued
```

The second flow is designed in Phase 5F and implemented/smoked in Phase 5G.
Until then, OP10 runtime close and lifecycle status remain intentionally
separate, matching the verified OP10 evidence.

## Legacy Handling

- No existing work order, operation, binding, runtime row, or queue row is
  automatically migrated.
- Retained V1 existing-state replay remains compatible.
- New release calls reject partial or ambiguous legacy state.
- No station/code/sequence-based migration exists.
- Explicit mapping mode is not a backfill tool; it applies only to a clean,
  unreleased, complete operation set with stable UUIDs.
- A manual backfill/migration proposal requires separate design, approval,
  source backup, and evidence.

## Unit-Test Plan

Schema/read tests:

- exact sidecar columns, constraints, FKs, indexes, and idempotent migration;
- malformed pre-existing table rejection;
- reads by work order/release ID, case/whitespace rules, missing rows, and
  read-only behavior;
- exact route resolution requires code and version.

Generated-mode tests:

- deterministic UUIDv5 values and stable ordering;
- correct snapshot fields and first/successor statuses;
- complete binding creation and digest;
- exact replay returns unchanged rows/timestamps and no new UUID;
- retry after injected rollback reuses the same computed UUID set.

Explicit-mode tests:

- complete exact mapping succeeds;
- wrong work order, wrong route version, duplicate/missing/extra mapping,
  terminal operation, and snapshot mismatch fail;
- exact complete release replay accepts unchanged existing pairs;
- orphan or partial pre-existing binding set fails.

Transaction/queue tests:

- injected failure at each write stage rolls back all artifacts;
- concurrent same request resolves to one first call plus one replay;
- concurrent different request resolves to one commit plus one conflict;
- initial queue only, rank conflict, legacy uniqueness, terminal initial
  operation, and no duplicate queue;
- config, runtime, events, approvals, production flow, inventory, and retained
  V1 are untouched.

API tests are excluded until Phase 5H.

## Disposable PostgreSQL Smoke Plan

Use
`docs/runbooks/work_order_release_route_binding_isolated_smoke_plan.md`.

The smoke must restore a fresh logical source dump into a disposable clone,
apply only required additive migrations and Canonical V2 seed to the clone,
create clone-only candidates, and prove first release, exact replay, conflicts,
rollback, complete immutable bindings, initial queue idempotency, lifecycle
counts, config no-write, audit scope, source 15-table integrity, cleanup, and
health. It must never use source `mes` as a template or smoke target.

## Source Database Apply Boundary

Phase 5B-5E does not automatically apply anything to source `mes`.

After migration review and disposable first-apply/reapply/malformed-schema
evidence, a separate explicitly approved source-apply task must:

1. capture and retain a fresh logical backup;
2. record the 15-table source baseline and release-table absence/presence;
3. apply only the reviewed release migration;
4. verify exact shape and no existing-table writes;
5. retain evidence and provide an explicit rollback/restore decision.

Core release helper must stay disabled against source until its own disposable
smoke passes and source enablement receives separate approval.

## API Phase

No endpoint or feature flag is added before core transaction evidence.

Phase 5H may add one narrow endpoint around
`release_work_order_to_route(...)`, with authentication/authorization, request
validation, domain error mapping, and replay response semantics. The endpoint
must not implement transaction logic independently or select a route version
for the caller.

## FERP Integration Phase

FERP may provide work-order identity/planning fields. Future integration must
provide exact route code/version or require explicit MES user selection.

If FERP provides lifecycle operations, Phase 5H must first define stable local
UUID resolution and the complete explicit mapping payload. Acknowledgement and
outbox delivery occur after local commit and are not part of a distributed
transaction. No FERP payload or adapter changes occur in Phase 5A-5G.

## MESQL Boundary

Current MESQL pull remains a separate import/upsert path and is not a route
source of truth. Phase 5A-5G does not change its payload, database, polling,
upsert, queue, outbox, or operation completion behavior.

Phase 5H must decide how a clean imported operation set enters explicit
mapping mode and how a pre-existing MESQL queue row is reconciled. Until that
decision, local release rejects an incompatible imported queue rather than
adopting or rewriting it.

## Rollback Strategy

Schema draft:

- Prefer forward-only additive correction before source apply.
- Any rollback SQL is separately reviewed and must not drop a populated release
  sidecar automatically.
- Source recovery uses the retained logical backup only under explicit
  approval.

Write helper:

- Transaction rollback is the only first-call failure behavior.
- No compensating deletes or rebinding updates are exposed.
- Feature enablement can be disabled without deleting committed release audit.
- A committed incorrect release has no MVP mutation path; correction requires
  a future auditable supersession design.

## Phase Breakdown

### Phase 5B — Schema/Contract Draft

- Draft the additive work-order route release sidecar migration, schema plan,
  helper contract, apply runbook, and migration tests.
- Do not apply to source or create release rows.

### Phase 5C — Release Read/Validation Helpers

- Implement exact route/version reads, release snapshot reads, canonical pair
  digest, and read-only validations.
- Prove no mutation on unit tests and a disposable clone.

### Phase 5D — Controlled Atomic Write Helper

- Implement `route_generated` first, transaction-scoped binding creation,
  deterministic UUIDs, initial queue insertion, replay/conflict handling, and
  rollback tests.
- Add explicit mapping only after its full set-equality tests pass.

### Phase 5E — Disposable Clone Release Smoke

- Execute first release, exact replay, route/mapping/partial conflicts,
  injected rollback, queue uniqueness, complete immutable bindings, source
  integrity, cleanup, and health evidence.

### Phase 5F — Runtime-to-Lifecycle Completion Bridge Design

- Define the one-way idempotent contract from runtime `closed` to lifecycle
  completion and existing successor activation, including binding checks and
  event/audit dedupe.

### Phase 5G — Completion Bridge Implementation and Smoke

- Prove OP10 runtime `closed` causes exactly one OP10 lifecycle completion and
  one OP20 queue activation, without duplicate events/queues or config writes.

### Phase 5H — API/FERP Boundary

- Only after core transaction and completion bridge evidence, design/implement
  API authorization, FERP explicit route/mapping contract, acknowledgements,
  and MESQL reconciliation as separately reviewed changes.

## Acceptance Criteria

- Work-order release persists one exact process-route ID/code/version and mode.
- Route selection is explicit and version-frozen.
- Generated lifecycle UUIDs are server-controlled and retry-stable.
- Explicit mapping has exact route/lifecycle set equality with no extras.
- Every new-release lifecycle operation has one immutable binding from the
  selected version before commit.
- Release record, operations, bindings, initial queue, and queued work-order
  state are one atomic transaction.
- Exact replay returns `released=false` and causes zero mutation.
- All listed conflicts are deterministic `409` responses with zero partial
  write.
- Only the first operation is queued at release; no duplicate queue exists.
- Existing successor logic remains lifecycle-identity based.
- Runtime close and lifecycle completion remain separate through Phase 5E.
- Legacy/V1, config/master, runtime, audit, approval, production flow,
  inventory, FERP, and MESQL state remain unchanged unless a later phase
  explicitly owns them.
- Disposable smoke proves source 15/15 integrity and clone cleanup.

## Out of Scope

- Any Phase 5A implementation or commit of these design files.
- Source database apply, Docker execution, `psql`, `pg_dump`, or smoke
  execution in this planning task.
- Existing-data backfill, route inference, config edits, or V1 migration.
- Runtime-to-lifecycle completion implementation before Phase 5G.
- API/feature flag, Kiosk, IoT/MQTT, Observer, OEE/KPI, inventory, approval,
  production-flow, FERP, or MESQL implementation.
- Push, PR, rebase, reset, amend, or deployment.
