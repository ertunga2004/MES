# Runtime Completion Bridge Concurrency Plan

## Status

`READY_FOR_COMPLETION_BRIDGE_IMPLEMENTATION`

Last updated: `2026-07-15`.

## Lock Hierarchy

All bridge-aware route-release completion transactions use:

```text
work order
-> release
-> lifecycle rows by UUID
-> bindings by binding PK
-> execution state
-> runtime steps by step_no
-> unique station advisory locks by lexical station code
-> station queue rows by station code and queue PK
```

Applicability marker and schema-readiness reads precede sidecar queries and
locks. Marker absence takes the retained legacy path without touching release
or binding tables. Marker presence requires schema readiness and revalidation
of every initially read identity after the work-order lock.

The bridge and Phase 5D release writer share the advisory namespace:

```text
mes:work_order_release:station_queue:<station_code>
```

The bridge forms a unique set from exact persisted current and successor
stations, sorts it lexically, and locks each station exactly once. Same current
and successor station therefore produces one lock call.

## Duplicate Runtime Finish

Two calls with the same event idempotency/external identity serialize through
the route-release work-order lock before runtime mutation.

- First valid close inserts the finish event, closes runtime, applies the
  bridge, and returns `completion_bridge.bridged=True`.
- The duplicate finds the existing event but does not early-return. It reads
  the closed execution and authoritative bridge state, performs zero writes,
  and returns `completion_bridge.bridged=False`.
- Duplicate event timestamps, lifecycle completion timestamp, queue rank, and
  work-order completion timestamp remain the original values.

Legacy/nonclosed duplicates retain their existing event semantics and always
include `completion_bridge=None`.

## Concurrent Bridge Replay

Two bridge attempts for one lifecycle UUID lock the same work order. The loser
observes the committed first bridge and can return replay only when runtime,
current lifecycle/current queue, successor or final-order state all satisfy the
exact replay contract.

Missing, partial, or incompatible rows are conflicts. No loser inserts a
second queue, reuses a new timestamp, updates rank, or repairs the winner's
state.

## Same-Station Successor Queue

Different work orders completing into one successor station may execute their
runtime/lifecycle work concurrently, but serialize at the shared station
advisory lock. Under that lock they lock station rows and allocate distinct
ranks.

The active-rank set is exactly:

```text
queued, active, pending_approval
```

`ready` and completed current rows are excluded. Different successor stations
remain parallel except for harmless 64-bit advisory-hash collisions.

## Same-Order Operation Races

OP10 and OP20 finish attempts share the work-order lock. OP20 cannot close or
bridge ahead of the transaction that completes OP10 and activates OP20.

After OP10 commits, a waiting OP20 call revalidates its lifecycle status,
binding, runtime identity, and exact current queue before it can proceed. It
cannot skip a lifecycle operation or infer a queue from station/code.

An old OP10 replay after OP20 progression remains valid when OP10 bridge
identity is exact; successor mutable operational progression alone is not a
conflict.

## Final Completion Race

Duplicate final-operation close calls serialize on the work order. One call
completes the final lifecycle/current queue and work order. The next returns
exact replay with `bridged=False` only when final work-order `completed_at`
equals the persisted execution `closed_at`.

Any other incomplete lifecycle row blocks final completion and rolls the whole
triggering runtime transaction back. A conflicting terminal work-order status
or timestamp is never overwritten.

## Queue-Rank Serialization

Advisory locks are acquired before any current or successor queue row lock.
After current queue terminalization, successor rank is computed under the same
transaction locks as:

```sql
SELECT COALESCE(MAX(queue_rank) + 1, 0)
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND status IN ('queued', 'active', 'pending_approval')
```

The database partial unique index remains the final boundary. A known station
queue `23505` rolls back the finish event and every runtime/lifecycle write,
then surfaces `RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT`. There is no automatic
rank retry or second write transaction.

The current station/order unique constraint means a same-work-order route that
revisits the same station cannot insert a second retained queue row under the
present schema. This is a deterministic queue conflict, not an upsert/adoption
case.

## Partial-State Detection

The synchronous bridge never repairs:

- applicability marker with missing schema, release, or binding;
- release count/digest or lifecycle static snapshot mismatch;
- invalid/duplicate lifecycle sequence;
- runtime/binding route mismatch;
- missing, duplicate, or wrong current queue;
- current queue terminal while lifecycle is not completed;
- successor activated before current completion;
- successor lifecycle without exact queue, or queue without exact lifecycle;
- wrong successor source/payload/metadata;
- final operation with another incomplete lifecycle row;
- work order completed at a conflicting timestamp.

Marker absence is an explicit legacy exclusion and does not query the sidecar
schema. `UndefinedTable` is never treated as marker absence.

## Failure Injection

Phase 5G unit and disposable-DB smoke tests use private primitive/cursor or
transaction-proxy seams, never a public production flag. Required points:

1. after triggering finish-event insert;
2. after runtime step completion;
3. after runtime closed transition;
4. after current lifecycle completion;
5. after current queue terminalization;
6. after successor resolution;
7. after successor lifecycle update;
8. after the complete lexical advisory-lock set;
9. after successor queue insert;
10. after final work-order completion;
11. before authoritative bridge snapshot;
12. before transaction exit/commit.

Every point must leave zero event, runtime-step, execution-state, lifecycle,
queue, work-order, approval, flow, completion, outbox, and inventory delta.
The exact triggering retry must then succeed and reuse the original request
identity without partial-state adoption.

## Retry Semantics

- Exact committed duplicate: replay with `bridged=False` and zero writes.
- Fully rolled-back deterministic caller retry: recompute state and may perform
  one new first bridge.
- Queue-rank conflict: no automatic retry; caller may retry explicitly after
  the competing state changes.
- `40P01`, `40001`, unknown `23505`, FK, connectivity, and unknown DB errors:
  propagate after rollback without application retry.
- Reconciliation/repair is not a retry path and remains deferred.

## Acceptance Criteria

- Bridge-aware finish and release replay share a compatible lock prefix.
- Applicability gating occurs before release/binding queries.
- Duplicate event branch reaches bridge classification and returns one true,
  then false replays.
- `completion_bridge` exists in every finish response.
- Station lock set is unique, lexical, and one-call-per-station.
- Same-operation, same-order, same-station, and final races meet the outcomes
  above without deadlock or skipped lifecycle state.
- Rank predicate exactly matches the existing partial unique index.
- Every failure injection rolls back the complete runtime-to-lifecycle unit.
- Retained V1/legacy operations remain unchanged and perform no sidecar read.
- No extra event, approval, production-flow, completion/outbox, inventory,
  API, FERP, or MESQL behavior is introduced.
