# Work-Order Route-Release Writer Isolated Smoke Evidence

## Summary

- Date: `2026-07-15`.
- Result: `PASS`.
- Reviewed and committed implementation:
  `e123a7d38e13fa64cabce71531b74fcfce12d7ff` (`e123a7d`,
  `feat: add work-order route release writer`).
- The Phase 5D-C route-generated writer passed review, regression, real
  PostgreSQL first-release/replay, mutable-progression replay, deterministic
  conflict, concurrency, queue-conflict, error-propagation, rollback, read
  model, and runtime-init verification.
- All database writes were confined to the exact disposable clone. Source
  database `mes` was used only for backup and read-only baseline/final checks.
- Phase 5F runtime completion, API, FERP, MESQL, inventory, and production
  rollout remain out of scope.

## Focused Review and Commit

- Initial implementation scope contained only:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Focused review result: no actionable P1 or P2 finding.
- The writer owns one connection, transaction, and cursor; private primitives
  open no nested connection and commit nothing.
- Replay equality correctly separates immutable release artefacts from mutable
  operational state. Lifecycle/work-order status, actual quantities,
  execution timestamps, and queue status/rank progression do not cause a
  replay conflict or rewind.
- Binding comparison is lifecycle-UUID scoped. Initial queue identity is tied
  only to the minimum-sequence lifecycle operation.
- Exact route/version selection has no latest/active fallback or inference.
- Queue rank selection uses exactly
  `status IN ('queued', 'active', 'pending_approval')`; `ready` is excluded.
- A `23505` exits the failed transaction/connection context before opening a
  new authoritative readback context.
- Commit scope was exactly the two reviewed files. No push occurred.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `403` tests, `OK`.
- Combined station-execution config, station-location, and MESQL V2 suite:
  `439` tests, `OK`.
- `py_compile mes_web/db/mesql_v2.py`: PASS.
- `git diff --check`: PASS.
- Existing binding/runtime helper coverage remained green.

## Source, Backup, and Isolation

- Container/database/user: `mes_postgres` / `mes` / `mes`.
- PostgreSQL: `16.14`; host port `5433`.
- Retained plain logical backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_work_order_release_writer_smoke_20260715-143831.sql`.
- Backup size: `2,881,697` bytes; PostgreSQL dump header present; no password
  was printed.
- Disposable clone:
  `mes_work_order_release_writer_smoke_20260715_143831`.
- Clone creation was an empty `template0` database followed by logical restore.
  `TEMPLATE mes` was not used.
- Restore equality was `15/15` counts and `15/15` run-local digests. Every
  mutation asserted the exact clone name and rejected database `mes`.

## Source Baseline and Final Integrity

The run-local baseline and final check used ordered `to_json(t)::text` MD5
serialization and matched exactly for all 15 tables. A separate final
canonical `to_jsonb(t)::text` check matched the established committed source
baseline for all 15 tables. The two serialization methods intentionally
produce different non-empty-table hashes; no hash from one method was compared
to the other.

| Table | Count | Canonical `to_jsonb` MD5 | Run-local `to_json` MD5 |
|---|---:|---|---|
| `mes.items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` | `440b07f6b23e09bbfa4171caa7f34072` |
| `mes.process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` | `46c188199b56d5afe415d29c758d185d` |
| `mes.route_operations` | 2 | `92a859fc57182954c5070670928c89e6` | `af5e180618224d39b6c991ad1d819ca9` |
| `mes.operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` | `9e61686fbf61a317e3813d831576f2c5` |
| `mes.station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` | `5ee0abb9cdb4cf606bdb6c4f154726ba` |
| `mes.work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` | `d3f2f5e976ad1dd9741268abe9caf979` |
| `mes.work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` | `ee2cd9ab98c5ae8d032ebd9faaebe6e9` |
| `mes.operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` | `69de947409308bb8c4d007032ef74960` |
| `mes.operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` | `375c53b752067be40de9c5a7228a8200` |
| `mes.work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` | `8abb090caa13c2ee409c180a1640288b` |
| `mes.station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` | `9423c967e91b025c7dd73f2fc70bf5ad` |
| `mes.locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` | `df822dda6d55be15266731083542d015` |
| `mes.station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` | `4b8e4aeb5764e70ced10dc19fb5e9301` |

Extended source baseline and final state also matched:

- binding and release tables absent;
- Canonical V2 route count `0`;
- retained V1 route count `1`;
- events / approvals / production-flow counts `4 / 0 / 0`;
- source `PHASE5E-%` work-order count `0`.

## Clone Prerequisites and Negative Pre-Migration Check

- Logical restore reproduced the source baseline before any clone mutation.
- A clone-only planned candidate was inserted before migrations.
- Calling the real public writer before migration raised unmasked
  `psycopg.errors.UndefinedTable`, SQLSTATE `42P01`.
- The failed call left candidate status `planned`, operations `0`, and queue
  rows `0`.
- Only on the clone, migrations `009` and `010` plus
  `006_station_execution_seed_canonical_v2.sql` were applied.
- Verified shapes:
  - binding `9 / 9 / 4` columns / constraints / indexes;
  - release `14 / 15 / 5`;
  - Canonical V2 route / operations / steps `1 / 2 / 4`;
  - OP10 / OP20 steps `3 / 1`;
  - station-location roles `5 / 5`.
- Initial release/lifecycle/binding/queue artefact counts were all `0`.

## First Release and Read Model

- First public release returned `released=true` and committed exactly:
  - one release row;
  - two lifecycle operations;
  - two immutable lifecycle-UUID bindings;
  - one OP10 initial queue row;
  - work-order status `queued`.
- Deterministic lifecycle UUIDs were:
  - OP10: `db37c17e-c17d-5b9a-8d83-e3156cfdb247`;
  - OP20: `3d1ce242-ff59-55fd-ae8d-c1a36bb671f6`.
- OP10 was `queued` at `ASSEMBLY_01`; OP20 was `planned` at
  `PACKAGING_01`. Both preserved target quantity `5`, UOM `piece`, zero
  good/scrap quantities, empty payload, and the exact static route snapshot.
- Immediate identical replay returned `released=false` and the complete
  persisted state, timestamps, and queue rank were unchanged.
- After deliberate operational progression of work-order/operation statuses,
  good/scrap quantities, timestamps, and queue status/rank, replay still
  returned `released=false`, rewound nothing, and preserved the immutable
  release/operation/binding digest.
- All five Phase 5C helpers agreed with the writer response. A foreign
  work-order binding targeting the same route operation was excluded; observed
  binding leakage count was `0`.

## Runtime-Init Compatibility

- A separate released OP10 initialized successfully through the existing
  runtime helper.
- Runtime state was `ready`, `current_step=null`, with exactly three pending
  OP10 steps.
- Release, lifecycle, binding, and queue state was unchanged by init.
- Runtime init created no operation event, approval, or production-flow event.
- No step was executed and OP20 was not queued or initialized.

## Deterministic Conflicts and Eligibility

All expected conflicts returned the contracted error and left zero unintended
writes. After restoration of each controlled corruption, valid replay passed.

- release ID assigned to another order;
- order assigned to another release;
- route code/version and persisted mode mismatch;
- actor, metadata, and unsupported source mismatch;
- missing/extra lifecycle operation and static operation snapshot mismatch;
- missing/orphan binding and complete mapping/digest mismatch;
- missing, extra, or wrong initial queue identity.

Eligibility checks passed for missing work order, non-positive target,
product mismatch, started/terminal order, inactive route/item/operation,
missing unit policy, empty/duplicate operation set, pre-existing lifecycle, and
runtime/event evidence. The database schema prevents persisting a blank item
unit, so that writer policy branch was exercised by a test-process private
selector seam; no production flag or test-only production logic was added.

## Concurrency and Queue Allocation

- Two concurrent identical requests returned one `released=true` and one
  `released=false`, with one persisted release.
- Two different orders using the same release ID returned one success and one
  `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT`; the losing transaction left no
  release artefacts.
- Two concurrent different orders targeting `ASSEMBLY_01` both succeeded with
  distinct queue ranks. Each created only an OP10 queue row; OP20 queue count
  remained `0`.
- A controlled `ready` row at rank `161` was excluded. With active-set maximum
  `61`, the writer allocated `62`, proving exact partial-index predicate
  alignment.
- A non-cooperating clone-only queue insert occupied the selected active rank
  after allocation. The writer rolled back completely, returned
  `WORK_ORDER_RELEASE_QUEUE_CONFLICT`, and did not retry rank allocation.
- Instrumented DB-context events proved the failed first context exited before
  the recovery context entered, and the two contexts used different PostgreSQL
  backend PIDs. Removing the blocker allowed a clean `released=true` retry.

## SQLSTATE Propagation

- An unrelated real PostgreSQL `23505` was re-raised as the identical
  `psycopg.errors.UniqueViolation` object after authoritative readback found no
  supported release/queue classification. The transaction was clean and retry
  succeeded.
- Injected private-primitive failures with SQLSTATE `23503`, `40P01`, `40001`,
  `08006`, and `XX000`, plus a generic exception, propagated as the original
  objects with no release artefacts. Every clean retry succeeded.

## Rollback Failure Injection

All 12 documented injection points were exercised inside real PostgreSQL
writer transactions:

1. `after_work_order_lock`
2. `after_route_validation`
3. `after_release_insert`
4. `after_first_lifecycle_insert`
5. `after_all_lifecycle_inserts`
6. `after_first_binding`
7. `after_all_bindings`
8. `after_queue_insert`
9. `after_work_order_update`
10. `before_invariant_validation`
11. `before_snapshot_read`
12. `before_transaction_exit`

For every point, release/lifecycle/binding/queue/runtime/event/approval/flow
deltas were `0`; the work-order row, including status, payload, metadata, and
timestamps, was byte-equivalent to its baseline. All `12/12` clean retries
returned `released=true`. Failure injection used only temporary test-process
private primitive seams; production has no failure-injection flag.

## Cleanup and Health

- Final clone observation contained only clone fixtures and expected smoke
  artefacts; no source row was involved.
- The exact clone guard matched once. The clone was dropped with forced session
  termination.
- Remaining `mes_work_order_release_writer_smoke_%` databases: `0`.
- Container temporary dump copy: absent. Host logical backup retained.
- Final source count equality: `15/15`; final source digest equality: `15/15`.
- `mes_postgres`: healthy. `mes_web`: up.
- `GET http://127.0.0.1:8080/health`: HTTP `200`, `status=ok`.
- No Docker build, rebuild, recreate, restart, down, image, or volume action
  occurred.

## Guardrails

- No source migration, seed, fixture, writer, or mutation occurred.
- No API, feature flag, completion bridge, FERP, MESQL, Kiosk, IoT/OEE,
  approval, production-flow, or inventory implementation was added.
- No Phase 5F work was started.
- Evidence and `CURRENT_STATE.md` remain uncommitted and unstaged.
- No push, reset, rebase, amend, or `.agents/` access occurred.

## Result

`PASS`
