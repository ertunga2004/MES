# F2C-A Production Completions Live Hook

## 1. Purpose
F2C-A adds the source-level code path that can mirror `APPLY_SAFE` production completion events into `mes.production_completions`. The feature remains default off. This phase is code preparation only.

## 2. Preconditions
- F1F created the partial unique index on `mes.production_completions.external_ref`.
- F2B dry-run observation confirmed `APPLY_SAFE` and `OFF_ORDER` routing semantics.
- F2B controlled resync aligned the database baseline before live hook preparation.

## 3. Hook Location
The live hook is attached in `mes_web/oee_state.py` after `_route_completed_item_to_work_orders(...)` and after the existing dry-run diagnostic hook, before `_complete_runtime_item(...)` returns `True`.

## 4. Feature Flag Behavior
- `MES_WEB_DB_ENABLED=false`: no write attempt.
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=true`: dry-run wins and live write is skipped.
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=false`: live hook is disabled.
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true` and dry-run false: live write path is eligible.
- If live and dry-run are both true, a warning is logged and no DB write is attempted.

## 5. APPLY_SAFE Policy
An item is a write candidate only when it has:
- `order_id` / `work_order_id`
- `item_id`
- `completed_at`

For valid candidates, the writer builds `external_ref` as `{order_id}_{item_id}`.
`build_production_completion_row(...)` returns a typed `ProductionCompletionRow` dataclass with attribute-style fields including `external_ref`, `status`, `apply_safe`, and `reason`.

## 6. OFF_ORDER / SKIPPED Policy
OFF_ORDER, missing order id, missing item id, and missing completed timestamp records are skipped before `safe_db_write` is called. OFF_ORDER includes `inventoryAction=off_order_completion` and `inventoryAction=scrap_excluded`.

## 7. Natural Key / external_ref Policy
The live hook uses the same natural key policy as the mirror/resync flow:
`external_ref = f"{order_id}_{item_id}"`.

This key matches the partial unique index:
`ux_mes_production_completions_external_ref`.

## 8. DB Write Strategy
SQL is isolated in `mes_web/db/production_completion_writer.py`. The writer uses `safe_db_write` and an idempotent PostgreSQL upsert against the existing columns in `mes.production_completions`.

The table currently has `created_at` but no `updated_at`, so the upsert updates only existing table columns.

## 9. Fail-Open Behavior
The live hook remains fail-open. Writer errors return `DatabaseWriteResult(reason="error_fail_open")`, and `_complete_runtime_item(...)` continues without changing its return behavior.

## 10. No Runtime Activation in F2C-A
F2C-A does not enable runtime flags, edit `.env`, restart containers, run migrations, or perform DB write tests. PostgreSQL is still not the full source of truth, and no DB read transition is included.

## 11. F2C-B Controlled Test Plan
F2C-B should:
- take a fresh PostgreSQL backup,
- temporarily enable `MES_WEB_DB_ENABLED=true`,
- set `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true`,
- keep dry-run false,
- run a controlled completion,
- verify one idempotent row in `mes.production_completions`,
- restore flags to false.

## 12. Things Not To Do
- Do not run F2C-B live tests in F2C-A.
- Do not change work order read paths.
- Do not add vision or OEE snapshot hooks.
- Do not edit migrations, scripts, compose files, `.env`, data, logs, exports, or app source folders.
- Do not make PostgreSQL the source of truth yet.

## 13. Next Recommended Step
Review the F2C-A source diff and source-level test output. If accepted, the next phase is F2C-A commit/push, followed by F2C-B controlled live write testing.
