# F2D-F-A Package Flow Implementation

## 1. Purpose
This checkpoint documents the default-safe package buffer and kiosk package flow implementation.

The goal was to prepare code for package work-order-bound completions without enabling live DB writes, changing schema, changing Docker/runtime files, or changing the existing `production_completions` writer.

## 2. Implemented Runtime State
`workOrders` now includes explicit package state:

- `packagingBuffer`
  - `itemsById`
  - `availableItemIds`
- `packagingSessions`

The state normalizer tolerates missing legacy fields and creates default empty package structures.

## 3. Packaging Buffer Policy
Completed production items are eligible for packaging buffer only when:

- `item_id` is present.
- `completed_at` is present.
- `classification` is exactly `GOOD`.
- The item is not already a `WO-PKT-*` package item.
- The item is not already reserved, consumed, packaged, or quality locked.

`REWORK`, `SCRAP`, and NOK-style non-`GOOD` items do not enter the package buffer. Quality override resyncs buffer eligibility.

## 4. Package Start Flow
Added manager flow:

- `OeeRuntimeStateManager.start_package_flow(...)`

Added API endpoint:

- `POST /api/modules/{module_id}/kiosk/package/start`

Start behavior:

- Validates `package_order_id`.
- Requires a package work order, currently detected by `WO-PKT-*` and package/paket markers.
- Infers package color from order/product fields.
- Selects a matching available GOOD buffer item.
- Reserves the buffer item.
- Creates a `packagingSessions[session_id]` record.
- Marks the upstream item as package-reserved to block quality override during the session.

## 5. Package Finish Flow
Added manager flow:

- `OeeRuntimeStateManager.finish_package_flow(...)`

Added API endpoint:

- `POST /api/modules/{module_id}/kiosk/package/finish`

Finish behavior:

- Validates the active package session.
- Consumes the reserved buffer item.
- Produces a new runtime package completion item.
- The package item carries `work_order_id=WO-PKT-*`.
- The package item carries `inventoryAction=package_completion`.
- The upstream item is marked consumed and quality locked.
- Package work order completion counters are updated.
- Existing production completion dry-run/live hook functions are invoked with the package item.

## 6. Quality / Buffer Eligibility
Quality override now rejects package-reserved or package-consumed items with:

- `ITEM_QUALITY_LOCKED_BY_PACKAGING`

This prevents changing the quality result after package reservation/consumption.

## 7. Work Order Matching Policy
Package matching currently uses a small color inference helper:

- order/product color
- match key
- stock code/name
- `WO-PKT-*` package order detection

For first MVP, package order selection remains kiosk-explicit. Automatic routing can be added later after the controlled flow is proven.

## 8. Production Completions Hook Interaction
`mes_web/db/production_completion_writer.py` was not changed.

The existing hook remains responsible for writing package completions when live flags are enabled. Since package finish creates an item with:

- `work_order_id=WO-PKT-*`
- non-empty `item_id`
- non-empty `completed_at`

the existing natural key policy can produce:

- `external_ref={WO-PKT order id}_{package item id}`

## 9. Safety / Rollback Notes
Default runtime remains safe:

- No DB live flags were changed.
- No migration was added.
- No Docker build/restart was run.
- No DB write was performed.
- No `.env` change was made.

Rollback is limited to reverting the code changes in `mes_web/oee_state.py`, `mes_web/app.py`, and this document.

## 10. Tests Performed
Compile checks:

- `.venv\Scripts\python.exe -m py_compile mes_web/oee_state.py mes_web/app.py mes_web/db/production_completion_writer.py`

Unit-like local temp-state checks:

- GOOD red production item entered `packagingBuffer`.
- SCRAP item did not enter `packagingBuffer`.
- `WO-PKT-RED-001` package flow start reserved a buffer item.
- Package finish created a package item with `work_order_id=WO-PKT-RED-001`.
- Consumed upstream item became quality locked.

Static checks planned/performed for QA:

- `packagingBuffer`, `packagingSessions`, `WO-PKT`, and package routes are visible in source.
- No new SQL or `safe_db_write` was added to `app.py` or `oee_state.py`.

## 11. F2D-G Controlled Package Flow Test Plan
Recommended next controlled test:

1. Keep DB flags false.
2. Create one GOOD production box.
3. Confirm it appears in `packagingBuffer`.
4. Call package start for the matching `WO-PKT-*` order.
5. Call package finish.
6. Confirm a new package runtime item has `work_order_id=WO-PKT-*`.
7. Only after QA, run a separate controlled live DB test with temporary flags.
8. Confirm `production_completions` receives a new row with `order_id=WO-PKT-*`.
9. Restore flags false.

## 12. Not In Scope
- DB migration.
- DB read transition.
- Docker rebuild/restart.
- Runtime live DB write test.
- Pick-to-light integration.
- Frontend kiosk UI polishing.
- Changing `production_completion_writer.py`.
