# Work-Order Release and Route-Binding Isolated Smoke Plan

## Status

`PLANNED_NOT_EXECUTED`

Last updated: `2026-07-15`.

This runbook is a future disposable PostgreSQL smoke plan. Phase 5A does not
run Docker, PostgreSQL, `psql`, `pg_dump`, a migration, a seed, or a helper.

## Objective

Prove that the accepted work-order release transaction creates one immutable
route release, the complete lifecycle operation/binding set, and one initial
queue row; exact replay is read-only; conflicts and injected failure leave no
partial artifacts; source `mes` remains unchanged.

## Safety Boundary

- Obtain explicit approval before executing the future smoke.
- Never use source `mes` as a template or smoke target.
- Create a logical source backup and restore it into a uniquely named
  disposable clone.
- Apply future release migration and Canonical V2 seed only to the exact clone.
- Use clone-only candidate IDs, actors, release IDs, UUIDs, and audit metadata.
- Do not call FERP, MESQL, Kiosk, IoT/MQTT, Observer, OEE, approval,
  production-flow, or inventory integrations.
- Do not alter retained V1 runtime/history.
- Preserve the host backup after clone cleanup.
- Abort if any connection identity does not prove the intended database.

## Required Artifacts

- Approved decision and implementation plan.
- Reviewed work-order release migration and exact-shape assertions.
- Reviewed release read/validation and atomic write helpers.
- Passing targeted and combined unit tests.
- Existing migrations required by source shape, including station execution,
  station queue, MESQL lifecycle operations, and operation route binding.
- `db/migrations/006_station_execution_seed_canonical_v2.sql`.
- A unique run timestamp and evidence file path.

## Source Backup

Before clone creation:

1. Verify Docker/PostgreSQL health and the exact source database identity.
2. Create a fresh logical PostgreSQL dump at a timestamped host path outside
   transfer/build/cache folders.
3. Verify nonzero size and PostgreSQL dump header.
4. Record the exact backup path, byte size, timestamp, and source identity.
5. Read credentials only from the existing secure local environment; never
   print or embed them in evidence.

The source backup is retained. The clone is restored from this dump, not
created with `CREATE DATABASE ... TEMPLATE mes`.

## Source 15-Table Baseline

In one read-only source transaction, record deterministic row counts and
ordered `to_jsonb(t)::text` digests for the same established 15-table scope:

1. `mes.items`
2. `mes.process_routes`
3. `mes.route_operations`
4. `mes.operation_steps`
5. `mes.station_event_sources`
6. `mes.work_order_operation_execution_state`
7. `mes.work_order_operation_steps`
8. `mes.operation_events`
9. `mes.operation_approvals`
10. `mes.production_flow_events`
11. `mes.work_orders`
12. `mes.work_order_operations`
13. `mes.station_queue`
14. `mes.locations`
15. `mes.station_location_bindings`

Also record whether the binding and future work-order release sidecars exist,
their exact row counts/digests when present, source Canonical V2 route count,
and retained V1 state/event/approval/production-flow snapshot. Baseline queries
must perform no writes.

## Disposable Clone Restore

1. Generate a unique database name such as
   `mes_work_order_release_smoke_<timestamp>`.
2. Create an empty clone database.
3. Restore the verified logical dump into that exact clone.
4. Reconnect and assert `current_database()` equals the generated name.
5. Compare all 15 clone counts/digests with source before any clone migration.
6. Abort and drop the clone if any table differs.

## Required Migrations and V2 Seed

On the verified clone only:

1. Apply any missing prerequisite migrations in repository order.
2. Apply `009_work_order_operation_route_binding.sql` if absent and verify its
   established exact `9 / 9 / 4` column/constraint/index shape.
3. Apply the future reviewed work-order release migration.
4. Reapply the release migration and prove idempotency: same table OID, exact
   shape, zero row creation, and unchanged existing-table digests.
5. Apply Canonical V2 seed and reapply it for idempotency.
6. Verify Canonical V2 scope `1 / 2 / 4`, OP10/OP20 steps `3 / 1`, configured
   and resolved roles `5 / 5`, and V1 coexistence.
7. Record config/master digests after setup as the no-write baseline for all
   helper calls.

No migration or seed is applied to source `mes`.

## Clone-Only Candidate Work Orders

Use distinct candidate work orders so one negative scenario cannot invalidate
another. All IDs include the run timestamp.

Route-generated candidate:

- `order_id = WO-RELEASE-V2-GENERATED-<timestamp>`;
- product/item `PACKAGED_PRODUCT`;
- status `queued` with no release, lifecycle operation, binding, queue,
  runtime, event, approval, or production-flow row;
- explicit route `ROUTE_BOX_PACKAGING_V2`, version `2`;
- stable `release_id = RELEASE-V2-GENERATED-<timestamp>`;
- mode/source/actor
  `route_generated / local_planning / SMOKE_RELEASE_ACTOR`.

Explicit-mapping candidate:

- a separate clean work order with product `PACKAGED_PRODUCT` and status
  `queued`;
- exactly two clone-only lifecycle rows with stable UUIDs and snapshots matching
  V2 OP10/OP20;
- no release, binding, queue, runtime, or audit side effect;
- a complete explicit map from those UUIDs to the two exact V2 route-operation
  IDs.

Negative candidates:

- a different-route replay candidate;
- an orphan/partial-binding candidate;
- missing/duplicate/extra/wrong-parent/snapshot-mismatch mapping candidates;
- an injected-failure candidate.

Record candidate-level baseline counts/digests before each scenario.

## Route-Generated First Release

Call the core helper directly, not through an API, with the exact generated
request.

Expected:

- `released=true`;
- one immutable release record with route ID/code/version `V2` and stored mode;
- exactly two lifecycle operations with server-controlled deterministic UUIDv5
  values;
- OP10/OP20 lifecycle snapshots match station/code/sequence from the selected
  route;
- OP10 is `queued`, OP20 is `planned`;
- exactly two `work_order_release` binding rows cover the selected route once;
- binding IDs are server-controlled, deterministic, and stable on replay;
- one initial queue row references OP10 lifecycle UUID;
- work order remains/enters release-equivalent `queued`;
- count/digest and release audit fields match the returned snapshot;
- no runtime, operation event, approval, production-flow, inventory, FERP, or
  MESQL side effect.

Capture returned UUIDs, PKs, timestamps, row payloads, metadata, count/digest,
queue rank, and all candidate table digests.

## Exact Replay

Repeat the byte/canonical-equivalent exact request.

Expected:

- `released=false`;
- same release/lifecycle/binding/queue PKs and UUIDs;
- same timestamps, actor, source, metadata, route count/digest, statuses, and
  queue rank;
- no new UUID generation visible as a persisted row;
- zero count/digest change in every candidate-related table;
- no work-order update timestamp change;
- no event/audit row beyond the immutable release/binding records created by
  the first call.

This proves replay and no duplicate queue.

## Different-Route and Release-ID Conflicts

Against the already released generated candidate, attempt separately:

- same release/work order with V1 or another route version;
- same work order with a new release ID;
- same release ID with a different work order;
- same immutable request with a different mode.

Expected: deterministic `409` domain errors. Counts, digests, timestamps,
status, operation pairs, bindings, and queue remain exactly equal to the
post-first-release snapshot.

## Explicit Operation Mapping Validation

Call the helper for the clean explicit-mapping candidate with the complete
exact pair set.

Expected first call/replay:

- `released=true / false`;
- lifecycle operation count stays exactly two; no lifecycle UUID is replaced;
- two bindings exactly match the supplied UUID/config pairs;
- one OP10 initial queue row and no OP20 queue row;
- complete count/digest and stable audit snapshot.

On separate clean negative candidates, verify deterministic failure for:

- lifecycle operation from a different work order;
- route operation from a different route/version;
- missing OP20 mapping;
- duplicate lifecycle UUID;
- duplicate route-operation ID;
- extra lifecycle operation or extra mapping;
- station mismatch;
- operation-code mismatch;
- sequence mismatch;
- terminal/active/already-executed lifecycle operation.

All failures must leave release/operation/binding/queue/status counts and
digests unchanged. Snapshot fields are validation only; no scenario may infer
identity from them.

## Partial Binding Conflict

For the partial-binding candidate:

1. Create the clean candidate lifecycle operation set explicitly in the clone.
2. Create exactly one clone-only binding using the reviewed controlled binding
   helper, with no work-order release record.
3. Record its exact count/digest/timestamps.
4. Attempt a generated and, separately if applicable, explicit release that
   would need the complete set.

Expected:

- `409 WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT`;
- no release record;
- no second binding;
- no queue/status/runtime/audit mutation;
- the pre-existing clone-only binding remains byte-identical.

Do not complete the partial set automatically.

## Initial Queue and Successor Boundary

For successful candidates, verify:

- only the smallest V2 sequence (OP10) has a queue row;
- queue identity is OP10 `work_order_operation_id`;
- config identity is available only through OP10's binding;
- station, source, queued status, and rank are correct;
- station/operation, station/order, and active-rank uniqueness hold;
- replay adds no row and performs no re-rank/update;
- OP20 remains planned and unqueued;
- release does not call lifecycle completion or successor activation.

The future Phase 5G smoke, not this run, will prove OP10 runtime close to
lifecycle completion and OP20 activation.

## Binding Completeness and Immutability

For each successful release:

- release route-operation count equals route config count;
- lifecycle operation count equals route config count;
- binding count equals route config count;
- distinct lifecycle and route-operation IDs both equal that count;
- every binding joins to the same work order and selected route version;
- no missing or extra pair exists;
- stored canonical digest equals a freshly computed digest;
- OP10 and OP20 are proven members of the same V2 release.

Attempt controlled conflicting rebinds and any unsupported update/delete path.
Expected: conflict or denied operation, with binding counts/digests and
timestamps unchanged. Do not mutate rows directly merely to demonstrate a
failure unless the approved smoke harness wraps the attempt in a guaranteed
rollback.

## Injected Failure Rollback

Use the dedicated failure candidate and a test-only injection point after the
last binding insert but before initial queue completion; repeat at least once
after queue insert but before final invariant validation/commit.

Expected after each raised failure and transaction rollback:

- release count delta `0`;
- lifecycle operation count delta `0`;
- binding count delta `0`;
- queue count delta `0`;
- work-order status/timestamps unchanged;
- runtime/event/approval/production-flow/inventory deltas `0`;
- config/master digests unchanged;
- connection remains usable and a subsequent normal call succeeds with the
  deterministic UUID set that the failed attempt would have used.

No cleanup delete is accepted as proof of atomicity; inspect immediately after
rollback.

## Lifecycle Operation Counts

Record before/after/replay/conflict/rollback counts and deterministic digests
for each candidate. Required generated success delta is exactly `+2`; replay
and all conflict paths are `0`; injected failure is `0` after rollback.

For explicit mapping, lifecycle operation delta is exactly `0` because the two
rows pre-exist. No existing source-restored lifecycle row changes.

## Config No-Write and Audit Scope

After every success, replay, conflict, and rollback scenario, compare the
post-seed count/digest snapshots of:

- items, process routes, route operations, operation steps;
- stations, event sources, locations, and station-location bindings;
- Canonical V2 and retained V1 config scopes.

All must remain equal.

Permitted successful first-call audit is limited to immutable release and
binding actor/source/timestamp/metadata fields. Unless the approved helper
contract explicitly adds a release event in a later design, operation events,
approvals, production-flow events, integration inbox/outbox, runtime steps,
and runtime execution state must have zero delta. Replay/conflict/rollback add
no audit row.

## Source Final Integrity

After all clone work, open a new read-only source transaction and repeat the
same 15 table counts/digests and sidecar/config/V1 observations.

Required:

- source count equality `15/15`;
- source digest equality `15/15`;
- source Canonical V2 route count unchanged;
- source binding/release sidecar presence and row counts unchanged;
- retained V1 state/current step/final step/events/approvals/production-flow
  unchanged;
- no candidate release/work-order/operation/queue identifier exists in source.

Any source difference makes the smoke `FAIL` and blocks cleanup conclusions
until investigated.

## Clone Cleanup and Health

1. Record final clone evidence and exact clone database name.
2. Terminate only sessions connected to that verified disposable clone.
3. Drop only that clone.
4. Query database catalog and prove remaining exact/prefix match count is `0`.
5. Verify PostgreSQL/Docker health after cleanup.
6. Verify source `mes` remains connectable and read-only integrity checks pass.
7. Preserve the logical backup and report its path.
8. Do not leave background smoke processes or extra clone databases.

## PASS Criteria

The run is `PASS` only if:

- backup, 15-table baseline, clone restore, migrations, and V2 seed pass;
- generated and explicit first calls create the exact selected artifacts;
- exact replay is fully read-only and UUID-stable;
- different-route/release/mapping/partial conflicts are deterministic and
  mutation-free;
- only the initial operation is queued and no duplicate queue exists;
- bindings are complete, same-version, and immutable;
- injected failure proves rollback without cleanup deletes;
- lifecycle operation deltas match mode-specific expectations;
- config/master and retained V1 are unchanged;
- audit scope contains no forbidden side effects;
- source final integrity is `15/15` counts and digests;
- clone cleanup leaves zero matching databases;
- final database/container health passes.

If any identity, atomicity, replay, conflict, source-integrity, cleanup, or
health assertion is unproven, report `FAIL` or `BLOCKED`, never `PASS`.
