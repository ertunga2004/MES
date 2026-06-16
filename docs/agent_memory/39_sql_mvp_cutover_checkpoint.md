# 39. SQL MVP Cutover Checkpoint

Date: 2026-06-16

Decision: SQL MVP cutover is complete with guarded runtime rollout.

This checkpoint records the SQL MVP source-of-truth transition completed on
2026-06-16. It is a durable agent memory note for later work, not a migration
script and not an instruction to rerun deployment.

## 1. MVP Scope

Included in this MVP:

- `work_orders` can be read from PostgreSQL when
  `MES_WEB_DB_READ_WORK_ORDERS=true`.
- If DB read fails or DB returns no usable work orders, runtime JSON/FERP
  fallback remains active.
- `MES_WEB_DB_READ_WORK_ORDERS=true` is read-only behavior. It does not seed,
  mirror, or upsert work orders.
- `production_completions` live DB write remains enabled through its existing
  hook.
- `station_events` live writer was completed for
  `mes.item_station_events`.
- Dashboard and kiosk work-order views can operate from the DB work-order
  overlay.
- Excel, MQTT, FERP, and runtime JSON are preserved as audit/fallback/import
  and export paths.

Not included:

- Full SQL source-of-truth for all runtime state.
- Automatic work-order seeding when DB is empty.
- New DB migration in this cutover checkpoint.
- Removal of JSON, Excel, FERP, or MQTT paths.

## 2. Main Behavior Changes

- `mes_web/db/work_order_read.py` adds the DB work-order read adapter.
- `DashboardStore.refresh_oee_runtime_state()` overlays DB work orders when the
  read flag is enabled.
- Kiosk bootstrap uses the same DB work-order overlay.
- `work_order_mirror.py` now requires
  `MES_WEB_DB_MIRROR_WORK_ORDERS=true` for write/upsert.
- `MES_WEB_DB_READ_WORK_ORDERS=true` no longer triggers mirror/upsert.
- Runtime startup mirror only runs when `db_mirror_work_orders` is true.
- `station_event_writer.py` writes apply-safe station event rows with
  `ON CONFLICT (source, external_ref)` idempotency.
- `production_completions` behavior was kept unchanged, with regression tests
  added.

## 3. Runtime Flag Final State

Validated container flags after runtime revision deploy:

```text
MES_WEB_DB_READ_WORK_ORDERS=true
MES_WEB_DB_MIRROR_WORK_ORDERS=false
MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true
MES_WEB_DB_HOOK_STATION_EVENTS=true
```

Cutover flag set expected for this phase:

```text
MES_WEB_DB_ENABLED=true
MES_WEB_DB_FAIL_OPEN=true
MES_WEB_DB_READ_WORK_ORDERS=true
MES_WEB_DB_MIRROR_WORK_ORDERS=false
MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true
MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=false
MES_WEB_DB_HOOK_STATION_EVENTS=true
MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN=false
MES_WEB_DB_READ_DASHBOARD=false
MES_WEB_DB_SHADOW_READ_DASHBOARD=false
MES_WEB_DB_STRICT_TIMESTAMP_GUARD=false
```

Important policy:

- `READ_WORK_ORDERS` means read only.
- `MIRROR_WORK_ORDERS` means JSON/FERP to DB mirror/upsert.
- DB-empty work-order seeding is not automatic and must be handled by an
  explicit future import or seed path.

## 4. DB Validation Results

Runtime deploy validation results:

```text
work_orders count = 6
production_completions duplicate external_ref = 0
item_station_events duplicate source/external_ref = 0
```

Earlier cutover count snapshot:

```text
work_orders = 6, distinct order_id = 6
production_completions = 20, distinct external_ref = 20
item_station_events = 0, distinct source/external_ref = 0
```

Read/write guard validation:

```text
READ_WORK_ORDERS=true with MIRROR_WORK_ORDERS=false:
disabled|attempted=False|message=MES_WEB_DB_MIRROR_WORK_ORDERS=false
```

This confirms the read flag does not trigger work-order mirror/upsert.

## 5. Dashboard / Kiosk Smoke Result

Runtime smoke validation after revision deploy:

```text
/health = 200
dashboard konveyor_main work orders = 6
kiosk konveyor_main work orders = 6
```

Observed module:

```text
module_id = konveyor_main
```

## 6. JSON / Excel / FERP / MQTT Remaining Role

These paths remain intentionally active:

- Runtime JSON: fail-open fallback and current runtime state persistence.
- Excel workbook: audit/reporting log path.
- FERP import/export: work-order import and export workflow.
- MQTT: live ingest/publish path for the physical conveyor system.

PostgreSQL is now the MVP read source for work-order views when the flag is
enabled, but the system is not yet a full SQL-only runtime.

## 7. Backup Paths

Backups created during the SQL MVP cutover run:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\.env.before_mesql_sql_sot_20260616-132702.bak
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\compose.before_mesql_sql_sot_20260616-132825.yaml.bak
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\deploy_backups\mesql_sql_sot_20260616-132702
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs\backups\mesql_sql_sot_20260616-133122\oee_runtime_state.json.bak
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs\backups\mesql_sql_sot_20260616-133122\ferp_work_orders.json.bak
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mesql_sql_sot_20260616-133122.dump
```

This checkpoint document did not create new backups and did not modify runtime.

## 8. Known Gaps

- `item_station_events` had no rows at validation time because no new
  controlled station-event physical flow was run after the deploy.
- Full dashboard SQL read remains disabled:
  `MES_WEB_DB_READ_DASHBOARD=false`.
- Work-order DB empty state falls back to runtime JSON; there is no automatic
  DB seed.
- Vision events are not part of this runtime cutover as a new live source.
- Full SQL source-of-truth for OEE snapshots, downtime, maintenance, quality,
  device sessions, and complete package state remains future work.
- Container log review was intentionally not used as a required proof in the
  final revision flow.

## 9. Recommended Next Work

1. Run a controlled physical flow after deploy and verify
   `mes.item_station_events` inserts.
2. Add an explicit, operator-controlled work-order DB seed/import command if DB
   bootstrap from FERP is needed.
3. Add a shadow-read comparison report for work orders:
   DB rows vs runtime JSON rows.
4. Plan SQL read transition for package flow state separately from work-order
   read.
5. Keep `MES_WEB_DB_MIRROR_WORK_ORDERS=false` unless an explicit mirror/import
   operation is being tested.
6. Do not enable full dashboard DB read until OEE, package, quality, and
   downtime read models are designed.
