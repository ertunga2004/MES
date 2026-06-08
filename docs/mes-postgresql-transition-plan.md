# MES PostgreSQL Transition Plan

## Purpose

This document describes the passive PostgreSQL foundation for Faz 4A. The goal is to prepare configuration, helper modules, and a manual initial migration without changing the current MES source-of-truth behavior.

## Current state

MES Web does not currently use PostgreSQL as source of truth. Runtime data continues to flow through `logs/oee_runtime_state.json`, the Excel workbook, FERP import/export files, work order JSON files, and MQTT-driven in-memory dashboard state.

The Docker setup already provides a PostgreSQL container and Adminer. `MES_WEB_DB_ENABLED=false` remains the safe default.

## Feature flag policy

`MES_WEB_DB_ENABLED` must default to `false`. When it is false:

- MES Web must not open a PostgreSQL connection.
- Missing PostgreSQL drivers must not break application import.
- A stopped PostgreSQL container must not break MES Web startup.
- Excel, JSON, FERP, MQTT, dashboard, kiosk, technician, and OEE behavior must remain unchanged.

The DB helper layer is passive. It is not wired into startup, runtime writes, dual-write, or source-of-truth reads in Faz 4A.

## DB env variables

The passive DB configuration is read from these environment variables:

```text
MES_WEB_DB_ENABLED=false
MES_WEB_DB_HOST=mes_postgres
MES_WEB_DB_PORT=5432
MES_WEB_DB_NAME=mes
MES_WEB_DB_USER=mes
MES_WEB_DB_PASSWORD=
MES_WEB_DB_SSLMODE=disable
MES_WEB_DB_CONNECT_TIMEOUT_SEC=2
MES_WEB_DB_MIRROR_WORK_ORDERS=false
```

In Docker, containers should use `mes_postgres:5432`. Host-side manual access remains `localhost:5433`.

## Initial migration scope

The first migration is stored at:

```text
db/migrations/001_initial_mes_schema.sql
```

It creates the `mes` schema and mirror/outbox-oriented starter tables:

- `mes.work_orders`
- `mes.work_order_events`
- `mes.production_completions`
- `mes.oee_snapshots`
- `mes.downtime_events`
- `mes.maintenance_records`
- `mes.quality_overrides`
- `mes.vision_events`
- `mes.device_sessions`
- `mes.ferp_import_batches`
- `mes.ferp_export_outbox`
- `mes.operators`
- `mes.stations`
- `mes.error_types`
- `mes.maintenance_steps`

The schema intentionally uses JSONB payload and metadata fields. It avoids a tight foreign-key network until the existing JSON, Excel, and FERP data shapes are proven through mirror validation.

## Why DB is passive in Faz 4A

The current runtime has multiple file-based persistence boundaries. Moving directly to PostgreSQL would risk dual-write drift, startup failures, Excel divergence, FERP artifact changes, and MQTT event duplication issues.

Faz 4A only creates infrastructure:

- config parsing
- passive connection helpers
- explicit health check helper
- manual migration script
- documentation

No runtime service calls the DB helper automatically.

## What is not changed

Faz 4A does not change:

- MES application runtime behavior
- `app.py` startup flow
- `runtime.py`
- `oee_state.py`
- `store.py`
- `excel_runtime.py`
- `masterdata.py`
- `mqtt_runtime.py`
- `ferp_export.py`
- `ferp_xls_export.py`
- Docker compose service definitions
- Excel workbook write flow
- `logs/oee_runtime_state.json`
- FERP import/export folder behavior
- work_orders flow
- MQTT/ESP32 bridge behavior

## Manual migration usage

The migration is not applied automatically. It can be reviewed and applied manually against the local PostgreSQL container after explicit approval.

Example manual direction:

```text
psql -h localhost -p 5433 -U mes -d mes -f db/migrations/001_initial_mes_schema.sql
```

Do not add this command to MES Web startup in Faz 4A.

## Manual DB Smoke Test

The manual smoke test script is:

```text
scripts/check_mes_db_connection.py
```

It imports `AppConfig.from_env()` and the passive DB helper layer only. It does not import the FastAPI app, start MES Web, run migrations, or write data.

Disabled/default test:

```powershell
$env:MES_WEB_DB_ENABLED="false"
python scripts/check_mes_db_connection.py
```

Expected disabled output:

```text
DB disabled by MES_WEB_DB_ENABLED=false
```

Enabled connection test from Windows host:

```powershell
$env:MES_WEB_DB_ENABLED="true"
$env:MES_WEB_DB_HOST="localhost"
$env:MES_WEB_DB_PORT="5433"
$env:MES_WEB_DB_NAME="mes"
$env:MES_WEB_DB_USER="mes"
$env:MES_WEB_DB_PASSWORD="change_me_local_only"
python scripts/check_mes_db_connection.py
```

The script runs read-only `SELECT` checks for the current database, current schema, `mes` schema table count, and table names.

Docker network note:

- From inside a Docker container, use host `mes_postgres` and port `5432`.
- From Windows host, use host `localhost` and port `5433`.

## OEE Runtime State Dry-Run Analysis

The dry-run analyzer script is:

```text
scripts/analyze_oee_runtime_state_for_db.py
```

It reads the current OEE runtime JSON state and prints a PostgreSQL candidate mapping report for:

- `mes.work_orders`
- `mes.work_order_events`
- `mes.production_completions`
- `mes.oee_snapshots`
- `mes.downtime_events`
- `mes.maintenance_records`
- `mes.quality_overrides`
- `mes.vision_events`
- `mes.device_sessions`

The script does not connect to PostgreSQL, does not import the FastAPI app, does not start MES Web, does not write files, and does not execute `INSERT`, `UPDATE`, or `DELETE`.

Example command:

```powershell
python scripts/analyze_oee_runtime_state_for_db.py --state-file logs/oee_runtime_state.json
```

Optional JSON output:

```powershell
python scripts/analyze_oee_runtime_state_for_db.py --state-file logs/oee_runtime_state.json --json
```

The report includes top-level runtime JSON keys, source JSON paths, estimated record counts, candidate natural keys/external references, payload fields, suspicious or missing fields, and risk notes.

This report is input for the next read-only mirror design phase. It is not a migration runner and it does not write data to PostgreSQL.

## Manual Work Orders Mirror

The manual work orders mirror script is:

```text
scripts/mirror_work_orders_to_db.py
```

It reads `workOrders.ordersById` from the OEE runtime state JSON and prepares rows for `mes.work_orders`. It is not connected to MES runtime, does not import or start the FastAPI app, and does not change Excel, JSON, FERP, MQTT, or dashboard behavior.

Default mode is dry-run. Dry-run does not open a DB connection and does not write data:

```powershell
python scripts/mirror_work_orders_to_db.py --state-file "C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs\oee_runtime_state.json"
```

To write to PostgreSQL, both `--apply` and `MES_WEB_DB_ENABLED=true` are required:

```powershell
$env:MES_WEB_DB_ENABLED="true"
$env:MES_WEB_DB_HOST="localhost"
$env:MES_WEB_DB_PORT="5433"
$env:MES_WEB_DB_NAME="mes"
$env:MES_WEB_DB_USER="mes"
$env:MES_WEB_DB_PASSWORD="change_me_local_only"
python scripts/mirror_work_orders_to_db.py --state-file "C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs\oee_runtime_state.json" --apply
```

The script writes only to `mes.work_orders` and uses the runtime `order_id` or `ordersById` key as the idempotent external reference. It does not write to work order events, OEE snapshots, FERP outbox, or any other table. It does not make PostgreSQL source of truth.

DB verification after an approved apply:

```powershell
docker exec -i mes_postgres psql -U mes -d mes -c "SELECT count(*) FROM mes.work_orders;"
docker exec -i mes_postgres psql -U mes -d mes -c "SELECT work_order_pk, external_ref, source_system, source_file, created_at, updated_at FROM mes.work_orders ORDER BY created_at DESC LIMIT 10;"
```

The migration uses `work_order_pk` as the primary key column. Do not use destructive SQL for rollback. Before manual cleanup or correction, take a PostgreSQL backup and review the affected rows.

## Work Orders Mirror Verification

The read-only work orders mirror verification script is:

```text
scripts/verify_work_orders_db_mirror.py
```

It compares runtime JSON `workOrders.ordersById` records with PostgreSQL `mes.work_orders` mirror rows by `external_ref`. It does not change runtime source-of-truth behavior, does not write to PostgreSQL, and does not execute `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `DROP`, or `ALTER`.

The script requires `MES_WEB_DB_ENABLED=true` because it must connect to PostgreSQL for read-only verification. If the flag is false, it exits without opening a DB connection:

```text
DB verification requires MES_WEB_DB_ENABLED=true
```

Example one-off Docker verification from the MES Docker network:

```powershell
docker run --rm `
  --network mes_net `
  -v "C:\Users\ertun\Documents\.CODE\codex\MES_sql_inventory:/work" `
  -v "C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs:/runtime_logs:ro" `
  -w /work `
  -e MES_WEB_DB_ENABLED=true `
  -e MES_WEB_DB_HOST=mes_postgres `
  -e MES_WEB_DB_PORT=5432 `
  -e MES_WEB_DB_NAME=mes `
  -e MES_WEB_DB_USER=mes `
  -e MES_WEB_DB_PASSWORD=change_me_local_only `
  python:3.12-slim `
  sh -lc "python -m pip install 'psycopg[binary]<4.0,>=3.2' && python scripts/verify_work_orders_db_mirror.py --state-file /runtime_logs/oee_runtime_state.json"
```

Expected success case after Faz 4E:

- JSON count = 6
- DB count = 6
- `missing_in_db` = 0
- `extra_in_db` = 0
- `changed_or_suspicious` = 0

This verification is the basis for the next read-only mirror validation phase. PostgreSQL still remains a mirror, not MES source of truth.

## Optional Runtime Work Orders Mirror

Faz 4H adds an optional runtime mirror write hook for `mes.work_orders`. It remains disabled by default and requires both flags to be true:

```text
MES_WEB_DB_ENABLED=true
MES_WEB_DB_MIRROR_WORK_ORDERS=true
```

If either flag is false, MES Web does not attempt a runtime work orders DB connection. The safe default remains:

```text
MES_WEB_DB_ENABLED=false
MES_WEB_DB_MIRROR_WORK_ORDERS=false
```

The runtime hook is attached after the existing work order runtime sync path. It does not replace or change JSON, Excel, FERP, or MQTT behavior. PostgreSQL remains a mirror only; MES Web does not read work orders from PostgreSQL and PostgreSQL is not source of truth.

The helper writes only to:

```text
mes.work_orders
```

It uses idempotent upsert by runtime `order_id` / `external_ref`, stores the raw work order payload as JSONB, and updates `updated_at` on repeated mirror attempts. It does not write to work order events, OEE snapshots, FERP outbox, or any other table.

Runtime safety policy:

- DB disabled means no-op.
- Mirror flag disabled means no-op.
- Missing or empty `workOrders.ordersById` means no-op.
- DB connection/write failure is caught and logged.
- Endpoint responses and existing runtime writes must not fail because of mirror errors.

Rollback is flag-based: set `MES_WEB_DB_MIRROR_WORK_ORDERS=false` or `MES_WEB_DB_ENABLED=false`. Existing JSON, Excel, FERP, and MQTT behavior continues unchanged. Mirror rows may remain in PostgreSQL as passive data; normal rollback does not require deleting DB rows.

## Rollback plan

Rollback is file-level:

- remove `mes_web/db/`
- remove `db/migrations/001_initial_mes_schema.sql`
- remove `docs/mes-postgresql-transition-plan.md`
- remove DB fields from `mes_web/config.py`
- remove `psycopg[binary]<4.0,>=3.2` from requirements files

Because no runtime DB call is wired in, rollback does not require changing Excel, JSON, FERP, MQTT, or Docker compose behavior.

## Next phases

1. Read-only mirror

   Mirror selected runtime facts into PostgreSQL while keeping JSON, Excel, and FERP as the active behavior.

2. Optional DB write

   Add feature-flagged DB writes with validation and fallback. Keep the flag disabled by default.

3. Feature-flagged DB read

   Move selected low-risk read models behind feature flags with file-based fallback.

4. Source-of-truth migration

   Promote PostgreSQL only after mirror comparison, backup/replay tooling, idempotency rules, and rollback paths are proven.
