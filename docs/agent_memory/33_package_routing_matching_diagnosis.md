# F2D-E Package Routing / Matching Diagnosis

## 1. Purpose
This document records the read-only diagnosis after the F2D-D package smoke test failed to prove a package work-order-bound completion.

No code, runtime state, `.env`, migration, Docker lifecycle, or database write changes were made in this diagnosis phase. Runtime files and PostgreSQL were inspected read-only.

## 2. F2D-D Failure Summary
- `production_completions` live hook worked.
- DB count moved from `15` to `16`.
- The new row was not package-bound:
  - `external_ref=TEST-FERP-001_31`
  - `order_id=TEST-FERP-001`
  - `item_id=31`
  - `classification=GOOD`
  - `source_file=runtime_hook`
- The expected package-bound result would have used a `WO-PKT-*` order id.

This is not a live hook failure. The hook wrote the item it received after runtime routing. The failure is upstream: the runtime did not create a separate package completion item/order context.

## 3. Correct Production-to-Packaging Model
The correct process is two-stage:

1. Station 1 produces a colored box.
2. The box receives a quality classification.
3. Only `GOOD` boxes become package input candidates.
4. `REWORK`, `SCRAP`, and other NOK outcomes must not enter package input.
5. Station 2 / kiosk starts a package work order such as `WO-PKT-RED-001`.
6. Package flow consumes one compatible upstream `GOOD` box.
7. Package finish produces a separate package completion.
8. That package completion must be written to `production_completions` with `order_id=WO-PKT-*`.
9. The package completion payload/metadata should preserve upstream traceability.

The finished red box is not itself the red package. It is the input for a later red package operation.

## 4. Current Runtime State Analysis
Read-only runtime state inspection showed:

- Runtime work order count: `6`
- `WO-PKT-BLUE-001`, `WO-PKT-RED-001`, and `WO-PKT-YELLOW-001` are present.
- Current `activeOrderId` was `WO-PKT-RED-001` after the user attempt.
- `inventoryByProduct` was `{}`.
- Latest completed item:
  - `item_id=31`
  - `final_color=red`
  - `classification=GOOD`
  - `work_order_id=TEST-FERP-001`
  - `inventoryAction=work_order`
  - `work_order_match_key=red`
  - `inventory_match_key=""`

This means the latest red box is linked to the production work order, not available as package input.

## 5. Current Routing / Matching Behavior
Current runtime routing is centered on `_complete_runtime_item()` and `_route_completed_item_to_work_orders()` in `mes_web/oee_state.py`.

Observed behavior:

- `_complete_runtime_item()` sets `completed_at`, `classification=GOOD`, `queue_status=completed`, and freezes the final color.
- It then calls `_route_completed_item_to_work_orders()`.
- `_route_completed_item_to_work_orders()` only checks the current active work order.
- If the active work order has a matching remaining requirement, the item is assigned to that active order.
- If there is no matching active order and the item is not `SCRAP`, the item is moved to `inventoryByProduct` with `inventoryAction=off_order_completion`.
- Queued `WO-PKT-*` orders are not scanned as downstream package orders.
- Already completed items are not reprocessed because `_complete_runtime_item()` returns early when `completed_at` already exists.

Therefore a completed `TEST-FERP-001` red box cannot later become a `WO-PKT-RED-001` package completion through the current completion path.

## 6. Inventory / Buffer Analysis
There is an existing `workOrders.inventoryByProduct` state area.

It is useful for generic inventory/off-order behavior:

- Off-order `GOOD` completions can be stored there.
- `start_work_order()` can consume matching inventory when a work order starts.
- Existing tests validate this behavior for color-matched inventory consumption.

But it is not a complete package buffer for this use case:

- Work-order-linked completed items are skipped by inventory backfill.
- `_sync_completed_item_inventory_eligibility()` returns `work_order_linked` for items that already have `work_order_id`.
- Consuming inventory for a work order assigns the item to the consuming order, which is risky for upstream traceability unless extra fields are added.
- Current inventory exclusion only explicitly blocks `SCRAP`; package eligibility should require exactly `GOOD`.

Recommended minimal model: add an explicit runtime package input buffer, for example under `workOrders.packagingBuffer`, rather than overloading `inventoryByProduct` directly.

The buffer can still reuse the existing color/match-key logic, but it should preserve package-specific fields:

- `item_id`
- `upstream_order_id`
- `upstream_external_ref`
- `color`
- `product_code`
- `classification`
- `completed_at`
- `quality_locked_at`
- `package_status`: `available`, `reserved`, `consumed`
- `reserved_by_packaging_order_id`
- `consumed_at`

No database migration is required for the first MVP because package traceability can live in runtime JSON and in the package completion payload/metadata.

## 7. Package Work Order Selection Policy
For the first MVP, the safest policy is kiosk-assisted explicit selection with backend validation.

Recommended behavior:

- Kiosk shows package orders separately from production orders.
- Operator selects a `WO-PKT-*` order, or the kiosk suggests one based on available `GOOD` buffer color.
- Backend validates that the selected package order color/match key has at least one available `GOOD` upstream box.
- Backend rejects package start if no matching available item exists.
- Queue priority rules for normal production work orders should not block package-specific start, as long as package flow is explicitly entered.

Automatic selection by color can be added later, but first MVP should keep operator intent visible.

## 8. Kiosk Package Flow Proposal
Add a first-class package flow to the kiosk:

1. `GET kiosk/bootstrap` exposes package buffer counts by color and queued `WO-PKT-*` orders.
2. `POST kiosk/package/start` reserves one compatible `GOOD` upstream item for the selected package order.
3. Kiosk shows the reserved upstream item and selected package order.
4. `POST kiosk/package/finish` creates a new package completion item.
5. The package completion item uses:
   - `work_order_id=WO-PKT-*`
   - `classification=GOOD`
   - `completed_at=<finish time>`
   - `inventoryAction=package_completion`
   - `work_order_match_key=<color>`
   - trace fields for the consumed upstream item.
6. The existing `production_completions` live hook writes that package item.

Pick-to-light is not part of the first MVP. Kiosk `package start` / `package finish` is enough.

## 9. Quality Locking Policy
Current kiosk quality override is already limited:

- Kiosk override only sees recent completed items.
- Items linked to completed work orders are not overrideable through the kiosk path.

F2D-F should make the package lock explicit:

- A completed production item can be adjusted only before it is packaged.
- Once reserved/consumed by package flow, it should get fields such as `packaged_at` and `packaging_order_id`.
- Quality override must reject items with package consumption fields.
- `REWORK`, `SCRAP`, and NOK items must be removed from or blocked from package buffer.

Package completion quality should also be locked after package finish for the first MVP.

## 10. Production Completions DB Impact
The current `production_completion_writer.py` does not need a first-pass change.

It builds the natural key from:

- `order_id` / `work_order_id`
- `item_id`

and writes `payload` plus `metadata`.

If package finish creates a package item with `work_order_id=WO-PKT-RED-001`, non-empty `item_id`, and non-empty `completed_at`, the current writer should generate an APPLY_SAFE row like:

- `external_ref=WO-PKT-RED-001_<package_item_id>`
- `order_id=WO-PKT-RED-001`
- `source_file=runtime_hook`

Traceability fields can be carried in the payload/metadata without schema migration:

- `consumed_item_id`
- `upstream_order_id`
- `upstream_external_ref`
- `packaging_order_id`
- `color`
- `product_code`

## 11. Minimal Implementation Options
Option A: Use `inventoryByProduct` directly.

- Pros: Reuses existing matching and consumption helpers.
- Cons: Can overwrite upstream `work_order_id`, blurs generic inventory with package input, and needs extra guardrails to preserve traceability.

Option B: Add explicit `packagingBuffer`.

- Pros: Clearer semantics, safer traceability, easier quality lock, avoids changing generic inventory behavior.
- Cons: Requires new small state helper methods and kiosk endpoints.

Option C: Do only package finish synthetic item creation without buffer.

- Pros: Smallest code change.
- Cons: Weak validation and traceability; risk of packaging NOK or already consumed items.

Recommended: Option B.

## 12. Recommended Implementation Path
F2D-F should be kept small:

1. Add runtime helpers for package eligibility:
   - identify completed `GOOD` production items
   - exclude package-completed, reserved, `REWORK`, `SCRAP`, and NOK items
2. Add `workOrders.packagingBuffer` or an equivalent explicit projection.
3. Populate/update the buffer after production order acceptance and quality override changes.
4. Add kiosk package start/finish endpoints.
5. On package finish, create a package completion item with `work_order_id=WO-PKT-*`.
6. Reuse the existing production completion live hook/writer.
7. Add focused tests for red package flow, NOK exclusion, and quality lock.

## 13. Files Likely To Change in F2D-F
Likely source files:

- `mes_web/oee_state.py`
- `mes_web/app.py`
- kiosk frontend/static files if the package controls are visible in the existing kiosk UI
- `tests/test_mes_web_oee_state.py`
- `tests/test_mes_web_kiosk_app.py`

Avoid changing:

- `mes_web/db/production_completion_writer.py`, unless tests prove the package item shape cannot be represented by the current writer.
- migrations, for the first MVP.

## 14. Migration Need Assessment
No migration should be required for the first MVP.

Reasons:

- Runtime JSON can hold package buffer state.
- `production_completions.payload` can hold traceability fields.
- `production_completions.metadata` can hold hook/package context.
- Existing `order_id`, `item_id`, `completed_at`, `external_ref`, and unique-key behavior are sufficient for package completion rows.

A later traceability schema can be added after the kiosk package flow is proven.

## 15. Safety Rules
F2D-F should follow these safety rules:

- Keep DB read transition out of scope.
- Keep PostgreSQL not-full-source-of-truth.
- Keep live flags false by default.
- Do not modify migrations unless a later explicit phase requires it.
- Do not change the production completion writer unless necessary.
- Protect package flow with tests before another controlled live test.
- Never allow `REWORK`, `SCRAP`, or NOK items into package buffer.
- Never allow quality reclassification after package consumption.

## 16. F2D-F Prompt Outline
Suggested next prompt:

```text
Proceed to F2D-F package buffer + kiosk package flow implementation.

Scope:
- Implement explicit package input buffer for completed GOOD production boxes.
- Add kiosk package start/finish endpoints.
- Package finish must create a new runtime package completion item with work_order_id=WO-PKT-*.
- Existing production_completions writer should remain unchanged unless tests prove it cannot support the item shape.
- No migration.
- No DB read transition.
- Add focused unit/API tests.

Safety:
- Do not enable live DB flags.
- Do not run controlled live test in this implementation phase.
- Do not change .env, compose, Docker, or migrations.
```

## 17. Next Recommended Step
Proceed to F2D-F implementation planning/implementation after user approval.

F2D-D should not be considered passed yet. It proved that the live hook still works, but it did not prove package work-order binding.

The next successful smoke test should require:

- runtime work orders include `WO-PKT-*`
- one completed `GOOD` box enters package input
- kiosk starts and finishes a package flow
- `production_completions` count increases by one
- the new row has `order_id=WO-PKT-*`
- payload/metadata records the consumed upstream item
- duplicate `external_ref` remains zero
- live flags are restored false after the test
