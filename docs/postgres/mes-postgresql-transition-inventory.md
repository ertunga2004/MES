# MES PostgreSQL Transition Inventory

## 1. Purpose

This document analyzes where persistent data is currently stored in the MES application and which data groups are candidates for a future PostgreSQL transition.

The scope is inventory and transition planning only. It does not define SQL migrations, PostgreSQL table DDL, or changes to the current Excel, JSON, FERP, MQTT, Docker, or MES application runtime behavior.

## 2. Current Persistence Summary

PostgreSQL is not the current source of truth in the MES system. Live state primarily flows through `logs/oee_runtime_state.json`, the Excel workbook, FERP import/export files, and work order JSON files.

`MES_WEB_DB_ENABLED` appears in Docker and documentation context, but the MES runtime does not currently bind that flag to an active database connection behavior.

## 3. Persistence Inventory Table

| Data group | Current location | Read/write behavior | Accessing module | PostgreSQL candidate | Notes |
|---|---|---|---|---|---|
| OEE runtime state | `logs/oee_runtime_state.json` | Read/write current runtime state | `oee_state.py`, `runtime.py`, `store.py`, `app.py` | Yes, gradually | Holds active shift, counters, work order state, stations, faults, maintenance, help request, vision state, trend, and recent runtime data. |
| Excel workbook | `logs/MES_Konveyor_Veritabani_*.xlsx` | Runtime append/update projection and audit output | `excel_runtime.py`, `runtime.py`, `mqtt_runtime.py` | Yes, as audit/backfill source | Should not be treated as the first transactional source of truth. It is a compatibility and reporting artifact today. |
| Excel template/masterdata | `MES_Konveyor_Veritabani_Sablonu*.xlsx`, workbook definition sheets | Mostly read, copied when creating runtime workbook | `config.py`, `excel_runtime.py`, `masterdata.py` | Yes, for master data | Operators, stations, fault options, maintenance steps, and defaults can become conceptual master data groups later. |
| Work order JSON | `mes_web/ferp_import/*.json`, `mes_web/work_orders/*.json` | Read/import into runtime state | `config.py`, `runtime.py`, `oee_state.py`, `app.py` | Yes | Import files are the current boundary for work order intake and should be preserved during early phases. |
| FERP labels | `docs/FERP_XLS/ferp_labels.xlsx` | Read-only validation and label registry | `ferp_labels.py`, `app.py`, tests | Yes, for reference/mapping | Label registry can become a reference table later, but the workbook source should remain supported until migration is proven. |
| FERP XLS/XML templates | `docs/FERP_XLS/*` | Read template/source artifacts | `ferp_xls_export.py` | No, not as raw template data | Keep file templates as artifacts. A DB may later track metadata, versions, or export jobs. |
| FERP export outputs | `logs/ferp_exports/pending`, `logs/ferp_exports/examples` | Write generated JSON/XLS export artifacts | `ferp_export.py`, `ferp_xls_export.py`, `app.py` | Yes, as outbox metadata | Exported files should remain file artifacts. PostgreSQL can later track outbox status, file path, timestamp, and source work order. |
| MQTT/ESP32/bridge state | MQTT topics, in-memory dashboard store, selected runtime JSON/workbook records | Mostly live/in-memory; selected events are persisted | `mqtt_runtime.py`, `store.py`, `oee_state.py`, `excel_runtime.py` | Partial | Live connection status and heartbeat are runtime-only. Durable event facts may become DB event records later. |
| Admin/kiosk/technician state | Runtime JSON and Excel workbook | Read/write through API actions | `app.py`, `oee_state.py`, `excel_runtime.py` | Yes, via underlying groups | These screens do not currently have a separate persistence boundary; they mutate runtime state and workbook projections. |
| Test/seed data | `tests`, `.tmp-tests`, sample work order files, template files | Test fixtures and sample inputs | test modules, config env overrides | No, except controlled seed strategy later | Test temp data should not become production persistence. Sample files can inform migration tests. |

## 4. Read/Write Access Points

### `config.py`

Defines path and feature configuration for runtime files, workbook locations, FERP import/export folders, labels, MQTT topics, and Excel behavior. It is the main place where environment variable overrides are resolved.

### `oee_state.py`

Owns the runtime JSON shape and read/write behavior for `logs/oee_runtime_state.json`. It manages active shift state, counters, station state, work orders, faults, maintenance, help requests, quality overrides, vision data, and OEE trend snapshots.

### `runtime.py`

Wires the runtime services together. It starts the Excel sink, OEE runtime state manager, MQTT ingest client, startup work order loading, and watchdog refresh loop.

### `store.py`

Maintains the in-memory dashboard state used by the web layer and WebSocket updates. It reads OEE runtime state snapshots and applies incoming MQTT/status/log data, but most store data is not independently durable.

### `excel_runtime.py`

Writes runtime events and projections to the Excel workbook. It creates or loads the workbook, ensures expected sheets, appends log/event rows, and records work order, OEE, inventory, maintenance, quality, and vision projections.

### `masterdata.py`

Reads workbook/template-based master data such as operators, stations, fault options, maintenance steps, and defaults. It uses the current workbook when available and falls back to the template.

### `ferp_labels.py`

Reads FERP label definitions from `docs/FERP_XLS/ferp_labels.xlsx` or the configured override path. It is used for validation and mapping support.

### `ferp_export.py`

Builds FERP export package payloads and writes JSON export artifacts to the configured pending export directory.

### `ferp_xls_export.py`

Reads FERP XLS/XML template sources and writes seeded examples or pending work order export artifacts. It should remain file-artifact based during early migration phases.

### `mqtt_runtime.py`

Subscribes to MES MQTT topics, updates the dashboard store, records selected logs/events into Excel, and forwards relevant events into the OEE runtime state manager.

### `app.py`

Exposes the HTTP/API surface for dashboard, kiosk, technician, work order, FERP, quality, maintenance, and runtime actions. It delegates persistence to OEE state, Excel runtime, FERP helpers, and configuration paths.

## 5. PostgreSQL Candidate Groups

The following are conceptual PostgreSQL candidate groups. This document intentionally does not define table DDL.

- work orders
- work order events
- production completions
- OEE snapshots/trends
- downtime/fault events
- maintenance records
- quality override records
- vision events/measurements
- device/session metadata
- FERP import batches
- FERP export outbox
- operator/station/error type/maintenance step master data

## 6. Data That Should Not Move Yet

The following data should not be moved to PostgreSQL as source of truth in the first phase:

- live MQTT connection status
- temporary bridge heartbeat
- raw runtime cache
- `.tmp` files
- Docker volume outputs
- exported XLS/JSON artifacts
- test temp data
- FERP artifact files

These groups are either transient, artifact-based, test-only, or safer to track later through metadata rather than by replacing the current file behavior immediately.

## 7. Migration Risks

- dual-write drift between JSON, Excel, file exports, and PostgreSQL
- Excel file lock/corruption during runtime writes
- runtime JSON atomic replace behavior and compatibility with concurrent readers
- MQTT event idempotency and duplicate event handling
- active work order state consistency during shift, station, and package operations
- FERP file format sensitivity and downstream compatibility
- test environment path overrides that assume file-based persistence

## 8. Suggested Incremental Strategy

1. Read-only mirror

   Observe existing runtime writes and mirror selected facts into PostgreSQL without changing the current source of truth. Compare counts, timestamps, active work order state, OEE snapshots, and export records against JSON/Excel/file outputs.

2. Optional DB write with feature flag

   Add optional DB writes behind an explicit feature flag that remains disabled by default. The existing Excel, JSON, and FERP behavior remains authoritative.

3. Feature-flagged DB read

   Move low-risk read models to optional PostgreSQL reads while keeping fallback to the current file-based sources. Use this phase to prove query behavior, test coverage, and rollback paths.

4. Source-of-truth migration

   Promote PostgreSQL to source of truth only after mirror validation, backup/replay tooling, idempotency handling, and operational rollback are proven.

## 9. Areas Not To Touch Yet

The following areas should remain unchanged during this inventory phase:

- MES application runtime behavior
- SQL migrations
- PostgreSQL schema/table DDL
- Excel workbook write flow
- `logs/oee_runtime_state.json`
- FERP import/export folder behavior
- work_orders flow
- MQTT/ESP32 bridge behavior
- Docker service definitions
