# Runtime-to-Lifecycle Completion Bridge Isolated Smoke Plan

## Status

`READY_FOR_PHASE_5G_C_EXECUTION_AFTER_IMPLEMENTATION`

Last updated: `2026-07-15`.

This plan is not executed in Phase 5F. It becomes executable only after Phase
5G-A private primitives and Phase 5G-B atomic runtime integration are committed,
reviewed, and regression-clean.

## Safety Boundary

- Source database `mes` is backup/baseline/final-integrity read-only.
- All migrations, seed, fixtures, runtime events, bridge writes, concurrency,
  and failure injections run only in an exact disposable clone.
- Create an empty database from `template0`, then restore a verified logical
  source dump. Never use `TEMPLATE mes`.
- Every mutation asserts exact clone identity and rejects database `mes`.
- Do not rebuild/recreate/restart/down Docker or touch images/volumes.
- Preserve the host logical backup after clone cleanup.
- Do not add a production failure flag or call API/Kiosk/IoT/FERP/MESQL paths.

## Source Backup and Baseline

1. Require clean reviewed Phase 5G commits and no unrelated workspace change.
2. Verify exact container/database/user identity and PostgreSQL health.
3. Capture a unique timestamp and create
   `mes_before_runtime_lifecycle_bridge_smoke_<timestamp>.sql` in the approved
   host backup directory.
4. Verify nonzero size and plain PostgreSQL dump header without printing the
   password.
5. In one repeatable-read, read-only source transaction record established
   15-table counts and ordered `to_jsonb(t)::text` digests.
6. Record extended counts/digests for release/binding presence, runtime state,
   steps, operation events, approvals, production flow, production
   completions, work-order events, integration outbox, and any inventory
   movement/balance tables.
7. Record retained V1 lifecycle/runtime/config identity and assert no smoke ID
   exists in source.

## Disposable Clone Preparation

1. Use a unique exact name such as
   `mes_runtime_lifecycle_bridge_smoke_<timestamp>`.
2. Require matching database count `0`, create from `template0`, restore the
   logical dump, and prove current database is the clone and not `mes`.
3. Require restore equality for all established counts/digests and extended
   state before any mutation.
4. Apply only to the clone, in dependency order:
   - `009_work_order_operation_route_binding.sql`;
   - `010_work_order_route_release.sql`;
   - `006_station_execution_seed_canonical_v2.sql`.
5. Verify binding/release shapes, exact V2 route version `2`, OP10/OP20
   operations, OP10 three steps, OP20 one step, and both policies
   `auto_close_on_required_steps`.

## Marker and Legacy Gating

Before the end-to-end bridge case, verify the normative applicability boundary:

- retained V1/legacy lifecycle without exact
  `metadata.source=work_order_release` plus nonblank `release_id` completes its
  existing runtime response with `completion_bridge=None`;
- instrument SQL and prove no release/binding sidecar query occurred;
- a marker-bearing lifecycle with either sidecar table deliberately hidden in
  a disposable negative clone/transaction returns
  `503 RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY`;
- an unmasked/unclassified `UndefinedTable` is never converted to legacy
  success;
- marker plus missing release or binding returns its deterministic conflict
  with zero runtime/event/lifecycle/queue delta.

## Route-Generated Release Fixture

1. Insert one clone-only clean planned work order for `PACKAGED_PRODUCT` with a
   positive quantity and immutable smoke payload/metadata.
2. Call the public route-release writer for exact
   `ROUTE_BOX_PACKAGING_V2`, version `2`, `route_generated`, and
   `local_planning`.
3. Require one release, deterministic OP10/OP20 UUIDs, two complete immutable
   bindings, only the OP10 initial queue, and queued work-order state.
4. Capture immutable digests and every mutable timestamp/rank before runtime.

## OP10 Runtime and Bridge

1. Initialize OP10 through its exact binding and station `ASSEMBLY_01`.
2. Require `ready`, no current step, and three pending ordered execution steps.
3. Execute the real configured OP10 steps in order with unique event identity:
   - `COLOR_SENSOR_ENTRY_EVIDENCE` auto/implicit finish path;
   - `ROBOT_ARM_DROP_COMPLETED` auto/implicit finish path;
   - `PROCESS_END_OBSERVATION` manual start then manual finish.
4. The last required finish must persist runtime `closed` and invoke the bridge
   in the same transaction.
5. Require `completion_bridge.bridged=True` and exact response/readback
   agreement:
   - runtime `closed_at` equals triggering finish `event_time`;
   - OP10 lifecycle status `completed` and `completed_at` equals `closed_at`;
   - OP10 good/scrap, payload, metadata, and started_at unchanged by bridge;
   - OP10 queue retained with original rank/source/payload/metadata and status
     `completed`;
   - OP20 lifecycle `planned -> queued`;
   - one OP20 queue at `PACKAGING_01`, source
     `runtime_completion_bridge`, exact immutable payload/metadata, and no
     route/config ID in queue state;
   - work order not completed.

## Duplicate and Concurrent Replay

- Replay the exact final OP10 finish event. Require no early-return omission:
  response contains `completion_bridge.bridged=False` and the current
  authoritative snapshot.
- Compare all event/runtime/lifecycle/queue/work-order counts and digests around
  replay; require zero writes and original timestamps/ranks.
- Run two concurrent identical final-step finishes on a fresh released work
  order. Require one true bridge and one false replay, one finish event, one
  successor queue, and no partial state.
- After OP20 later progresses/completes, replay the old OP10 finish and require
  `bridged=False`; successor operational progression must not become conflict.

## Same-Station Queue Concurrency

1. Prepare two independent released work orders whose current operations close
   into the same successor station.
2. Synchronize them before the station advisory-lock boundary.
3. Require both bridges succeed with distinct active ranks and no deadlock.
4. Instrument advisory calls and prove each transaction uses the unique,
   lexical-sorted exact current/successor station set and locks each station
   once. A same-current/successor-station negative fixture must show one lock
   call and then the current schema's deterministic station/order queue
   conflict rather than legacy upsert.
5. Insert a high-rank `ready` control row and prove it does not affect the next
   active rank.

## Queue-Rank Conflict

1. At successor queue insertion, use a test-process non-cooperating transaction
   to occupy the selected active rank.
2. Require known queue `23505` maps to
   `RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT` only after full rollback.
3. Require triggering finish event, runtime step/state, current lifecycle/
   queue, successor lifecycle/queue, and work order all equal their pre-call
   baseline.
4. Require no automatic rank retry. After removing the blocker, an explicit
   exact caller retry must succeed cleanly.
5. Unknown `23505`, `23503`, `40P01`, `40001`, and generic DB errors must
   propagate unchanged after rollback.

## Rollback Failure Injection

Use only test-process monkeypatch/cursor/transaction-proxy seams at:

1. after finish-event insert;
2. after runtime-step completion;
3. after runtime closed transition;
4. after current lifecycle completion;
5. after current queue terminalization;
6. after successor resolution;
7. after successor lifecycle update;
8. after all unique lexical station advisory locks;
9. after successor queue insert;
10. after final work-order completion;
11. before authoritative snapshot;
12. before transaction exit.

For each point require zero delta across operation events, runtime steps/state,
lifecycle, binding, queue, work order, approval, production flow, production
completion, work-order events, outbox, and inventory. Require exact work-order
payload/metadata/timestamps unchanged and a clean successful retry.

## OP20 and Final Work-Order Completion

1. Initialize OP20 only through its immutable successor binding and exact
   queued lifecycle/queue identity.
2. Execute `PACKAGING_EXECUTION` manual start and finish with a unique event.
3. Require runtime closes and final bridge returns `bridged=True`.
4. Require OP20 lifecycle/current queue completed at the exact runtime
   `closed_at` and no successor lifecycle/queue.
5. Require every lifecycle operation completed, then work order status
   `completed` and `completed_at` equal OP20 `closed_at`.
6. Require work-order payload/metadata, release, bindings, lifecycle quantities,
   and queue ranks unchanged except for contracted mutable statuses/timestamps.
7. Duplicate the final finish and require `bridged=False`, zero writes, and
   original final timestamp.
8. In a negative fixture leave another lifecycle operation incomplete; require
   final work-order conflict and rollback of the triggering finish.

## No-Extra-Audit Boundary

Across each successful bridge, require only the triggering step-finish event
expected from the existing runtime helper. Bridge deltas must be zero for:

- additional `operation_events` including `system_transition`;
- `operation_approvals`;
- `production_flow_events`;
- `production_completions`;
- `work_order_events`;
- `integration_outbox`;
- inventory movement, balance, or stock tables.

Retained V1 config, lifecycle, runtime, queue, events, and digests must remain
unchanged throughout clone testing.

## Readback and Repeated-Read Checks

- Compare the nested bridge response with direct cursor-scoped authoritative
  reads for execution, lifecycle, current queue, successor, and work order.
- Verify every response path contains `completion_bridge`; value is `None` for
  nonclosed/legacy/not-applicable paths.
- Around conflict/replay/read calls, prove no write through count/digest and
  timestamp/rank comparisons.
- Verify no latest route, station/code inference, legacy queue adoption,
  binding backfill, or repair SQL appears in the observed bridge transaction.

## Cleanup and Source Final Integrity

1. Terminate sessions only for the exact disposable clone.
2. Drop only the exact clone and require matching clone count `0`.
3. Remove only the exact container temporary dump copy; retain host backup.
4. Re-run source established 15-table counts/digests and extended audit/
   inventory baselines in a new repeatable-read, read-only transaction.
5. Require source equality `15/15` counts, `15/15` digests, unchanged retained
   V1, and zero clone-only IDs.
6. Require PostgreSQL/container health and `GET /health` HTTP `200`,
   `status=ok` without Docker lifecycle action.

## PASS Criteria

- Marker gating precedes and suppresses all sidecar access for retained legacy.
- Runtime close and bridge are one atomic transaction.
- OP10 completion terminalizes its queue and activates exact OP20 once.
- Duplicate/concurrent finish yields one true bridge then false replay(s).
- Unique lexical station locks and exact three-status rank allocation pass.
- OP20 final close completes the work order once with authoritative timestamp.
- Every conflict/failure leaves zero partial write and clean retry succeeds.
- Bridge adds no extra audit/approval/flow/completion/outbox/inventory effect.
- Retained V1 and source database remain unchanged.
- Clone cleanup, backup retention, and health all pass.

Any missing atomicity, marker ordering, exact identity, lock-order, rollback,
source-integrity, cleanup, or health evidence makes Phase 5G-C `FAIL` or
`BLOCKED`, never `PASS`.
