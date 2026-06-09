# MVP SQL Transition Checkpoint

## 1. Purpose
This document marks the conclusion of the initial PostgreSQL transition sprint at an MVP (Minimum Viable Product) level. It serves as a comprehensive checkpoint for the current state of the database, the active hooks, and the remaining technical debt before moving to subsequent sprints.

## 2. MVP Scope
- **This checkpoint is NOT a "full PostgreSQL source-of-truth".**
- It represents an **"MVP operational persistence checkpoint"**.
- The runtime system continues to rely on the JSON/Excel/FERP/MQTT data flows as its primary operational truth.
- There is **no DB read transition yet**. All active integrations currently function in a write-only or mirrored capacity.

## 3. Current Database State
- **work_orders**: 6
- **production_completions**: 15
- **vision_events**: 43
- **Duplicate `external_ref`**: None (0)
- `production_completions` can successfully receive live inserts with `source_file='runtime_hook'`.

## 4. Completed PostgreSQL Transition Work
- Initial schema (`001_initial_mes_schema.sql`) applied.
- `F1F UNIQUE external_ref` migration successfully completed.
- Unique partial indexes created for `production_completions` and `vision_events` based on `external_ref`.
- Mirror verification scripts implemented and verified clean.
- Compose environment plumping for DB flags completed (`F1B-COMPOSE`).

## 5. Work Orders Status
- Verified as a stable **current-state mirror**.
- Mirror script correctly reflects the active runtime JSON state.

## 6. Production Completions Status
- The `production_completions` live write hook (`F2C`) is **stable**.
- Successfully passed dry-run observations (`F2B`).
- Successfully passed controlled live tests (`F2C-B`).
- Successfully passed multi-run observation tests (`F2C-C`) with correct `APPLY_SAFE` writing and `OFF_ORDER` skipping logic.
- Post-F2C multi-run count stands at **15**.

## 7. Vision Events Status
- Vision events are currently populated via a stable Excel backfill mirror process.
- **There is no live hook for vision events yet.**

## 8. Schema / Constraint Status
- The schema correctly enforces unique `external_ref` values where applicable.
- Constraints accurately reflect natural keys to prevent duplication during restarts or script re-runs.

## 9. Feature Flag / Fail-Open Status
- All database write hooks are strictly controlled by environment feature flags.
- By default, all runtime flags remain `false`.
- The `safe_db_write` utility operates with `fail-open` semantics to ensure that database issues do not crash the core MES runtime.

## 10. Runtime / Docker Status
- Docker volumes have **not** been deleted (`docker compose down -v` was avoided).
- The `mes_web` and `mes_web_portable` containers incorporate the latest F2C hook codebase.
- The `production_completions` multi-run testing correctly restored `.env` to safe mode post-test.

## 11. What Is Considered Done in This MVP
- Schema foundation and migrations.
- Controlled mirroring of base entities (work orders, completions, vision events).
- Fail-open write hook pattern established and proven for `production_completions`.
- Safely verifiable checkpoint mechanisms.

## 12. What Is Explicitly NOT Done Yet
- DB Read capabilities (the application does not load state from PostgreSQL).
- Live hooks for vision events, OEE snapshots, downtime, maintenance, quality, or device sessions.

## 13. Deferred Tables / Deferred Work
The following items are explicitly deferred to future sprints:
- `oee_snapshots`
- `downtime_events`
- `maintenance_records`
- `quality_overrides`
- `device_sessions`
- FERP outbox integrations

## 14. Risks and Known Gaps
- Since PostgreSQL is not the full source-of-truth, any manual modification to the JSON state files while the DB sync is disabled can lead to drift.
- `production_completions` functions as an event-log baseline rather than a strict current-state mirror, meaning it may contain historical records no longer present in the runtime JSON.

## 15. Work Order Source Reload Note
During the F2C multi-run checks, the runtime `workOrders` array only contained 3 test orders:
- `TEST-FERP-001`
- `TEST-FERP-REWORK`
- `TEST-FERP-SCRAP`

*(Loaded from `ferp_work_orders.json` at `2026-06-09T12:18:47.742+00:00`)*
Package/paket work orders were noticeably absent from the state/source. This is a separate FERP / work order source reload issue and is completely independent of the `production_completions` live hook logic.

## 16. Recommended Next Sprint
Due to user fatigue and the risk of unforced errors, it is recommended to close the current sprint at this checkpoint.
For the next sprint, the recommended options are:
- **A)** F3A `vision_events` live hook planning.
- **B)** `work_orders` shadow-read planning.

## 17. Safe Operating Rules Going Forward
- Maintain `MES_WEB_DB_ENABLED=false` by default until DB reads are implemented.
- Do not use `docker compose down -v` unless a full data wipe is explicitly intended.
- Any new hook must follow the `dry-run -> controlled test -> live hook` progression established in this MVP.
