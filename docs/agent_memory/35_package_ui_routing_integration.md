# 35. Package UI & Routing Integration

## Context
In phase F2D-F-A, the backend infrastructure for the Kiosk packaging flow was introduced (`packagingBuffer`, `packagingSessions`, `POST /package/start`, `POST /package/finish`).
However, during the F2D-G runtime test, it was discovered that the existing `Kiosk UI` didn't have a way to trigger these endpoints. The Kiosk UI relies on a central `bigActionButton` whose action label and state are dynamically calculated by `app.py` (`_kiosk_big_action()`) and whose clicks are handled in `kiosk.js` (`handleBigAction()`).

## Implementation Details

### 1. `mes_web/app.py`
The `_kiosk_big_action` function was updated to pass the `packaging` state into its context. It now evaluates package orders when an order is active:
- It checks if the active order is a packaging order using `_is_kiosk_package_order()`.
- It scans `packaging["active_sessions"]` to see if there is an active session for the current packaging order.
    - If YES: it returns the action `"package_finish"` with the label `"Paketlemeyi Bitir"`, supplying `session_id` in the payload.
    - If NO: it checks `packaging["buffer"]["available_count"]`.
        - If available count > 0, it returns `"package_start"` with the label `"Paketlemeyi Baslat"`, supplying `package_order_id` in the payload.
        - If available count = 0, it returns a disabled `"wait"` action with the label `"Uygun GOOD kutu yok"`.

To support this logic, `_project_kiosk_packaging()` is now called earlier in `_build_kiosk_snapshot` so the result can be reused inside the `_kiosk_big_action` invocation.

### 2. `mes_web/static/kiosk.js`
The central dispatch function `handleBigAction()` was updated to support the two new actions:
- **`package_start`**: Reads the `package_order_id` from the payload, constructs a REST body, and fires a `POST` request to `/api/modules/{module_id}/kiosk/package/start`.
- **`package_finish`**: Reads the `session_id` from the payload, constructs a REST body, and fires a `POST` request to `/api/modules/{module_id}/kiosk/package/finish`.

Both calls automatically reload the Kiosk bootstrap payload to update the view visually.

## Status
- **Source Code**: Modified and syntax verified (`app.py`, `kiosk.js`).
- **Runtime Test**: F2D-G can now be retried.

## QA Review Checkpoint Notes
- F2D-G blocker sebebi Kiosk UI integration eksikliðiydi.
- Bu commit package endpoints'i mevcut UI 'bigActionButton' yapýsýna baðlar.
- Bu faz sadece local source deðiþimidir, runtime test yapýlmamýþtýr.
- DB write veya herhangi bir migration uygulanmamýþtýr.
- Mevcut bilinen production_completions count = 18'dir.
- F2D-G týkanýklýk testi sýrasýnda yazýlan TEST-FERP-001_32 ve TEST-FERP-001_33 standart üretim kayýtlarýdýr, package completion deðildir.
- F2D-G retry baþarý kriteri, 'WO-PKT-*' order_id'si ile PostgreSQL'e baþarýlý bir hook insert atýlmasýdýr.
- PostgreSQL halen full source-of-truth deðildir, DB read transition yoktur.

