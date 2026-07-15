# Work-Order Release Transaction Primitive Design

## Status

`READY_FOR_PRIVATE_PRIMITIVE_IMPLEMENTATION`

Last updated: `2026-07-15`.

This document is the Phase 5D-A decision record. It designs the private
cursor-scoped transaction primitives but creates no Python, SQL migration,
database row, API, or feature flag.

## Scope

The initial writer owns one atomic local PostgreSQL transaction that persists:

```text
immutable release row
-> deterministic lifecycle-operation snapshots
-> complete immutable route-operation bindings
-> one initial queue row
-> release-equivalent work-order status
```

Only `route_generated` with `release_source=local_planning` is enabled.

## Existing Repository Write Model

- `mes.work_orders` has nullable lifecycle/status fields and mutable JSON
  payload/metadata; it has no distinct `released` status.
- `mes.work_order_operations` defaults UUIDs with `gen_random_uuid()` and has
  unique `(order_id, operation_no)` and `(order_id, sequence_no)` keys.
- Existing MESQL import uses `ON CONFLICT DO UPDATE` and can rewrite lifecycle
  snapshots. That SQL is not safe for immutable route-generated release.
- The standalone binding writer opens and commits its own transaction. Its
  mapper and equality logic may be extracted, but its public wrapper must not
  be called from the release transaction.
- Existing successor activation calculates `MAX(queue_rank)+1` without a
  station-scoped serialization primitive. Release needs a dedicated allocator.
- `uq_mes_station_queue_station_active_rank` covers exactly
  `status IN ('queued', 'active', 'pending_approval')`.

## Public Writer Boundary

The future public signature remains:

```python
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

The response is:

```python
{
    "released": True | False,
    "release": {...},
    "work_order": {...},
    "operations": [...],
    "bindings": [...],
    "initial_queue": {...} | None,
}
```

First commit returns `released=True`; an exact immutable replay returns
`released=False` and current authoritative operational state.

`explicit_existing_operation_mapping` is recognized but returns
`409 WORK_ORDER_RELEASE_MODE_NOT_ENABLED`. FERP/MESQL sources, migration
backfill, reroute, cancellation, and supersession remain disabled.

## Transaction Boundary

The public writer owns exactly one `database_connection`, one PostgreSQL
transaction, and one cursor at `READ COMMITTED` isolation:

1. Normalize and validate the request and JSON objects.
2. Lock/read the target work order.
3. Lock/read candidate release rows by order ID and release ID.
4. Resolve exact route, route item, and ordered route operations.
5. Read/lock existing lifecycle, binding, evidence, and queue state.
6. Classify first release, immutable replay, or deterministic conflict.
7. Derive every operation UUID, binding ID, static snapshot, count, and digest.
8. Insert release row.
9. Insert every deterministic lifecycle operation.
10. Insert every immutable binding.
11. Serialize station rank allocation and insert the initial queue row.
12. Set work order to release-equivalent `queued` state.
13. Read and validate the authoritative snapshot on the shared cursor.
14. Exit the transaction context and commit.

Any exception before transaction-context success leaves no release row,
operation, binding, queue row, status change, or timestamp change.

Private cursor-scoped primitive inventory:

```python
_select_work_order_for_release_cursor(cursor, work_order_id)
_select_releases_for_update_cursor(cursor, work_order_id, release_id)

_select_exact_process_route_cursor(cursor, route_code, route_version)
_select_route_item_cursor(cursor, item_code)
_list_process_route_operations_cursor(cursor, process_route_id)

_list_existing_work_order_operations_for_update_cursor(cursor, work_order_id)
_list_existing_release_bindings_for_update_cursor(cursor, work_order_id)
_list_work_order_release_evidence_cursor(cursor, work_order_id)
_select_initial_queue_cursor(cursor, work_order_id, work_order_operation_id)
_lock_station_queue_scope_cursor(cursor, station_code)

_insert_work_order_route_release_cursor(cursor, release_snapshot)
_insert_route_generated_work_order_operation_cursor(cursor, operation_snapshot)
_insert_work_order_operation_route_binding_cursor(cursor, binding_snapshot)
_insert_initial_station_queue_cursor(cursor, queue_snapshot)
_update_work_order_released_state_cursor(cursor, work_order_id)

_validate_work_order_release_invariants_cursor(cursor, expected_snapshot)
_read_work_order_release_snapshot_cursor(cursor, work_order_id)
```

Every primitive accepts the caller-owned cursor, returns database/domain rows
rather than API responses, and performs no connection open, transaction open,
commit, rollback, retry, or exception masking. The combined release selector
locks both possible identities in one stable `release_pk` order, avoiding
request-dependent lock ordering.

## Lock Ordering

Every route-release transaction uses this order:

1. `mes.work_orders` exact `order_id` row `FOR UPDATE`.
2. All matching release rows selected by
   `order_id = request.order_id OR release_id = request.release_id`, ordered by
   `release_pk`, `FOR UPDATE`.
3. Exact route/item/config reads without row locks.
4. Existing work-order lifecycle rows ordered by
   `work_order_operation_id`, `FOR UPDATE`.
5. Existing binding rows ordered by `binding_pk`, `FOR UPDATE`.
6. Existing execution/evidence rows in stable PK/UUID order when first-release
   eligibility is evaluated.
7. Initial-station transaction advisory lock.
8. Station queue rows ordered by `station_queue_pk`, `FOR UPDATE`.

The advisory lock is acquired only after the initial operation and station are
known. Phase 5D creates only one initial queue, so no multi-station advisory
lock ordering is needed.

## Work-Order Lock

`_select_work_order_for_release_cursor` selects all persisted work-order
fields with `FOR UPDATE`.

First-release eligibility policy requires:

- status `planned`, or `queued` with no release artifacts or execution state;
- normalized product code equal to exact route item code;
- positive target quantity;
- `started_at` and `completed_at` are null;
- no lifecycle operation, binding, queue, runtime state, operation event,
  approval, or production-flow evidence.

Positive target quantity is an initial Phase 5D route-generated eligibility
policy, not a claim that the existing work-order schema enforces positivity.
An already complete immutable release is classified before this first-release
policy, so later work-order status progression does not break idempotency.

## Route and Configuration Reads

- `_select_exact_process_route_cursor` resolves exact normalized route code and
  positive version; no latest/active fallback is permitted.
- `_select_route_item_cursor` reads the route item by exact item code.
- `_list_process_route_operations_cursor` reads the exact route identity in
  `sequence_no, route_operation_id` order.
- The route, route item, and every route operation must be active at first
  release. The set must be nonempty with unique positive sequences.
- The active route item's nonblank `mes.items.unit` supplies lifecycle
  `uom_code`.

Active route-item and unit validation is an initial Phase 5D route-generated
eligibility policy. It is not described as a new database-schema constraint.
Versioned configuration is treated as immutable during release; these reads do
not use `FOR UPDATE` and never mutate config/master rows.

## Deterministic Lifecycle Operations

Each route operation uses the Phase 5C UUIDv5 utility and a dedicated plain
`INSERT`; MESQL upsert SQL and `ON CONFLICT DO UPDATE` are prohibited.

Exact inserted fields:

| Field | Value |
|---|---|
| `work_order_operation_id` | deterministic UUIDv5 |
| `order_id` | exact work-order ID |
| `mesql_work_order_operation_id` | `NULL` |
| `operation_no` | route `sequence_no` |
| `operation_code` / `operation_name` | exact config snapshot |
| `sequence_no` / `station_code` | exact config snapshot |
| `status` | first `queued`, successors `planned` |
| `planned_quantity` | positive work-order target quantity |
| `good_quantity` / `scrap_quantity` | `0 / 0` |
| `uom_code` | active route-item unit |
| `started_at` / `completed_at` | `NULL / NULL` |
| `payload` | `{}` |
| `metadata` | exact server-owned snapshot below |
| `updated_at` | database `now()` |

Lifecycle metadata is exactly:

```json
{
  "source": "work_order_release",
  "release_id": "<release_id>",
  "process_route_id": "<route_id>",
  "route_code": "<route_code>",
  "route_version": 2,
  "route_operation_id": "<route_operation_id>"
}
```

The static replay snapshot comprises UUID, order ID, null MESQL ID,
operation/sequence identity, code/name/station, planned quantity, UOM, payload,
and metadata. Operational status, good/scrap quantities, started/completed
timestamps, and `updated_at` are mutable and are not immutable replay keys.

## Binding Primitive

`_insert_work_order_operation_route_binding_cursor` uses the shared cursor and
a plain immutable insert. It receives deterministic binding ID, lifecycle UUID,
exact route-operation ID, source `work_order_release`, actor `released_by`, and
metadata exactly `{"release_id":"<release_id>"}`.

Replay validation requires the complete deterministic binding set, including
binding IDs and both sides of every pair. Missing, extra, partial, orphan, or
different pairs are conflicts. Binding timestamps are returned but never
rewritten. Existing public binding helper signature and behavior remain
unchanged.

## Initial Queue Primitive

The unique smallest route sequence is the initial operation. A sequence tie is
a route-validation failure.

`_lock_station_queue_scope_cursor` executes:

```sql
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'mes:work_order_release:station_queue:' || %(station_code)s,
        0
    )
)
```

It then locks station rows by PK and allocates `MAX(queue_rank)+1` using exactly
the partial-index predicate:

```sql
status IN ('queued', 'active', 'pending_approval')
```

`ready` is deliberately excluded because it is not in the current database
uniqueness predicate. No schema change is introduced.

The inserted queue row has exact lifecycle UUID/order/station, status `queued`,
source `work_order_release`, and:

```json
// payload
{
  "order_id": "<work_order_id>",
  "work_order_operation_id": "<uuid>",
  "operation_no": 10,
  "sequence_no": 10,
  "station_code": "<station_code>",
  "status": "queued"
}
```

```json
// metadata
{"source":"work_order_release","release_id":"<release_id>"}
```

Route/config identity is resolved through the binding and is not copied into
the queue. On immutable replay, queue identity fields must remain unambiguous,
but status, rank, and operational timestamps may have progressed and are not
replay conflicts.

## Work-Order Status Transition

Only a true first release updates the work order:

```sql
status = 'queued', updated_at = now()
```

The update occurs even when the eligible clean pre-release status was already
`queued`, recording the first release transition time. Business payload and
metadata are not merged or rewritten. Replay never updates work-order status,
timestamps, payload, or metadata; later active/completed/cancelled operational
state alone does not invalidate the immutable release replay.

## Insert Ordering

Selected order is:

```text
release -> lifecycle operations -> bindings -> initial queue -> work order
```

The release row is the semantic source of truth and exposes order/release
unique races before child work. Its FKs require only the already locked work
order and resolved route. All later rows remain transaction-local, so any
failure rolls the release row back with them. Inserting children before release
would weaken early identity classification without improving FK ordering.

## Snapshot Readback

Private full-state validators read every persisted lifecycle and binding field
needed for immutable comparison. The response snapshot reuses the Phase 5C
cursor-scoped read primitive and returns current mutable operational values.

Final invariant validation requires:

- one exact release row and correct count/digest;
- the complete deterministic static lifecycle snapshot set;
- the complete immutable binding set;
- one unambiguous initial queue identity;
- the first-release work order update on `released=True`.

It does not require mutable operation/work-order status, quantities, queue
status/rank, or operational timestamps to retain their release-time values on
`released=False` replay.

## Error Propagation

Missing parents:

- `WORK_ORDER_NOT_FOUND` (`404`);
- `PROCESS_ROUTE_NOT_FOUND` (`404`);
- `ROUTE_OPERATION_NOT_FOUND` (`404`).

Deterministic conflicts:

- `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT` for release-ID ownership or immutable
  request/source/actor/metadata mismatch;
- `WORK_ORDER_ROUTE_ALREADY_RELEASED` for another release ID on the work order;
- `WORK_ORDER_ROUTE_VERSION_CONFLICT` for route identity/version mismatch;
- `WORK_ORDER_RELEASE_MODE_CONFLICT` for mode mismatch;
- `WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH` for missing/extra operations;
- `WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH` for static snapshot mismatch;
- `WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT` for incomplete/orphan bindings;
- `WORK_ORDER_RELEASE_MAPPING_CONFLICT` for a different complete pair/digest;
- `WORK_ORDER_RELEASE_QUEUE_CONFLICT` for missing, duplicate, or wrong immutable
  initial-queue identity, or active-rank collision;
- `WORK_ORDER_RELEASE_NOT_RELEASABLE` for first-release eligibility failure.

After any `23505`, the first transaction must fully roll back and its context
must close. Authoritative classification then opens a new connection,
transaction, and cursor. Constraint names may route the readback, but persisted
rows decide replay/conflict. Unknown or unclassified PostgreSQL errors
propagate unchanged.

## Runtime Completion Boundary

Release creates no execution state or step instance and executes no operation.
Runtime initialization remains compatible with deterministic bindings.
Lifecycle completion and successor queue activation remain Phase 5F/5G.

## Deferred Modes

- `explicit_existing_operation_mapping` implementation;
- FERP/MESQL release sources and reconciliation;
- reroute, cancellation, supersession, and migration backfill;
- config immutability hardening outside the writer;
- API/authentication/feature flag.

## Out of Scope

- Python, test, migration, DB, Docker, or API implementation in Phase 5D-A;
- lifecycle, binding, queue, status, runtime, event, approval, flow, or
  inventory mutation;
- latest-active, station/code/sequence, product-route, or metadata inference;
- Phase 5D-B private primitive implementation.

## Phase 5D-A Replay Decision Amendment

This design supersedes the strict replay language in the Phase 5B helper
contract wherever that language requires release-time operational status,
quantity, queue rank/status, or timestamps to remain unchanged forever.

Immutable replay equality is limited to the release row, deterministic static
lifecycle snapshots, and complete immutable binding set, plus unambiguous
initial-queue identity. Work-order/operation statuses, good/scrap quantities,
start/completion/update timestamps, and queue status/rank are operational state.
Their legitimate progression does not turn the same immutable request into a
conflict. Replay returns `released=False`, performs no writes, and returns the
current authoritative snapshot.
