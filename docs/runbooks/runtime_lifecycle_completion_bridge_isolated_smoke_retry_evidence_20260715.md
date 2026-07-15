# Runtime-to-Lifecycle Completion Bridge Isolated Smoke Retry Evidence

## Result

`PASS`

Date: `2026-07-15`

This retry supersedes the failed acceptance result recorded in
`runtime_lifecycle_completion_bridge_isolated_smoke_evidence_20260715.md`.
The original evidence remains committed and unchanged as the historical record
of the stale mutable preflight replay blocker.

## Hotfix Closure

- Historical FAIL evidence commit:
  `c319c9081fba5d0fe66f63cf3cb9eebfefa3c9fe`.
- Phase 5G-BR1 hotfix commit:
  `2c62ad9ea3473886a51a0d1fa61bb25c10c0667f`.
- Commit subject:
  `fix: allow completion bridge replay after concurrent progress`.
- The commit contains only `mes_web/db/mesql_v2.py` and
  `tests/test_mes_web_mesql_v2.py`.
- Focused review found no actionable P1 or P2 issue.
- Targeted regression: `600`, `OK`.
- Combined regression: `636`, `OK`.
- Python compile and `git diff --check`: PASS.
- No push was performed.

The hotfix limits post-lock preflight revalidation to exact immutable lifecycle
UUID, work-order ID, operation code, sequence, station, marker source, and
marker release ID. Mutable lifecycle `status` and `completed_at` progression is
classified from authoritative locked rows. Full release count/digest, complete
binding set, static lifecycle identity, runtime identity, queue identity, and
partial-state conflict validation remain in place.

## Source Safety, Backup, and Baseline

- Source identity: container `mes_postgres`, database/user `mes/mes`,
  PostgreSQL `16.14`, host port `5433`.
- Source was used only for logical backup, repeatable-read/read-only baseline,
  final integrity, and health.
- Retained backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_runtime_lifecycle_bridge_retry_20260715_192421.sql`.
- Backup size: `2,881,697` bytes; plain PostgreSQL dump header verified.
- Restored clone and source matched for all `38/38` source tables and the
  established `15/15` count/digest set before clone mutation.
- Retained V1 route/operations/steps: `1/2/5`.
- Source release and binding sidecars remained absent.
- Source Canonical V2 route count remained `0`.
- Source operation-event/approval/flow counts remained `4/0/0`.
- Source retry fixture count remained `0`; inventory/stock tables were absent.

## Authoritative Disposable Clone

- Authoritative clean clone:
  `mes_runtime_lifecycle_bridge_retry_20260715_192421_clean`.
- Creation path: empty `template0` database followed by logical source dump
  restore. `TEMPLATE mes` was not used.
- Every mutation used an exact clone identity guard and rejected database
  `mes`.
- Earlier harness-development fixture runs were excluded from acceptance; the
  complete matrix below was rerun once, uninterrupted, on this fresh clone.
- Migrations/seed applied only to the clone, in order:
  `009_work_order_operation_route_binding.sql`,
  `010_work_order_route_release.sql`, and
  `006_station_execution_seed_canonical_v2.sql`.
- Verified shapes:
  - binding: `9/9/4`;
  - release: `14/15/5`;
  - V2 route/operations/steps: `1/2/4`;
  - OP10/OP20 steps: `3/1`;
  - configured/resolved location roles: `5/5`.

## Pre-Sidecar Legacy and Schema Gating

- Real marker-absent legacy finish succeeded with `finished=true` and
  `completion_bridge=None`.
- Instrumented schema-readiness/release/binding sidecar queries were `0/0/0`.
- Exact marker with sidecars absent returned HTTP-equivalent status `503` and
  `RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY`.
- Event, runtime, lifecycle, and queue scoped state had zero row/digest delta.
- A test-process unclassified `psycopg.errors.UndefinedTable` propagated as the
  original object and was not converted into legacy success.

## Main OP10 to OP20 Chain

- Route-generated release persisted one release, two deterministic lifecycle
  operations, two immutable bindings, one initial OP10 queue, and queued work
  order.
- Authoritative deterministic OP10 UUID:
  `2ca10942-0330-5b01-a305-ac39866db759`.
- Authoritative deterministic OP20 UUID:
  `7898abed-5b5c-5d90-b9fa-e1666a892db1`.
- OP10 initialized with three configured steps. The final finish closed runtime
  and returned `completion_bridge.bridged=true`.
- OP10 lifecycle/current queue completed at authoritative runtime `closed_at`;
  immutable quantities, payload, metadata, start timestamp, queue rank/source/
  payload/metadata were preserved.
- OP20 became queued and received one exact `runtime_completion_bridge` queue
  at rank `3` with no route/config ID in queue payload or metadata.
- OP20 initialized with one configured step. `PACKAGING_EXECUTION` start/finish
  closed runtime, completed OP20 lifecycle/queue, and completed the work order
  at the same authoritative `closed_at`.
- Immediate OP10 and OP20 duplicate finishes returned
  `finished=false`, `event_inserted=false`, and `bridged=false` with zero row
  digest delta.
- Old OP10 replay after OP20/work-order completion also returned
  `bridged=false` with zero writes.
- Nested bridge responses matched direct cursor-scoped authoritative readback.

## Real Concurrent Duplicate Replay

Two independent PostgreSQL connections were synchronized after both
applicability preflight reads and issued the exact same OP10 final finish.

- Winner: `finished=true`, `event_inserted=true`, `bridged=true`.
- Loser: `finished=false`, `event_inserted=false`, `bridged=false`.
- `RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT` did not occur.
- Persisted state contained one finish event, one closed runtime row, one OP10
  lifecycle completion, one OP10 queue terminalization, one OP20 activation,
  and one OP20 queue.
- Winner bridge instrumentation: one advisory-scope call, one rank read, and
  four bridge writes.
- Loser instrumentation: advisory calls `0`, rank reads `0`, writes `0`.
- Winner and loser authoritative bridge snapshots were equal apart from the
  `bridged` flag; no timestamp rewrite occurred.

## Station Concurrency and Queue Conflicts

- Two independent released work orders concurrently bridged into
  `PACKAGING_01`; both returned `bridged=true` with distinct ranks `4/5` and
  no deadlock.
- Each transaction used the unique lexical station set
  `ASSEMBLY_01, PACKAGING_01` and the exact advisory namespace
  `mes:work_order_release:station_queue:`.
- A high-rank `ready` control row at rank `999999` did not affect allocation;
  only `queued`, `active`, and `pending_approval` were active-rank inputs.
- Controlled equal current/successor station state used one
  `ASSEMBLY_01` advisory scope in the first transaction and one in fresh
  recovery, then returned `RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT`.
  All finish/runtime/lifecycle/queue changes rolled back and clean retry passed
  after restoring the controlled static station value.

## Live Queue 23505

- A non-cooperating connection occupied allocated successor rank `7` after
  rank computation.
- The first finish/bridge transaction rolled back completely; insertion was
  attempted once and no automatic rank retry occurred.
- The first context closed before authoritative recovery opened a new
  connection/transaction/cursor.
- Observed PostgreSQL backends were `28096` then `28098`; the aborted cursor
  was not reused.
- Fresh readback returned `RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT`.
- After blocker removal, an explicit caller retry returned `bridged=true`.

## Unknown Errors and Rollback Injection

- Test-process proxies injected unknown `23505`, `23503`, `40P01`, `40001`,
  `08006`, `XX000`, and a generic exception.
- Every original error object propagated unchanged, every real transaction
  rolled back to its exact pre-call row digest, and every clean retry passed.
- All `12/12` real-transaction injection points passed:
  - after finish-event insert;
  - after runtime-step completion;
  - after runtime close;
  - after current lifecycle completion;
  - after current queue terminalization;
  - after successor resolution;
  - after successor lifecycle update;
  - after station locks/queue reads;
  - after successor queue insert;
  - after final work-order completion;
  - before authoritative snapshot;
  - before transaction exit.
- Each case left zero table-row digest delta, including audit/outbox/package
  state, and its clean retry returned `bridged=true`.
- A controlled final-operation fixture with another incomplete lifecycle row
  returned `RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT`; the triggering
  finish rolled back and clean retry passed after fixture restoration.

## No-Extra-Audit Boundary

- `system_transition` operation-event delta: `0`.
- No bridge delta occurred in operation approvals, production flow,
  production completions, work-order events, integration/FERP outbox,
  item-station events, package WIP/session/traceability, or packaging units.
- No inventory movement/balance table existed, and none was created.
- Only the configured runtime start/finish events were written.

## Cleanup and Final Source Integrity

- Exact authoritative clone sessions were terminated and the clone was
  dropped.
- Remaining `mes_runtime_lifecycle_bridge_retry_%` database count: `0`.
- Matching container temporary file count: `0`.
- Host backup remained present at `2,881,697` bytes.
- A final repeatable-read/read-only source snapshot matched the restored
  baseline for `38/38` tables and all established `15/15` counts/digests.
- Final full-table fingerprint:
  `65a7a087833c57ddd69d28db62fdd606c675c1ea32a7f58a4200d04ca8646d6d`.
- Source sidecars remained absent, V2 count remained `0`, retained V1 remained
  `1/2/5`, audit remained `4/0/0`, and retry fixture count remained `0`.
- HTTP health was `200` with `status=ok`; container health was `healthy`.

## Guardrails

- No source migration, seed, release, runtime, bridge, or fixture write.
- No API, Kiosk, IoT, OEE, FERP, MESQL, inventory, backfill, adoption, or
  `complete_operation_v2` action.
- No Docker rebuild, recreate, restart, down, image, volume, or lifecycle
  operation.
- Original FAIL evidence was not amended, replaced, or renamed.
- This retry evidence and `CURRENT_STATE.md` closure remain uncommitted.
- No push was performed.
