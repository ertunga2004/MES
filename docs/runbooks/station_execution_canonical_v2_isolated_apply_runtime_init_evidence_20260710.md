# Station Execution Canonical V2 Isolated Apply and Runtime Init Evidence

## Summary

- Date: 2026-07-10
- Result: `BLOCKED`
- The committed Canonical V2 seed was tested only against a disposable dump/restore clone.
- The first seed apply stopped at its fail-fast location-role assertion and rolled back.
- The source `mes` database remained read-only and its final integrity matched the recorded baseline.
- Reapply, read-model, runtime-candidate, and runtime-init checks were not run because the first-apply gate did not pass.

## V2 Artifact Commit

- Commit: `25a3691 feat: add canonical station execution v2 seed`
- The commit contains the four authorized files:
  - `db/migrations/006_station_execution_seed_canonical_v2.sql`
  - `docs/runbooks/station_execution_canonical_v2_seed_apply_runbook.md`
  - `docs/architecture/observation_quality_control_transition_plan.md`
  - `docs/architecture/CURRENT_STATE.md`
- No push, amend, reset, or branch operation was performed.

## Metadata Normalization

- Legacy metadata key/value occurrences before normalization: 14 instances of `"status":"draft"`.
- Legacy metadata occurrences after normalization: 0.
- Canonical row metadata occurrences after normalization: 14 instances of `"configuration_status":"canonical_v2"`.
- Documentation distinguishes the reviewed-but-unapplied seed artifact state from the metadata stored on inserted canonical rows.

## Regression

- Targeted regression: `Ran 91 tests` — `OK`.
- Combined regression: `Ran 127 tests` — `OK`.
- Only existing FastAPI `on_event` deprecation warnings were observed.

## Source Database

- Source database: `mes`.
- PostgreSQL service/container: `mes_postgres`.
- Application service/container: `mes_web`.
- Source access during the isolated smoke was limited to backup and read-only verification.
- The Canonical V2 seed was not applied to the source database.

## Backup

- Host backup: `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_canonical_v2_isolated_smoke_20260710-141441.sql`
- Backup size: 2,886,710 bytes.
- PostgreSQL dump header verification: PASS.
- Temporary container dump: `/tmp/mes_before_canonical_v2_isolated_smoke_20260710-141441.sql`.
- The host backup was retained; the temporary container dump was removed after cleanup.

## Source Baseline Counts

| Table | Count |
| --- | ---: |
| `items` | 3 |
| `process_routes` | 1 |
| `route_operations` | 2 |
| `operation_steps` | 5 |
| `station_event_sources` | 4 |
| `work_order_operation_execution_state` | 1 |
| `work_order_operation_steps` | 3 |
| `operation_events` | 4 |
| `operation_approvals` | 0 |
| `production_flow_events` | 0 |
| `work_orders` | 12 |
| `work_order_operations` | 8 |
| `station_queue` | 13 |
| `locations` | 8 |
| `station_location_bindings` | 8 |

## Source Baseline Digests

| Table | MD5 digest |
| --- | --- |
| `items` | `c120ee7ee8808e4280bcb02895f76e8c` |
| `process_routes` | `163f416bfdcf16ca469e43adbd47b324` |
| `route_operations` | `92a859fc57182954c5070670928c89e6` |
| `operation_steps` | `3829d1b0a5185a4ac59a509532b4abc8` |
| `station_event_sources` | `c70220808f91a8562d14377c47b2a698` |
| `work_order_operation_execution_state` | `293d69efdb273e2bd0a8e6062f930d28` |
| `work_order_operation_steps` | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `operation_events` | `5bcb14870e3147f60e15cebdd146bba4` |
| `operation_approvals` | `d41d8cd98f00b204e9800998ecf8427e` |
| `production_flow_events` | `d41d8cd98f00b204e9800998ecf8427e` |
| `work_orders` | `283cf9b28e57bc5d6d398169f935473d` |
| `work_order_operations` | `fb74f90dcb2460542ad6422609144b6f` |
| `station_queue` | `2760e411b756b4194df0f86e4987cb5a` |
| `locations` | `03842ba4695966bbc65a4ec3eac438e9` |
| `station_location_bindings` | `f5274a415a5d1744af064a539693d0be` |

## Retained V1 Baseline

- Retained execution state: active.
- Current step: `OPERATOR_OBSERVATION_APPROVAL`.
- Completion policy: `auto_pending`.
- Step states: completed, completed, pending.
- Target operation events: 4.
- Target operation approvals: 0.
- Target production-flow events: 0.
- Source Canonical V2 route count before the smoke: 0.

## Isolation Strategy

- A single disposable database was created by restoring the verified source dump into an empty database.
- PostgreSQL template cloning was not used.
- The seed apply was directed only to the disposable clone.
- No fixture or lifecycle write was introduced to manufacture a runtime candidate.

## Clone Database

- Clone: `mes_v2_seed_smoke_20260710_141441`.
- The clone was used only for restore verification and the first seed-apply attempt.

## Clone Restore Verification

- Restore completed successfully.
- All 15 recorded table counts and digests matched the source baseline.
- V1 shape after restore: 1 route, 2 operations, and 5 steps.
- V2 shape after restore: 0 routes, 0 operations, and 0 steps.
- The retained active/current legacy execution matched the source baseline.
- Result: `CLONE_RESTORE_PASS`.

## V2 First Apply

- Result: `BLOCKED`.
- PostgreSQL error: `Canonical V2 location-role verification failed`.
- Context: `PL/pgSQL function inline_code_block line 353 at RAISE`.
- The seed transaction rolled back; no Canonical V2 rows were committed in the clone.
- No manual row fix or source-database change was made.

Root cause observed from read-only source inspection:

- The SQL validation requires an active `ASSEMBLY_01 / output_scrap` binding.
- The current database has no such binding.
- Relevant active bindings found were:
  - `ASSEMBLY_01 / active_wip -> ASSEMBLY_WIP`
  - `ASSEMBLY_01 / input -> RAW_MATERIAL`
  - `ASSEMBLY_01 / output_buffer -> BETWEEN_ASSEMBLY_PACKAGING`
  - `ASSEMBLY_01 / output_good -> BETWEEN_ASSEMBLY_PACKAGING`
  - `PACKAGING_01 / active_wip -> PACKAGING_WIP`
  - `PACKAGING_01 / input -> BETWEEN_ASSEMBLY_PACKAGING`
  - `PACKAGING_01 / output_good -> FINISHED_GOODS`
  - `PACKAGING_01 / output_scrap -> SCRAP_AREA`

All inspected bindings and locations were active; item and operation scopes were null.

## V2 Exact-Shape Verification

- Not run because the first apply did not commit.
- The apply transaction rollback prevented a partial V2 shape from being accepted as evidence.

## V1 Preservation

- Clone post-apply preservation verification was not run because the apply gate failed and the transaction rolled back.
- Source V1 preservation was verified by the final 15-table count/digest comparison and retained-execution checks.

## Runtime and Lifecycle No-Write Verification

- No step start, step finish, approval, production-flow, or other lifecycle command was executed.
- No runtime fixture was created.
- Source lifecycle counts remained 4 operation events, 0 approvals, and 0 production-flow events.

## V2 Idempotency Reapply

- Not run because the first apply gate failed.
- A failed first apply cannot establish the prerequisite for an idempotency reapply result.

## Config Read-Model Verification

- Not run because no V2 seed rows were committed in the clone.

## Runtime Candidate

- Candidate discovery was not run because the configuration apply/read-model gates did not pass.
- No deterministic candidate was fabricated with fixtures.

## Runtime Init Preconditions

- Not evaluated because first apply and read-model verification were incomplete.

## First Runtime Init

- Not run.

## Runtime Init Idempotency

- Not run.

## Runtime Init Forbidden Mutation Verification

- Runtime init was not invoked.
- Source final integrity verification confirms that the smoke introduced no source runtime or lifecycle mutation.

## Clone Cleanup

- The disposable clone was dropped after the failed apply.
- Remaining database count matching `mes_v2_seed_smoke_20260710_141441`: 0.
- Result: `CLONE_ABSENT=mes_v2_seed_smoke_20260710_141441`.

## Source Final Integrity

- All 15 final source table counts matched their baselines.
- All 15 final source table digests matched their baselines.
- Retained execution remained active with current step `OPERATOR_OBSERVATION_APPROVAL`.
- Retained final step remained pending.
- Source lifecycle counts remained `4 | 0 | 0`.
- Source Canonical V2 route count remained 0.
- Result: `SOURCE_FINAL_INTEGRITY=PASS`.

## Health

- Preflight response: `{"status":"ok","time":"2026-07-10T11:14:42.331+00:00"}`.
- Final response: `{"status":"ok","time":"2026-07-10T11:17:07.897+00:00"}`.
- Application health remained OK after clone cleanup and source-integrity verification.

## Guardrails

- No seed apply or write was performed against source `mes`.
- No Docker rebuild, recreate, image pull, dependency install, schema reset, or service reconfiguration was performed.
- No lifecycle fixture or step execution was performed.
- No manual repair was applied to clone data after the assertion failure.
- No push, amend, reset, or branch operation was performed.
- `docs/architecture/CURRENT_STATE.md` was not updated after the smoke because the required end-to-end result was not PASS.

## Result

`BLOCKED`

The isolated smoke cannot proceed beyond the first apply until the architecture decides whether `ASSEMBLY_01` must have an `output_scrap` location binding or the Canonical V2 OP10 scrap-role/validation contract must be revised. That decision requires a follow-up change; it was not made inside this evidence-only blocked closeout.
