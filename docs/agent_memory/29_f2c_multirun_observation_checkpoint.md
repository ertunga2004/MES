# F2C-C Multi-Run Observation Checkpoint

## 1. Purpose
This document records the successful multi-run observation of the `production_completions` live hook (F2C-C). The goal was to prove that the hook correctly discriminates between valid and invalid completions, inserts valid records into the PostgreSQL database using `safe_db_write` in a fail-open manner, and correctly skips unassociated ones without disrupting runtime operations.

## 2. F2C-C Runtime Context
- Source repository is clean.
- F2C-A code commit: `b9911cf` Add production completions live hook
- F2C-B documentation commit: `e5b33b9` Add F2C live hook test checkpoint
- The `F2C writer` logic was active inside the container.

## 3. Backup References
Before the multi-run observation, safety backups were taken:
- **DB Backup**: `.\data\db_backups\mes_postgres_before_f2c_multirun_20260609-151409.sql`
- **ENV Backup**: `.env.before_f2c_multirun_20260609-151409.bak`

## 4. Temporary Runtime Flags
The observation was conducted with the following runtime flags active:
- `MES_WEB_DB_ENABLED=true`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=false`
- `MES_WEB_DB_FAIL_OPEN=true`

## 5. Live Hook Multi-Run Observation
Three separate physical completion cycles were triggered:
- 2x `APPLY_SAFE` completions (valid, work-order-bound).
- 1x `OFF_ORDER/SKIPPED` completion (invalid or unassociated).

Live hook logs observed:
- `[LIVE:production_completions] reason=written attempted=True success=True skipped=False`
- `[LIVE:production_completions] reason=written attempted=True success=True skipped=False`
- `[LIVE:production_completions] reason=off_order attempted=False success=False skipped=True`

## 6. APPLY_SAFE Written Events
The following valid items were successfully intercepted and written to the database with `source_file=runtime_hook`:
- `TEST-FERP-001_28`
- `TEST-FERP-REWORK_29`
Both had valid `order_id`, `item_id`, and `completed_at` values.

## 7. OFF_ORDER / Skipped Event
One completion item without a valid work order binding was successfully identified and skipped, avoiding any unnecessary DB operations.

## 8. DB Count Change
- Initial `production_completions` count: **13**
- Final `production_completions` count: **15**
The count increase of `+2` exactly matches the number of `APPLY_SAFE` completions written. The `OFF_ORDER` item was correctly excluded and not written to the DB.

## 9. Duplicate Check
- Duplicate `external_ref`: **0**

## 10. Restore and Safe Mode Confirmation
- Health check returned **200 OK** at both start and finish.
- The `.env` file was successfully restored from the backup.
- All runtime flags were successfully reverted to `false`:
  - `MES_WEB_DB_ENABLED=false`
  - `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=false`
  - `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=false`
  - `MES_WEB_DB_FAIL_OPEN=false`
  - `MES_WEB_DB_MIRROR_WORK_ORDERS=false`

## 11. What This Proves
- The F2C live hook successfully passed the multi-run test.
- Database writes occur in a controlled and expected manner exclusively for `APPLY_SAFE` completions.
- The `safe_db_write` mechanism operates successfully in `fail-open` mode.

## 12. What This Does NOT Prove Yet
- **PostgreSQL is NOT yet the full source-of-truth.**
- **There is NO DB read transition yet.** The application still reads state from JSON files.

## 13. Work Order Source Note
During read-only QA checks, the runtime `workOrders` array contained only 3 test orders: `TEST-FERP-001`, `TEST-FERP-REWORK`, and `TEST-FERP-SCRAP` (from `ferp_work_orders.json`, loaded at `2026-06-09T12:18:47.742+00:00`).
The "packaging" work orders were not present in the runtime source.
**Important:** This missing packaging work orders issue is a separate FERP / work order source reload matter and is unrelated to the `production_completions` live hook logic.

## 14. Current DB State
- **production_completions count:** 15

## 15. Next Recommended Step
The next step is to close out this sprint by proceeding to the **MVP SQL Transition Checkpoint**.
Other features such as Vision live hook, OEE snapshots, downtime, maintenance, quality, and DB read transition should be deferred to future sprints.
