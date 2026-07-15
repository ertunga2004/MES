# Work-Order Release and Route-Binding Decision

## Status

`ACCEPTED_FOR_IMPLEMENTATION_PLANNING`

Last updated: `2026-07-15`.

This document selects a target architecture only. It does not authorize or
implement a migration, helper, API, database apply, lifecycle write, binding
write, queue mutation, FERP change, or MESQL change.

## Context

Canonical V2 now has an explicit immutable
`work_order_operation_id -> route_operation_id` sidecar binding and runtime
initialization validates that binding. The disposable OP10 execution smoke
then proved the complete runtime step flow, but it also proved the remaining
boundary: runtime OP10 reached `closed` while the lifecycle operation and its
station queue row both remained `queued`.

The repository still has no production contract that selects a route version
for a work order, freezes that selection, creates or maps the full lifecycle
operation set, creates every operation binding, and creates the initial queue
row atomically. This decision defines that missing release boundary without
combining it with runtime-to-lifecycle completion.

## Verified Current Repository Behavior

Work-order and operation storage:

- `db/migrations/001_initial_mes_schema.sql:6` defines
  `mes.work_orders`. It has product and lifecycle fields but no route code,
  route version, process-route ID, or release ID.
- `db/migrations/008_mesql_integration_v2.sql:10` defines
  `mes.work_order_operations`. PostgreSQL generates its UUID by
  `gen_random_uuid()` when an insert does not provide one. The table has unique
  `(order_id, operation_no)` and `(order_id, sequence_no)` constraints but no
  config identity.
- `db/migrations/004_station_execution_schema.sql:55` gives each process route
  a stable `route_id` and unique `route_code + version` identity.
- `db/migrations/004_station_execution_schema.sql:91` gives each route
  operation a stable `route_operation_id`; route sequence and operation code
  are unique only inside one route version.

JSON/FERP runtime import and mirror path:

- `mes_web/app.py:2292` exposes the work-order import endpoint and delegates to
  `mes_web/oee_state.py:4218::import_work_orders`.
- `mes_web/oee_state.py:1416::_normalize_work_order_row` normalizes a flattened
  work-order row. Its current fields include `sequenceNo`,
  `workStationCode`, and `operationCode` at lines 1524 and 1538-1539, but not
  route code, route version, route-operation ID, or a multi-operation mapping.
- `mes_web/app.py:1010::sync_work_order_runtime` invokes the configured mirror
  path. `mes_web/db/work_order_transition_writer.py:470::_execute_transition_write`
  upserts work orders/events and derives station queue rows at lines 491-503;
  it does not create `mes.work_order_operations` or bindings.
- Runtime start/finish endpoints in `mes_web/app.py:2414` and following mutate
  JSON/runtime work-order state. They are not a route release transaction.

MESQL pull path:

- `mes_web/db/mesql_v2.py:1763::upsert_mesql_queue_items` uses one database
  transaction and, for every queue payload, upserts a work order, one lifecycle
  operation, and its queue row at lines 1787-1830.
- `_build_operation_params` at line 1655 takes operation code, sequence, and
  station from the payload with explicit fallbacks. `UPSERT_OPERATION_SQL` at
  line 327 inserts or updates by `(order_id, operation_no)` and returns the
  persisted local UUID.
- This is an existing-operation/import reality, but it does not select or
  freeze a process route and does not create route bindings.

Release and route selection:

- Repository search found no `release_work_order` or equivalent helper that
  performs route selection and release.
- The current effective release-like states are the imported/mirrored
  `queued` work-order and queue rows. There is no distinct `released` status.
- No work-order row persists route/version today. Active route flags are used
  by config reads, but no discovered work-order creation path selects a latest
  active route version.
- `mes_web/__main__.py:278-393` exposes station-execution config reads. Those
  routes do not create or release work orders.

Queue and successor behavior:

- `db/migrations/006_station_queue.sql:1` originally identifies a queue row by
  station and work order; migration 008 additively adds
  `work_order_operation_id` and a unique station/operation index.
- `mes_web/db/mesql_v2.py:1352::SELECT_SUCCESSOR_OPERATION_SQL` selects the
  first nonterminal operation with a larger `sequence_no`, ordered by
  sequence then operation number. The schema already makes work-order sequence
  unique, so a sequence tie is rejected before this query can use its
  operation-number tie-breaker.
- `_activate_successor_operation` at line 3841 updates that lifecycle
  operation and upserts its queue by lifecycle operation identity. It uses
  neither operation code nor station to choose a successor and does not read
  the binding sidecar.

These findings answer the creation-model question: the repository contains
two separate paths, one that imports/mirrors work orders without a lifecycle
operation set and one that imports/upserts explicit lifecycle operations.

## Problem Statement

A production release must establish one durable, reviewable answer to all of
the following before execution begins:

- Which exact route code and version was selected for the work order?
- Which lifecycle operation instance corresponds to every required route
  operation?
- Is the mapping complete, immutable, and from one route version?
- Which lifecycle operation is the initial station queue identity?
- Can an exact retry return the same release and UUIDs without mutation?
- Can conflicting, partial, or concurrent attempts fail without partial rows?

Operation code, station, sequence, runtime metadata, or an active flag cannot
answer those identity questions safely.

## Identity Model

- Work-order identity: API `work_order_id`, stored as existing
  `mes.work_orders.order_id`.
- Release identity: caller-generated or orchestrator-generated stable,
  nonblank `release_id`, globally unique in the local MES database.
- Route identity: explicit `route_code + route_version`, resolved once to
  `mes.process_routes.route_id` (`process_route_id` in the release contract).
- Lifecycle operation identity: `work_order_operation_id` UUID.
- Config operation identity: stable `route_operation_id`.
- Binding identity: existing immutable binding row and its stable `binding_id`.
- Queue identity: `work_order_operation_id`; station and rank are operational
  placement fields.

The work-order release record proves the frozen route and complete operation
set. Individual binding rows prove each lifecycle/config-operation pair.

## Route Selection Contract

The caller must supply exact `route_code` and positive `route_version`. The
release helper resolves exactly one `process_routes` row and validates:

- the resolved row has the same code/version and is active at selection time;
- it is compatible with the work order's product/item contract;
- it has at least one active route operation;
- every selected route operation and required execution configuration passes
  the existing config validation contract;
- route-operation sequences are positive and unique.

The active flag is a releasability guard after exact resolution, never a
selector. A later route version does not affect a released work order. A route
that later becomes inactive remains the historical target of existing release
and binding rows. Existing route or route-operation rows are never updated by
release.

For the MVP, product compatibility is strict equality between the normalized
work-order `product_code` and the selected process route `item_code`. A future
FERP product-to-item catalog mapping must be explicit and separately approved;
product code must not silently select a route.

## Evaluated Models

Model A, route-generated lifecycle operations:

- Strongest canonical identity for new MES-controlled work: the frozen route
  operation set directly produces lifecycle rows and bindings.
- It fits the JSON/FERP mirror path, which currently has no complete database
  lifecycle operation set.
- By itself, it would reject or replace legitimate operations already imported
  through MESQL/ERP-style paths.

Model B, explicitly mapped existing operations:

- Preserves lifecycle rows already created by an integration path.
- Requires stable lifecycle UUIDs and a complete caller-supplied mapping.
- By itself, it makes simple local work-order release unnecessarily dependent
  on external operation creation.

Model C, controlled hybrid:

- Has two explicit modes: `route_generated` and
  `explicit_existing_operation_mapping`.
- The modes never mix in one release request.
- It matches the two independently verified repository creation paths.

## Selected Model

Select Model C, controlled hybrid.

`route_generated` is the default and only Phase 5D mode for new local MES work
orders. It creates the entire lifecycle operation set from the exact selected
route version.

`explicit_existing_operation_mapping` is a controlled compatibility mode for
work orders whose lifecycle operations already exist, such as MESQL/ERP import
results. It never creates, replaces, or infers an operation; it validates a
complete explicit mapping.

A request containing both generated-operation instructions and explicit
mappings fails. The release record persists the chosen mode, so replay cannot
switch modes.

## Rejected Inference Models

The following are rejected as identity mechanisms:

- station-code inference;
- operation-code inference;
- sequence inference;
- station plus operation-code inference;
- station plus sequence inference;
- latest-active route selection;
- silent product-code route selection;
- binding creation from runtime metadata;
- automatic binding during execution.

Station, operation code, and sequence are mandatory snapshot validations in
explicit mapping mode, but they never select a route operation.

## Work-Order Route Persistence

Select an additive immutable work-order sidecar named
`mes.work_order_route_releases`. Extending `mes.work_orders` would mix passive
mirror/import data with a new release lifecycle. Using binding rows alone would
not provide a stable release ID, chosen mode, frozen route-level audit, or a
single completeness record.

The Phase 5B schema draft should contain at least:

- `release_pk BIGSERIAL PRIMARY KEY`;
- `release_id TEXT NOT NULL UNIQUE` with a nonblank check;
- `order_id TEXT NOT NULL UNIQUE` with FK to `mes.work_orders(order_id)`;
- `process_route_id TEXT NOT NULL` with FK to
  `mes.process_routes(route_id)`;
- snapshot `route_code TEXT NOT NULL` and `route_version INTEGER NOT NULL`;
- controlled `release_mode TEXT NOT NULL`;
- controlled `release_source TEXT NOT NULL`;
- nonblank `released_by TEXT NOT NULL`;
- `released_at TIMESTAMPTZ NOT NULL`;
- positive `route_operation_count INTEGER NOT NULL`;
- nonblank `operation_set_digest TEXT NOT NULL`;
- object `metadata JSONB NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`.

The schema/helper contract must prove that `process_route_id`, route code, and
version describe the same parent row. The release has one-to-one cardinality
with a work order in the MVP and is insert-once: no update, delete, re-route,
soft delete, or supersession path is permitted.

`operation_set_digest` is computed over the canonical ordered list of
`route_operation_id -> work_order_operation_id` pairs. Together with the
stored count and full binding query, it detects missing, extra, mixed-version,
or partial binding sets and proves OP10/OP20 came from one frozen version.

## Lifecycle Operation Contract

In `route_generated` mode:

1. Load every selected route operation ordered by `sequence_no`.
2. Generate each lifecycle UUID server-side with UUIDv5 using a fixed,
   version-controlled MES release namespace and canonical input
   `release_id + newline + route_operation_id`.
3. Copy `operation_code`, `operation_name`, `sequence_no`, and `station_code`
   as lifecycle snapshots. Set `operation_no = sequence_no` under the current
   schema's uniqueness contract.
4. Copy work-order target quantity to planned quantity where applicable.
5. Create the first operation as `queued` and later operations as `planned`.

UUIDv5 was selected over random-per-attempt generation, caller-supplied UUIDs,
or an extra release-operation map. It is server-controlled and retry-stable;
an exact replay resolves the same UUIDs even after a rolled-back attempt.
Persisted readback remains authoritative after the first commit.

In `explicit_existing_operation_mapping` mode:

- each lifecycle UUID must exist and belong to the same work order;
- every selected route operation must appear exactly once;
- every lifecycle operation must appear exactly once;
- the work order may have no extra lifecycle operations in the MVP;
- selected route-operation IDs must all belong to the frozen route version;
- station, operation code, and sequence must equal their route-operation
  snapshots or the request fails with a snapshot-mismatch conflict;
- terminal, active, or already-executed operation sets are not releasable.

Strict set equality is deliberate: extra imported operations would make
successor sequencing and route completeness ambiguous. A future optional,
rework, or non-route operation policy is deferred.

## Operation Binding Contract

Every selected lifecycle operation receives exactly one existing
`mes.work_order_operation_route_bindings` row with source
`work_order_release`. The public release actor is recorded as `bound_by`; the
release ID is included as non-identity audit metadata.

Binding IDs are also server-controlled and retry-stable: use a separate fixed
UUIDv5 namespace over `release_id + newline + route_operation_id`, rendered as
a stable text identifier. A replay cannot mint a new binding identity.

Binding creation must use a transaction-scoped internal primitive operating on
the release transaction's cursor/connection. The current standalone binding
helper semantics may be reused, but it must not open or commit an independent
transaction per row.

On an exact replay of an already complete release, identical existing binding
pairs are accepted and returned unchanged. On a first release attempt, any
pre-existing binding set without the matching complete release record is a
conflict; the helper does not adopt or complete it automatically. A different
binding is always a conflict. Binding rows remain immutable.

## Release Transaction Boundary

One local PostgreSQL transaction performs:

1. Validate and lock the work order.
2. Resolve and validate the exact route code/version and its ordered config.
3. Lock/read any existing release, lifecycle operations, bindings, and relevant
   queue rows.
4. Classify the call as first release, exact replay, or conflict.
5. Compute the complete deterministic operation/binding pair set, count, and
   digest before the first write.
6. Insert the immutable work-order release record with that count/digest.
7. Generate lifecycle operations or validate the complete explicit mapping.
8. Insert all immutable operation bindings.
9. Insert or validate exactly one initial station queue row.
10. Set or retain the current release-equivalent work-order status `queued`.
11. Re-read and validate count, digest, route coverage, queue, and audit
    snapshot, then commit.

The repository has no distinct `released` status, so Phase 5D uses `queued` as
the release-equivalent. It rejects `active`, completed, cancelled/canceled, or
otherwise terminal work orders. A `queued` work order is eligible only when it
has no incompatible release, operation, binding, queue, or execution state.

## Idempotency and Conflict Model

Stable idempotency identity is `release_id`; `order_id` is independently
unique in the release sidecar. Exact replay compares at least:

- release ID and work-order ID;
- route code, version, and resolved process-route ID;
- release mode, source, actor, and identity-bearing metadata policy;
- the complete generated or explicit operation pair set;
- operation count/digest and initial queue identity.

Exact replay returns `released=false` and the unchanged release, work order,
operations, bindings, and initial queue. It creates no UUID, row, timestamp,
event, or status change.

Recommended deterministic HTTP/domain conflicts, all status `409`:

- `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT`;
- `WORK_ORDER_ROUTE_ALREADY_RELEASED`;
- `WORK_ORDER_ROUTE_VERSION_CONFLICT`;
- `WORK_ORDER_RELEASE_MODE_CONFLICT`;
- `WORK_ORDER_RELEASE_MAPPING_CONFLICT`;
- `WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT`;
- `WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH`;
- `WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH`;
- `WORK_ORDER_RELEASE_QUEUE_CONFLICT`;
- `WORK_ORDER_RELEASE_NOT_RELEASABLE`.

Missing work order, process route, route operation, or lifecycle operation uses
a specific `404`. Invalid request shape uses `400` or `422`. Database unique
violations caused by a concurrent call are re-read and classified as exact
replay or one of the same deterministic conflicts; they are not exposed as a
generic server error.

## Queue Contract

Release creates only the first operation's queue row. The first operation is
the selected route operation with the smallest unique `sequence_no`; route
schema uniqueness makes a tie invalid.

The queue row uses:

- identity `work_order_operation_id`;
- the lifecycle snapshot station;
- the next available active rank selected while the station queue is locked;
- status `queued` and source `work_order_release`.

Current uniqueness by station/operation and station/active-rank remains in
force; the older station/order uniqueness is also respected. An exact replay
must find exactly the same queue row and return it without rewriting rank,
status, source, payload, metadata, or timestamps. A different or duplicate row
is a conflict. A terminal initial lifecycle operation is not releasable.

No route-operation ID is added to `station_queue`: queue identity remains the
lifecycle operation, while config identity is resolved through its binding.

## Successor Activation Boundary

Existing successor activation can remain sequence-based lifecycle logic after
release because the release transaction validates a complete, unique sequence
snapshot and binds every successor before the first queue insert. It does not
need to select config identity.

The existing successor helper does not currently require a binding. New
release-created operations nevertheless must all have bindings; a Phase 5G
completion bridge should verify that invariant before completing OP10 and
activating OP20. OP20 queue activation continues to use OP20's
`work_order_operation_id`; its runtime config is separately resolved through
OP20's binding.

## Runtime Completion Boundary

Release and runtime completion are separate phases:

- Phase 1: release record, lifecycle operations, complete bindings, and initial
  queue.
- Phase 2: runtime `closed` to lifecycle operation completion and successor
  activation.

The OP10 smoke proved runtime `closed` currently leaves lifecycle/queue
`queued`. Phase 5D must not pretend that runtime close completes lifecycle or
activate a successor. Phase 5F designs the bridge; Phase 5G implements and
smokes OP10 lifecycle completion followed by OP20 queue activation.

## Legacy Compatibility

- Existing released/active/historical work orders receive no automatic
  backfill.
- Retained V1 historical existing-state replay continues without a binding
  table dependency.
- Work orders passing through the new release contract cannot remain partially
  or wholly unbound.
- Partial legacy bindings are rejected, not completed through inference.
- Existing operation codes and stations are never rewritten to resemble
  Canonical V2.
- Manual migration/backfill requires a separate approval, explicit evidence,
  and its own smoke plan.
- Unsupported records remain unbound legacy and cannot use the new production
  release path until explicitly resolved.

## FERP and MESQL Boundary

FERP may remain the source of the work-order ID and planning data. It must send
an explicit route code/version or a MES user must explicitly select them. If a
future FERP payload supplies operation mappings, it must also supply or resolve
stable local lifecycle operation identities through a reviewed contract.

MESQL currently imports/upserts lifecycle operations and queue rows, but it is
not the route-selection source of truth. The work-order release transaction is
atomic in local PostgreSQL. No cross-database transaction is introduced.
FERP acknowledgement, integration outbox, MESQL reconciliation, and external
delivery are Phase 5H or later, after the local core transaction is proven.

## API Boundary

The future core helper is:

`release_work_order_to_route(...)`

Minimum request:

- `release_id`, `work_order_id`, `route_code`, `route_version`;
- `release_source`, `released_by`, `mode`, and object `metadata`;
- complete `operation_bindings` only for explicit mapping mode.

Minimum response:

- `released` boolean;
- `release`, `work_order`, ordered `operations`, ordered `bindings`, and
  `initial_queue` snapshots.

The helper is designed before an endpoint. Phase 5A adds no API, feature flag,
or authorization surface. A future endpoint maps the domain errors above
without changing transaction semantics.

## Failure and Rollback Semantics

Any validation error or injected/database failure rolls back the entire first
release attempt. After rollback there must be no release record, generated
operation, new binding, new queue row, work-order status change, or release
audit side effect.

Validation is performed before writes where possible, but correctness does not
depend on validation order: one transaction, row locks, FK/unique constraints,
and final invariant reads are authoritative. No exception handler commits a
partial result. Exact replay and conflict paths are read-only.

## Security and Audit

- `released_by` is required and identifies a user/service principal; client
  display text is not authoritative.
- `release_source` is controlled. Phase 5D enables only `local_planning`;
  `ferp_import` and `mesql_import` remain reserved until Phase 5H.
- Binding source remains controlled as `work_order_release`.
- Metadata must be a JSON object and cannot override identity, actor, source,
  timestamp, count, or digest fields.
- Release and binding timestamps are server-generated and immutable.
- Database permissions should separate read/validation from the narrow release
  writer role; direct update/delete rights on release and binding sidecars are
  not part of the application role.
- Audit evidence records first call, exact replay, conflicts, injected
  rollback, and final invariant snapshots without logging secrets.
- A released version is changed by creating a new route version, never by the
  release helper editing config rows.

## Deferred Decisions

- Enforcement mechanism for preventing out-of-band edits to an already used
  route/config version; release code already treats versioned config as
  immutable, while DB trigger/permission hardening is separate.
- Optional/rework/non-route lifecycle operations in explicit mapping mode.
- Auditable release cancellation or supersession; the MVP release row is
  insert-once.
- FERP product-to-item catalog mapping and external acknowledgement/outbox.
- MESQL ownership and reconciliation when its imported queue conflicts with a
  local unreleased work order.
- API endpoint shape, authentication policy, and feature flag.
- Runtime-to-lifecycle completion bridge details, handled in Phase 5F.

None of these deferred items changes the selected identity, transaction,
idempotency, or no-inference contract for Phase 5B-5E.

## Consequences

Positive consequences:

- A work order has one immutable selected route version and complete binding
  evidence before execution.
- Local and imported operation paths coexist without silent inference.
- Exact retries are stable and read-only, including lifecycle UUIDs.
- Queue and config identities remain deliberately separate.
- Release failure cannot leave partial lifecycle artifacts.
- Runtime completion can be designed independently against a clean release
  invariant.

Costs and constraints:

- A new additive work-order release sidecar and controlled write helper are
  required.
- Explicit mapping payloads are strict and must include stable lifecycle UUIDs.
- Current FERP and MESQL payload contracts cannot silently opt into release.
- Existing legacy work orders remain unsupported until an explicit migration
  decision is made.
- Completion of OP10 runtime still does not complete lifecycle until the later
  bridge is implemented.
