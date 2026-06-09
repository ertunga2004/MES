# F2D-A Work Order Source / Reload Diagnosis

## 1. Purpose
This document records a read-only diagnosis of why package/paket work orders are missing from the current runtime `workOrders` state after the F2C `production_completions` live hook tests.

No code, runtime state, `.env`, migration, Docker lifecycle, or DB write changes were made during this diagnosis.

## 2. Current Runtime Work Order State
Current runtime state file:
- `/app/logs/oee_runtime_state.json`

Current runtime `workOrders.source`:
- `folder=/app/mes_web/ferp_import`
- `file=ferp_work_orders.json`
- `loadedAt=2026-06-09T12:18:47.742+00:00`

Current runtime `ordersById` contains 3 work orders:
- `TEST-FERP-001` - `completed` - `BOX-RED`
- `TEST-FERP-REWORK` - `completed` - `BOX-YEL`
- `TEST-FERP-SCRAP` - `queued` - `BOX-BLUE`

Runtime state package/paket search:
- `paket`: not found
- `package`: not found
- `pack`: not found
- `ambalaj`: not found

## 3. Current DB Work Order State
Read-only DB SELECT showed:
- `mes.work_orders` count: `6`

DB work orders:
- `TEST-FERP-001`
- `TEST-FERP-REWORK`
- `TEST-FERP-SCRAP`
- `WO-PKT-BLUE-001`
- `WO-PKT-RED-001`
- `WO-PKT-YELLOW-001`

The `WO-PKT-*` rows are still present in PostgreSQL with `source_file=ferp_work_orders.json` and `source_loaded_at=2026-06-05T11:40:21.088+00:00`.

This means DB and runtime currently drift:
- Runtime current state has 3 work orders.
- DB current-state mirror still has 6 work orders.
- The 3 missing runtime records are the `WO-PKT-*` package/paket work orders.

## 4. Source File Discovery
Runtime file discovery found:
- `/app/mes_web/ferp_import/ferp_work_orders.json`
- `/app/mes_web/work_orders/sample_work_orders.json`
- `/app/logs/oee_runtime_state.json`
- `/app/logs/oee_runtime_state_before_d5_20260608-164621.json`

Host/source repo files:
- `mes_web/ferp_import/ferp_work_orders.json`
- `mes_web/work_orders/sample_work_orders.json`

Current `mes_web/ferp_import/ferp_work_orders.json` contains only 3 physical field-test orders:
- `TEST-FERP-001`
- `TEST-FERP-REWORK`
- `TEST-FERP-SCRAP`

Current `mes_web/work_orders/sample_work_orders.json` contains 8 sample FERP-format orders, but no `WO-PKT-*` ids and no package/paket text.

Historical runtime backup `/app/logs/oee_runtime_state_before_d5_20260608-164621.json` contains 6 work orders and includes:
- `WO-PKT-RED-001`
- `WO-PKT-YELLOW-001`
- `WO-PKT-BLUE-001`

The historical backup source also points to:
- `folder=/app/mes_web/ferp_import`
- `file=ferp_work_orders.json`
- `loadedAt=2026-06-05T11:40:21.088+00:00`

## 5. Package/Paket Search Result
Package/paket terms were found in:
- Historical runtime backup: `/app/logs/oee_runtime_state_before_d5_20260608-164621.json`
- DB `mes.work_orders` rows via `WO-PKT-*` payloads

Package/paket terms were not found in:
- Current runtime state `/app/logs/oee_runtime_state.json`
- Current `/app/mes_web/ferp_import/ferp_work_orders.json`
- Current `/app/mes_web/work_orders/sample_work_orders.json`

## 6. Runtime Load/Reload Mechanism
`AppConfig.work_orders_dir` resolves as follows:
1. Use `MES_WEB_WORK_ORDERS_DIR` if set.
2. Else, if `ferp_import_dir` exists, use `mes_web/ferp_import`.
3. Else use `mes_web/work_orders`.

Because `mes_web/ferp_import` exists, runtime reload uses that folder by default.

Runtime startup behavior in `RuntimeService.start()`:
- It reads current runtime state.
- If `workOrders.ordersById` is empty, it loads the newest `*.json` from `config.work_orders_dir`.
- If runtime already has work orders, startup does not automatically reload source files.

Manual reload endpoint:
- `POST /api/modules/{module_id}/work-orders/reload`
- It selects the newest `*.json` from `config.work_orders_dir`.
- It calls `import_work_orders_from_file(..., replace_existing=True)`.

Import behavior:
- `replace_existing=True` builds the next runtime state from incoming source rows.
- Existing active/completed orders may be preserved when absent from the incoming source, but queued missing orders are not preserved.
- Therefore a reload from a 3-order `ferp_work_orders.json` can remove queued package/paket work orders from runtime state.

## 7. Root Cause Hypothesis
This does not look like a `production_completions` live hook bug.

Most likely root cause:
- The current runtime work order source file `ferp_work_orders.json` was replaced or regenerated as a 3-order physical field-test source.
- A reload/import then loaded that 3-order file at `2026-06-09T12:18:47.742+00:00`.
- Since the current source no longer contains `WO-PKT-*`, those package/paket orders disappeared from runtime state.

Supporting evidence:
- Historical runtime backup from `2026-06-05T11:40:21.088+00:00` contains 6 orders including `WO-PKT-*`.
- DB mirror still contains the same 6 orders, including `WO-PKT-*`, with `source_loaded_at=2026-06-05T11:40:21.088+00:00`.
- Current `ferp_work_orders.json` contains only the 3 `TEST-FERP-*` field-test orders.
- Current runtime `workOrders.source.loadedAt` is newer: `2026-06-09T12:18:47.742+00:00`.

## 8. Impact on Production Completions Live Hook
This is not a `production_completions` live hook issue.

The F2C live hook writes completion events based on the item after runtime routing. It does not load, reload, delete, or mutate work order source files. The hook successfully passed F2C-B and F2C-C:
- `APPLY_SAFE` completions were written.
- `OFF_ORDER` completions were skipped.
- Duplicate `external_ref` remained zero.

The missing package/paket work orders are a work order source/reload problem upstream of completion routing.

## 9. Recommended Fix Options
Recommended options, from least invasive to more involved:

1. Recreate or restore a complete `ferp_work_orders.json` that includes both the 3 physical field-test orders and the `WO-PKT-*` package/paket orders, then use the existing reload endpoint.
2. Use the existing `POST /api/modules/{module_id}/work-orders/import` endpoint with a complete payload and `replace_existing=true`, after backing up runtime state.
3. If the old 6-order state is the intended source, recover the `WO-PKT-*` order definitions from `/app/logs/oee_runtime_state_before_d5_20260608-164621.json` or from the DB payloads and regenerate the source file.
4. Add a future guard or UX warning before reload when the incoming source has fewer queued orders than current runtime or DB mirror. This is a code-change option and was not done in F2D-A.

Do not treat DB as source-of-truth yet. PostgreSQL still has no read transition.

## 10. Safe Next Step
Recommended next phase:
- F2D-B controlled work order source restoration plan.

Suggested F2D-B scope:
- Take runtime state and DB backups.
- Prepare a complete source JSON that includes `TEST-FERP-*` and `WO-PKT-*`.
- Validate it with existing import parsing rules.
- Reload/import through the existing endpoint.
- Verify runtime `ordersById` returns to 6 expected orders.
- Only then consider resyncing `mes.work_orders` current-state mirror if needed.

No direct DB read transition should be introduced in this step.
