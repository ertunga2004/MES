# Station Execution Canonical V2 Isolated Apply and Runtime Init Retry Evidence

## Summary

- Execution date: 2026-07-13.
- Result: `BLOCKED`.
- The optional scrap-role fix passed regression, isolated seed apply,
  idempotency, exact-shape, and config read-model verification.
- Runtime initialization was not run because the disposable clone contained no
  eligible work-order operation with canonical
  `operation_code=ASSEMBLY_COLOR_CLASSIFY`.
- No lifecycle fixture, work order, operation-status change, or retained-target
  reuse was allowed to manufacture a candidate.

## Prior Blocker

- Prior first-apply result: `BLOCKED`.
- Cause: the seed required an active `ASSEMBLY_01/output_scrap` binding that did
  not exist.
- The prior transaction rolled back and committed zero Canonical V2 rows.
- The prior clone was dropped and source `mes` passed 15/15 count and digest
  comparison.

## PM Decision

- OP10 output role: `output_buffer`.
- OP10 scrap role: `null`.
- OP20 output role: `output_good`.
- OP20 scrap role: `output_scrap`.
- Scrap is an optional, nullable operation capability. A binding is required
  only when the operation config contains a non-null scrap role.
- Process-end observation is not a scrap decision; no artificial
  `ASSEMBLY_01/output_scrap` binding was created.

## Blocker Evidence Commit

- Commit: `936bcec docs: record canonical v2 isolated apply blocker`.
- Historical evidence:
  `docs/runbooks/station_execution_canonical_v2_isolated_apply_runtime_init_evidence_20260710.md`.
- The historical BLOCKED evidence was not changed after commit.

## Optional Scrap-Role Fix Commit

- Commit: `4750f92 fix: make canonical v2 scrap routing optional`.
- Changed paths:
  - `db/migrations/006_station_execution_seed_canonical_v2.sql`
  - `docs/runbooks/station_execution_canonical_v2_seed_apply_runbook.md`
  - `docs/architecture/observation_quality_control_transition_plan.md`
  - `docs/architecture/CURRENT_STATE.md`
- No push was performed.

## Regression

- Targeted: `Ran 91 tests` - `OK`.
- Combined: `Ran 127 tests` - `OK`.
- `git diff --check`: PASS before the fix commit.
- Static SQL review:
  - OP10 seed value is `NULL::text`.
  - OP10 exact-shape assertion uses `scrap_location_role IS NULL`.
  - OP20 retains `scrap_location_role = 'output_scrap'`.
  - Configured location-role requirement is `5`.
  - No `ASSEMBLY_01/output_scrap` prerequisite remains.
  - Canonical metadata occurrences: 14.
  - Legacy `"status":"draft"` metadata occurrences: 0.
  - No `UPDATE mes.`, `DELETE FROM mes.`, `TRUNCATE`, `DROP TABLE`,
    `ALTER TABLE`, or `ON CONFLICT DO UPDATE` was introduced.
  - V1 migration, V1 seed, Python, tests, and historical evidence were not
    changed by the fix commit.

## Source Database

- Source database: `mes`.
- PostgreSQL container: `mes_postgres`.
- Host port: `5433`.
- Source access during the retry was limited to logical backup and read-only
  verification.
- The Canonical V2 seed and runtime helpers were never run against source
  `mes`.

## Backup

- Host backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_canonical_v2_retry_smoke_20260713-134124.sql`.
- Size: 2,881,697 bytes.
- Plain PostgreSQL dump header: PASS.
- Temporary container dump:
  `/tmp/mes_before_canonical_v2_retry_smoke_20260713-134124.sql`.
- Host backup was retained; the container temporary dump was removed after
  clone cleanup.

## Source Baseline

| Table | Count | MD5 digest |
| --- | ---: | --- |
| `items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` |
| `route_operations` | 2 | `92a859fc57182954c5070670928c89e6` |
| `operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` |
| `station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` |
| `operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` |
| `work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` |
| `station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` |
| `locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` |

Retained V1 baseline:

- Work-order operation:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Execution status: `active`.
- Current step: `OPERATOR_OBSERVATION_APPROVAL`.
- Completion policy: `auto_complete_pending_approval`.
- Final step status: `pending`.
- Events / approvals / production flow: `4 / 0 / 0`.
- Source V2 route count: `0`.

## Isolation Strategy

- Clone: `mes_v2_seed_smoke_retry_20260713_134124`.
- The verified source dump was restored with `psql` into an empty database
  created from `template0`.
- `CREATE DATABASE ... TEMPLATE mes` was not used.
- Every apply/read-model command guarded the exact task-created clone name and
  rejected source `mes`.

## Clone Restore

- Logical restore: PASS.
- Source/clone comparison: 15/15 counts equal and 15/15 digests equal.
- V1 shape: 1 route, 2 operations, 5 steps.
- V2 shape: 0 routes, 0 operations, 0 steps.
- Retained runtime matched source.

## First V2 Apply

- Apply database guard printed:
  `APPLY_DATABASE=mes_v2_seed_smoke_retry_20260713_134124`.
- Transaction: committed.
- Inserted: 1 route, 2 route operations, 4 operation steps.
- Configured location roles: `5/5`.
- V1 route/config counts and digests were preserved.
- Runtime, audit, lifecycle, location, and binding counts/digests were
  unchanged.

## Optional Scrap-Role Verification

- OP10 `input_location_role=input`.
- OP10 `output_location_role=output_buffer`.
- OP10 `scrap_location_role=null`.
- OP20 `input_location_role=input`.
- OP20 `output_location_role=output_good`.
- OP20 `scrap_location_role=output_scrap`.
- The five configured non-null roles all resolved to active bindings and active
  locations under the existing item/operation scope rules.

## V2 Exact Shape

- Route: `ROUTE_BOX_PACKAGING_V2`, version 2, item `PACKAGED_PRODUCT`, active.
- OP10: `ROUTE_BOX_PACKAGING_V2_OP10`, `ASSEMBLY_COLOR_CLASSIFY`,
  `ASSEMBLY_01`, `auto_close_on_required_steps`.
- OP10 steps:
  - 10 `COLOR_SENSOR_ENTRY_EVIDENCE`
  - 20 `ROBOT_ARM_DROP_COMPLETED`
  - 30 `PROCESS_END_OBSERVATION`
- OP20: `ROUTE_BOX_PACKAGING_V2_OP20`, `PACKAGING_FINAL`, `PACKAGING_01`,
  `auto_close_on_required_steps`.
- OP20 step: 10 `PACKAGING_EXECUTION`.
- Legacy approval steps: 0.
- `approval_required_after_finish=true`: 0.
- `QUALITY_CONTROL` operations: 0.
- V2 first-apply digests:
  - route: `ecb11a85cb9f03acf74654d8f1c3ec20`
  - route operations: `dfd99879e14133b01b63c412befe443c`
  - operation steps: `2c265aa009325947326f1ad47d130e38`

## V1 Preservation

- Route: 1 / `163f416bfdcf16ca469e43adbd47b324`.
- Route operations: 2 / `92a859fc57182954c5070670928c89e6`.
- Operation steps: 5 / `3829d1b0a5185a4ac59a509532b4abc8`.
- Result: PASS after first apply and second apply.

## Runtime and Lifecycle No-Write

- First apply and reapply left the existing runtime state/steps at `1/3` with
  baseline-identical digests.
- Operation events / approvals / production flow remained `4/0/0`.
- Work orders / work-order operations / station queue remained `12/8/13` with
  baseline-identical digests.
- Locations / bindings remained `8/8` with baseline-identical digests.

## Idempotency Reapply

- Second apply transaction: success.
- Inserts: `0 / 0 / 0`.
- V1 counts and digests: unchanged.
- V2 counts and digests: unchanged.
- Runtime, audit, lifecycle, location, and binding counts/digests: unchanged.

## Config Read Model

- Verified helpers:
  - `list_process_routes`
  - `get_process_route`
  - `list_route_operations`
  - `get_route_operation`
  - `list_operation_steps`
  - `get_operation_step`
  - `get_route_operation_config`
  - `get_station_execution_config`
- V1 visible: true.
- V2 visible: true.
- Identifier collision: false.
- OP10: 3 steps, `auto_close_on_required_steps`, scrap null, 0 critical
  warnings.
- OP20: 1 step, `auto_close_on_required_steps`, scrap `output_scrap`, 0
  critical warnings.
- `ASSEMBLY_01` aggregate contained distinct V1 OP10 and V2 OP10 identifiers.
- `PACKAGING_01` aggregate contained distinct V1 OP20 and V2 OP20 identifiers.
- Post-read-model clone digests showed no DB write.

## Runtime Candidate

- The implementation signature was confirmed as
  `initialize_execution_state(config, work_order_operation_id,
  route_operation_id, station_code, actor_id=None)`.
- The helper loads an existing work-order operation by ID but does not itself
  filter its lifecycle status. The smoke therefore applied the stricter
  handoff candidate query before any helper call.
- Required station: `ASSEMBLY_01`.
- Required operation code: `ASSEMBLY_COLOR_CLASSIFY`.
- Excluded retained target:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Required absence of execution state, runtime steps, and operation events.
- Required nonterminal lifecycle status, with `queued` then `ready` preference.
- Eligible candidate count: `0`.
- Existing ASSEMBLY operation codes were `OP-ASSEMBLY` and `OP-MVP-ASM`, not
  the canonical V2 `ASSEMBLY_COLOR_CLASSIFY` code.
- Result: `BLOCKED`.

## Runtime Initialization

- Not run because no eligible canonical candidate existed.
- No new work order or lifecycle fixture was created.
- No operation code or status was changed.
- The retained V1 target was not reused.

## Runtime Init Idempotency

- Not run because first runtime initialization was blocked by candidate
  selection.

## Forbidden Mutation

- Runtime helper calls: 0.
- Step start/finish calls: 0.
- Work-order writes: 0.
- Work-order-operation writes: 0.
- Queue writes: 0.
- Event ledger writes: 0.
- Approval writes: 0.
- Production-flow writes: 0.
- Location/binding writes: 0.
- The clone final no-write digests matched the post-reapply baselines.

## Clone Cleanup

- Exact clone connections were terminated.
- Exact clone dropped: true.
- Exact clone remaining count: 0.
- Remaining databases matching `mes_v2_seed_smoke_retry_%`: none.
- Container temporary dump removed: true.
- Host backup retained: true.

## Source Final Integrity

- Source final count comparison: 15/15 equal.
- Source final digest comparison: 15/15 equal.
- Source V2 route count: 0.
- Retained execution: `active`.
- Retained current step: `OPERATOR_OBSERVATION_APPROVAL`.
- Retained final step: `pending`.
- Events / approvals / production flow: `4 / 0 / 0`.
- Unintended source mutation: none.

## Health

- Final response status: `ok`.
- No container rebuild, recreate, down, or volume operation was performed.

## Guardrails

- Source `mes` was unchanged.
- V2 was applied only to the disposable clone.
- No artificial ASSEMBLY scrap binding was created.
- No V1 configuration or runtime mutation occurred.
- No lifecycle fixture or new work order was created.
- No step start/finish helper was called.
- No API, Kiosk, IoT, Observer, OEE, MESQL, or FERP work was performed.
- No approval/manual-close helper, production flow, inventory movement,
  work-order selection, or work-order close implementation was performed.
- No Docker rebuild/recreate/down/volume action was performed.
- No push was performed.
- `.agents/` was not read, listed, searched, or changed.
- Because the result is not PASS, no verified retry checkpoint was added to
  `docs/architecture/CURRENT_STATE.md`.

## Result

`BLOCKED`

The optional scrap-role correction is verified through seed apply,
idempotency, and read model. Runtime initialization cannot be claimed without
an existing eligible `ASSEMBLY_01 / ASSEMBLY_COLOR_CLASSIFY` work-order
operation. Creating or mutating lifecycle data to manufacture that candidate
is outside this task's guardrails.
