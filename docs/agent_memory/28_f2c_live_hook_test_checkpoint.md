# F2C-B Production Completions Live Hook Test Checkpoint

## 1. Purpose
This checkpoint records the successful F2C-B controlled live test for the `production_completions` runtime hook. The test proves that the F2C live hook can write one controlled `APPLY_SAFE` production completion into PostgreSQL through the live runtime completion path.

## 2. F2C-A Code Baseline
- F2C-A commit: `b9911cf Add production completions live hook`
- `mes_web/db/production_completion_writer.py` was added in F2C-A.
- `build_production_completion_row()` returns a typed `ProductionCompletionRow` dataclass.
- The natural key / `external_ref` policy is `{order_id}_{item_id}`.
- `OFF_ORDER`, missing `order_id`, missing `item_id`, and missing `completed_at` records remain outside the write path.
- SQL is isolated in `production_completion_writer.py`.
- `mes_web/oee_state.py` does not import `safe_db_write` and does not contain SQL.
- The F2B dry-run hook was preserved.

## 3. Deployment Context
- Source repo was clean before the test.
- `app_source` sync completed successfully.
- The portable `mes_web` image was rebuilt successfully.
- Only the `mes_web` container was recreated.
- The F2C writer was confirmed inside the running container.
- Health checks returned `200` before and after the live test.

## 4. Backup References
- DB backup: `.\data\db_backups\mes_postgres_before_f2c_live_20260609-150051.sql`
- Runtime `.env` backup: `.env.before_f2c_live_20260609-150051.bak`

## 5. Temporary Runtime Flags
The following temporary flags were enabled for the controlled test:

- `MES_WEB_DB_ENABLED=true`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=false`
- `MES_WEB_DB_FAIL_OPEN=true`
- `MES_WEB_DB_MIRROR_WORK_ORDERS=false`

No vision, OEE snapshot, downtime, maintenance, quality override, or DB read-transition flags were enabled.

## 6. Live Hook Observation
One controlled work-order-bound completion cycle was created by the user.

Observed live hook result:

```text
[LIVE:production_completions] reason=written attempted=True success=True skipped=False
```

## 7. Inserted Production Completion
The live hook inserted the following production completion:

- `external_ref=TEST-FERP-001_27`
- `order_id=TEST-FERP-001`
- `item_id=27`
- `classification=GOOD`
- `completed_at=2026-06-09 12:04:07.981+00`
- `source_system=mes_web`
- `source_file=runtime_hook`

## 8. DB Count Change
- Starting `mes.production_completions` count: `12`
- Final `mes.production_completions` count: `13`

The count change confirms that one controlled live `APPLY_SAFE` completion was written.

## 9. Duplicate Check
Duplicate `external_ref` check returned zero rows.

This confirms that no duplicate natural key was created during the controlled live test.

## 10. Restore and Safe Mode Confirmation
The runtime `.env` file was restored from `.env.before_f2c_live_20260609-150051.bak`.

Final safe-mode flags:

- `MES_WEB_DB_ENABLED=false`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=false`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=false`
- `MES_WEB_DB_FAIL_OPEN=false`
- `MES_WEB_DB_MIRROR_WORK_ORDERS=false`

Final health check returned `200`.

## 11. What This Proves
- F2C production completions live hook passed a controlled runtime test.
- One controlled work-order-bound `APPLY_SAFE` completion was written to PostgreSQL.
- The inserted row used the expected `external_ref={order_id}_{item_id}` policy.
- The row preserved non-empty `order_id`, `item_id`, and `completed_at`.
- The hook wrote through the live runtime path with `source_file=runtime_hook`.
- No duplicate `external_ref` was created.
- The runtime was restored to safe mode after the test.

## 12. What This Does NOT Prove Yet
- This is not a DB read transition.
- PostgreSQL is still not the full source of truth.
- This does not prove long-running unattended production stability.
- This does not validate vision event hooks, OEE snapshot hooks, downtime hooks, maintenance hooks, or quality override hooks.
- This does not prove continuous live flag operation should be left enabled permanently.

## 13. Current DB State
After F2C-B, `mes.production_completions` count is `13`.

The live flag was disabled after the test, and runtime flags returned to false.

## 14. Next Recommended Step
Recommended next phase:

1. F2C multi-run observation, or
2. F3A `vision_events` live hook planning.

The F2C `production_completions` live hook has now passed a controlled test. Before leaving it continuously enabled, a few additional controlled observation runs are recommended.
