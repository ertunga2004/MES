# Work-Order Release Concurrency and Idempotency Plan

## Status

`READY_FOR_PRIVATE_PRIMITIVE_IMPLEMENTATION`

Last updated: `2026-07-15`.

## Concurrency Scenarios

| Scenario | Required result |
|---|---|
| Same work order, exact same request | one `released=True`, one `released=False` |
| Same work order, different route/version | one success, one deterministic `409` |
| Same release ID, different work orders | one success, one `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT` |
| Same station, different work orders | both succeed with distinct queue ranks |
| Failure after any partial write | full rollback; clean retry returns `released=True` |
| Exact request after lifecycle progression | `released=False`; no operational rewind |

## Lock Hierarchy

The normative hierarchy is:

```text
work order row
-> matching release rows ordered by release_pk
-> lifecycle rows ordered by UUID
-> binding/evidence rows ordered by PK/UUID
-> station advisory lock
-> station queue rows ordered by station_queue_pk
```

Exact route/item/config reads occur between release and lifecycle reads but are
not locked because versioned config is treated as immutable. Every release
writer follows the same hierarchy; no primitive commits or opens a connection.

## Queue-Rank Serialization

The selected no-schema mechanism is a PostgreSQL transaction advisory lock on
the 64-bit `hashtextextended` value of the namespaced station code. Same-station
release writers serialize; different stations remain parallel except for a
vanishingly rare hash collision, which only over-serializes.

After the lock, rank allocation uses:

```sql
SELECT COALESCE(MAX(queue_rank) + 1, 0)
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND status IN ('queued', 'active', 'pending_approval')
```

This predicate exactly matches the current partial unique index. `ready` is
not added without a separately reviewed schema change.

The existing partial unique index remains the final safety boundary. A race
with a non-cooperating legacy writer rolls back and becomes
`WORK_ORDER_RELEASE_QUEUE_CONFLICT`; there is no automatic rank retry and no
persisted timestamp/rank from the failed attempt.

## Same-Request Concurrency

The first request locks the work order, persists all artifacts, and commits.
The second blocks on the same work-order row, then reads the committed immutable
release and returns `released=False`. It does not insert, update, re-rank, or
replace UUIDs.

If an identity unique violation is reached through a cross-work-order race,
classification occurs only after complete rollback in a new DB context.

## Conflicting-Request Concurrency

- Different route/version on one work order is serialized by the work-order
  lock; the loser reads the committed release and raises route/version conflict.
- Different release IDs on one work order raise already-released conflict.
- One release ID on different work orders is arbitrated by release-ID unique
  enforcement; post-rollback readback raises release-ID conflict.
- Same-station different-work-order releases serialize only rank allocation;
  both transactions may otherwise proceed concurrently.

## Unique-Violation Classification

`23505` handling is an outer public-writer concern:

1. Exit the failing transaction and confirm rollback.
2. Close that connection/cursor context.
3. Open a new `database_connection`.
4. Open a new transaction and cursor.
5. Read release by order ID and release ID plus the authoritative snapshot.
6. Classify immutable replay or the deterministic persisted-state conflict.

The aborted cursor is never reused. A constraint name may select which
readback to prioritize, but it is not sufficient evidence for the result.
Unknown `23505`, `40P01`, `40001`, FK, connectivity, and other unclassified DB
errors propagate unless an authoritative domain state is proven.

## Authoritative Readback

Readback captures:

- both release identities and all 14 release fields;
- every lifecycle persisted field for the work order;
- every binding row reached through lifecycle UUID/work-order ownership;
- the initial queue identity and current operational fields;
- current work-order state.

Readback returns replay only after exact immutable equality. It never repairs
partial state, merges metadata, restores statuses, or allocates a rank.

## Exact Replay Equality

Immutable equality:

- release ID/order/route/mode/source/actor/caller metadata/count/digest;
- deterministic lifecycle UUID set;
- static lifecycle order/config snapshot, planned quantity, UOM, payload, and
  server metadata;
- deterministic complete binding IDs and lifecycle/config pairs;
- one unambiguous initial queue identity: lifecycle UUID, order, station,
  source, payload, and metadata.

Mutable operational state excluded from conflict equality:

- work-order status and start/completion/update timestamps;
- lifecycle status, good/scrap quantities, start/completion/update timestamps;
- queue status, rank, and update timestamp.

Thus the same immutable request remains idempotent after start, completion,
successor activation, or queue progression. Replay returns current state with
`released=False` and performs zero writes.

## Partial-State Detection

- Release missing but lifecycle/binding/queue artifacts exist: first-release
  conflict; no adoption.
- Release exists with missing/extra lifecycle operations: operation-count
  mismatch.
- Static lifecycle identity/snapshot differs: operation-snapshot mismatch.
- Binding set is missing/orphan/partial: partial-binding conflict.
- Complete binding pairs/digest differ: mapping conflict.
- Initial queue identity missing, duplicated, or points to a different
  order/operation/station/source: queue conflict.
- Queue status/rank progression alone is not partial-state corruption.

## Failure Injection

Unit tests configure fake cursor/connection failures, not a public production
flag, at:

1. after work-order lock;
2. after route validation;
3. after release insert;
4. after first lifecycle insert;
5. after all lifecycle inserts;
6. after first binding insert;
7. after all binding inserts;
8. after queue insert;
9. after work-order status update;
10. before snapshot read;
11. before commit.

Real-DB smoke uses test-process monkeypatch/proxy wrappers around private
primitives, cursor execution, or transaction exit. No test-only branch or
public injection argument is added to production code.

Every injected failure must prove release/operation/binding/queue deltas `0`,
unchanged work-order status/timestamps, and a clean subsequent
`released=True` retry.

## Retry Semantics

- Application-level automatic retry is not used for queue-rank conflict,
  deadlock, serialization failure, or unknown DB error.
- An exact caller retry after a fully rolled-back attempt recomputes the same
  UUIDs, binding IDs, static snapshots, and digest.
- A caller retry after a non-cooperating queue writer may obtain a later rank;
  the failed attempt persisted neither rank nor timestamp.
- A retry after a committed exact release returns `released=False`, even when
  operational lifecycle/queue state has progressed.

## Deadlock Considerations

- Work-order locking serializes same-order writers before release/child locks.
- Matching release rows are locked in PK order, never request-dependent order.
- Child rows and queue rows use stable UUID/PK ordering.
- Only one station advisory lock is acquired per release.
- Same-station writers never hold a second station lock.
- Phase 5D does not coordinate foreign MESQL/runtime ownership; incompatible
  concurrent mutations must surface through constraints/final invariants and
  are not silently adopted.

## Isolation Level

`READ COMMITTED` is selected with explicit row/advisory locks and database
unique/FK constraints. `SERIALIZABLE` is not required for the supported writer
concurrency matrix and would introduce unrelated retry semantics. Any observed
`40001` or `40P01` propagates after rollback.

## Acceptance Criteria

- All supported concurrency scenarios produce the table above.
- Shared-cursor primitives create no nested transaction or commit.
- Queue predicate exactly matches the existing partial unique index.
- `23505` readback always uses a completely new DB context.
- Immutable replay remains idempotent after operational progression.
- Partial immutable artifacts never replay and are never repaired.
- All failure injections roll back fully and deterministic retry succeeds.
- No schema/config/runtime/API/FERP/MESQL mutation is introduced by Phase 5D-A.

## Phase 5D-A Replay Decision Amendment

The immutable/mutable split in this plan supersedes the earlier strict replay
wording in `work_order_release_helper_contract.md`. That earlier text remains
historical Phase 5B design context; Phase 5D-B/C implementation and tests must
follow this amendment.
