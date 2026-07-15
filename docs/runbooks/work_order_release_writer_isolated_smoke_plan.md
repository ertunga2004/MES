# Work-Order Release Writer Isolated Smoke Plan

## Status

`PLANNED_NOT_EXECUTED`

Last updated: `2026-07-15`.

This Phase 5E plan may run only after Phase 5D-B private primitives and Phase
5D-C public writer are committed and reviewed. Phase 5D-A does not execute it.

## Safety Boundary

- Source: container `mes_postgres`, database/user `mes`, host port `5433`.
- Source is backup/baseline/final-integrity read-only.
- Create an empty `template0` database, then restore the logical source dump.
- Apply migrations `009`, `010`, and Canonical V2 seed only to the exact clone.
- Guard every clone mutation with exact database name and `database != mes`.
- Use clone-only IDs, actors, UUIDs, timestamps, and metadata.
- Do not rebuild/recreate/restart Docker or touch volumes.

## Source Backup and Baseline

1. Verify clean implementation commit and regression baseline.
2. Create retained plain logical backup
   `mes_before_work_order_release_writer_smoke_<timestamp>.sql`.
3. Verify nonzero size, dump header, and no password output.
4. Capture established 15-table count/digest baseline in one read-only
   repeatable-read transaction.
5. Capture release/binding relation state, parent route constraint, Canonical
   V2 count, retained V1 state, and `4/0/0` audit counts.

## Disposable Clone

1. Create `mes_work_order_release_writer_smoke_<timestamp>` from `template0`.
2. Restore logical dump with `ON_ERROR_STOP=1`.
3. Require `15/15` count equality, `15/15` digest equality, and extended-state
   equality before mutation.
4. Apply clone-only migration `009`, migration `010`, and V2 seed with exact
   guards.
5. Verify binding `9/9/4`, release `14/15/5`, V2 `1/2/4`, OP10/OP20 `3/1`,
   and roles `5/5`.

## Candidate Work Orders

Create clean clone-only work orders with positive target quantity, matching
`PACKAGED_PRODUCT`, null start/completion timestamps, and `planned` or clean
`queued` status for:

- first release and exact replay;
- same-request concurrency;
- same-order different-route/version conflict;
- release-ID reuse on another work order;
- two same-station concurrent releases;
- every injected rollback case.

No candidate may have a pre-existing release, lifecycle operation, binding,
queue, runtime state, event, approval, or production-flow row unless the case
explicitly creates controlled partial/conflicting state.

## First Route-Generated Release

Call the public writer with exact V2/version `2`, `route_generated`,
`local_planning`, fixed actor, and object metadata.

Require:

- `released=True`;
- one exact immutable release with fixed count/digest;
- deterministic OP10/OP20 UUIDs and static lifecycle snapshots;
- OP10 inserted `queued`, OP20 inserted `planned`;
- positive target copied to planned quantity and route-item unit copied to UOM;
- complete deterministic binding set with source `work_order_release`;
- exactly one OP10 queue row with source `work_order_release`;
- work order `queued`, payload/metadata unchanged;
- no execution state, step, event, approval, flow, or inventory action.

## Exact Replay and Operational Progression

Immediately replay the exact request and require `released=False`, identical
immutable rows/UUIDs/PKs/timestamps, identical queue rank, and zero writes.

Then, in one guarded clone-only SQL fixture transaction, advance mutable
operational columns without changing immutable release artifacts:

- update work-order/operation statuses;
- update good/scrap and start/completion timestamps;
- progress initial queue status/rank.

This is a disposable classification fixture, not a production transition
helper or completion bridge. It creates no runtime state, step execution,
event, approval, production-flow, successor queue, or inventory movement.

Replay again and require:

- `released=False`;
- immutable release, static operation snapshots, and bindings unchanged;
- current operational values returned without rewind;
- zero replay writes or timestamp updates.

This case proves the Phase 5D-A amendment superseding strict Phase 5B replay.

## Concurrency Cases

Use independent host connections and a synchronization barrier:

- Same work order/exact request: one `released=True`, one `released=False`.
- Same work order/different route or version: one commit, one deterministic
  route/already-released `409`.
- Same release ID/different work orders: one commit, one
  `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT` after new-context readback.
- Two work orders/same OP10 station: both commit with distinct active queue
  ranks.
- Two different initial stations: no shared station-lock blocking beyond normal
  database scheduling.

Capture connection IDs, start/end times, result codes, release rows, queue
ranks, and table digests without logging credentials.

## Queue-Rank Contract

Before and after same-station concurrency, verify rank allocation considers
exactly:

```text
queued, active, pending_approval
```

Create a controlled `ready` row and prove it is not part of the normative
active-rank `MAX+1` predicate because the current partial unique index excludes
it. Do not alter schema.

Verify one queue row per station/order and station/operation, no duplicate
active rank, OP20 absent from queue, and replay does not re-rank.

## Conflict and Partial-State Cases

Prove deterministic, zero-write handling for:

- inactive/missing route or route operation;
- nonmatching product, invalid target, terminal/started work order;
- another release on the work order;
- release ID owned by another work order;
- route/version/mode/source/actor/caller-metadata mismatch;
- missing/extra/static-mismatched lifecycle operations;
- orphan, partial, extra, or different bindings;
- missing/duplicate/wrong immutable initial queue identity;
- caller mappings in disabled generated-mode boundary.

Mutable lifecycle/work-order status, quantities, operational timestamps, and
queue status/rank progression alone must not produce replay conflict.

## Unique-Violation Readback

Instrument the writer connection lifecycle and prove that a `23505` path:

1. exits and rolls back the first transaction;
2. closes the first cursor/connection context;
3. opens a new connection, transaction, and cursor;
4. classifies authoritative immutable replay or conflict;
5. never queries through the aborted cursor.

An unclassified injected `23505` and non-unique DB error must propagate.

## Failure Injection and Rollback

Using test-process monkeypatch/proxy wrappers, inject after:

- work-order lock;
- route validation;
- release insert;
- first/all lifecycle inserts;
- first/all binding inserts;
- queue insert;
- work-order status update;
- before snapshot read;
- before commit.

After every failure require:

- release/lifecycle/binding/queue deltas `0`;
- unchanged work-order status, payload, metadata, and timestamps;
- config/master/runtime/event/approval/flow/inventory digests unchanged;
- exact retry succeeds as a clean `released=True` first release.

No production public failure-injection parameter is permitted.

## Read-Model and Runtime Compatibility

- Read the committed release through all five Phase 5C helpers.
- Require release row, exact route, ordered operations, lifecycle-scoped
  bindings, and OP10 initial queue agreement with writer response.
- Initialize OP10 runtime using its deterministic binding and verify compatible
  route identity.
- Do not execute a step, close runtime, complete lifecycle, or queue OP20.

## Repeated-Read and No-Write Checks

Around replay, conflict, concurrency readback, and read-model calls, compare
counts/digests for release, work order, lifecycle, binding, queue, runtime,
event, approval, flow, config/master, and location tables. Only the intended
first-release/concurrency commits may change rows.

## Cleanup and Source Final Integrity

1. Terminate exact clone sessions.
2. Drop exact clone and require matching database count `0`.
3. Retain logical backup.
4. Re-run source 15-table count/digest and extended-state baseline in a new
   read-only transaction.
5. Require `15/15` counts, `15/15` digests, unchanged extended/V1 state, and no
   clone-only IDs in source.
6. Require health HTTP `200`, `status=ok`.

## PASS Criteria

- First release is atomic and deterministic.
- Immutable replay is read-only before and after operational progression.
- Complete bindings and only OP10 initial queue are present.
- Same-station concurrency produces unique ranks with exact three-status
  allocation predicate.
- Every deterministic conflict and failure injection leaves no partial write.
- `23505` readback uses a new DB context after full rollback.
- Runtime initialization remains compatible without step execution.
- Source integrity, clone cleanup, backup retention, and health all pass.

Any identity, atomicity, immutable replay, concurrency, rollback, source, or
cleanup failure makes the smoke `FAIL` and blocks Phase 5F.
