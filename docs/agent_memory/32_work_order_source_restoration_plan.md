# Work Order Source Restoration Plan (F2D-B)

## 1. Purpose
This document outlines the strategy for restoring the missing `WO-PKT-*` packaging work orders to the runtime source file (`ferp_work_orders.json`). This will resolve the state drift between the PostgreSQL database (which retained the packaging orders) and the MES runtime (which lost them due to a source file replacement).

## 2. Diagnosis Summary
- **Runtime:** Contains only 3 test orders (`TEST-FERP-001`, `TEST-FERP-REWORK`, `TEST-FERP-SCRAP`).
- **Database:** Contains 6 orders, including `WO-PKT-RED-001`, `WO-PKT-YELLOW-001`, and `WO-PKT-BLUE-001`.
- **Root Cause:** The `ferp_work_orders.json` file was updated/replaced with a version containing only the 3 test orders, causing the runtime to drop the packaging orders during the next reload.

## 3. Current Runtime Work Order Source
The file `mes_web/ferp_import/ferp_work_orders.json` uses a specific nested FERP extraction structure:
```json
{
  "source": {
    "system": "FERP",
    "note": "Physical field test work orders. MES reload reads this folder by default."
  },
  "orders": [
    {
      "ferp_object": "mym4004",
      "ferp_screen": "Is Emirleri",
      "cycle_time_sec": 15,
      "ferp_labels": {
        "lblMMFB0_NUMBER": "TEST-FERP-001",
        "lblMMFB0_QTY": 1,
        "lblMTM00_CODE": "BOX-RED",
        "lblMTM00_NAME": "Kirmizi Test Kutusu",
        "lblMMFB0_DESC": "Fiziksel saha test is emri - GOOD akisi"
      }
    }
  ]
}
```

## 4. Current DB Work Order State
The `mes.work_orders` table contains the parsed payloads for the missing orders:
- `orderId`: WO-PKT-RED-001, WO-PKT-YELLOW-001, WO-PKT-BLUE-001
- `stockCode`: PKT-RED, PKT-YELLOW, PKT-BLUE
- `erpType`: Paketleme Is Emirleri

## 5. Candidate Restoration Sources
- **DB Payload:** The safest and most accurate source. The DB contains the exact properties needed to reconstruct the `ferp_labels` format.
- **Old Backup:** The `data/logs/oee_runtime_state_before_*.json` files contain the internal MES representation, which is functionally equivalent to the DB payload.
- **Decision:** The DB payload will be used as the primary source of truth for the restoration values since it is structured, readily queryable, and officially mirrored.

## 6. Recommended Restoration Strategy
We will extract the 3 missing packaging orders from the database, convert them back into the expected `ferp_labels` schema, and append them to the existing `ferp_work_orders.json` file.

## 7. Merge vs Replace Decision
**Merge.** We must merge the restored `WO-PKT-*` orders with the current 3 `TEST-FERP-*` orders to yield a combined source file of 6 orders. Replacing the file entirely would destroy the current test orders. Care will be taken to prevent duplicate `order_id`s during the merge.

## 8. Runtime Reload Requirement
After updating `ferp_work_orders.json`, the MES runtime must be forced to reload the source. This can be accomplished safely by:
1. Recreating the `mes_web` container (`docker compose up -d --force-recreate mes_web`).
2. Alternatively, triggering the internal `/api/ferp/reload` endpoint.
We will use the container recreate method for maximum determinism.

## 9. Safety Rules
- Take a backup of the current `ferp_work_orders.json` before any modification.
- Do not modify the DB state.
- Do not alter the `.env` file.
- Perform the modifications carefully via a one-off script during the F2D-C phase.

## 10. Exact F2D-C Apply Plan
1. Backup `mes_web/ferp_import/ferp_work_orders.json` to `.bak`.
2. Query the DB for the missing `WO-PKT-*` payloads.
3. Map the DB payload fields to `ferp_labels` (`orderId` -> `lblMMFB0_NUMBER`, `stockCode` -> `lblMTM00_CODE`, etc.).
4. Append the newly formatted objects to the `orders` array in `ferp_work_orders.json`.
5. Sync the updated file to the portable Docker `app_source`.
6. Restart `mes_web` to trigger the reload.

## 11. Verification Plan
- `mes_web` logs should show 6 work orders loaded.
- `verify_work_orders_db_mirror.py` should report 0 missing and 0 extra in DB (perfect sync).

## 12. Rollback Plan
Restore the `ferp_work_orders.json.bak` file and restart the `mes_web` container.

## 13. Impact on Production Completions Live Hook
The live hook will perfectly align with the new state. Packaging completions will no longer be marked `OFF_ORDER` since the parent work orders will exist in the runtime state again.

## 14. Not In Scope
- DB writes or schema changes.
- Modifying the production completions hook logic.

## 15. Next Recommended Step
Proceed to **F2D-C: Controlled Work Order Source Restoration Apply**, executing the merge script according to this plan.
