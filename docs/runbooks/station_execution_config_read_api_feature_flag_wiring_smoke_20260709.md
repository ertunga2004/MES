# Station Execution Config Read API Feature Flag Wiring Smoke

## Summary

Result: PASS

Portable compose pass-through for
`MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED` was verified on the
normal `mes_web:8080` service without using a temporary smoke container.

Setting the host env value to `true` and recreating only `mes_web` enabled the
read-only station execution config API. Removing the host env value and
recreating only `mes_web` restored default disabled behavior.

## Precheck

Git log included:

```text
809c12a chore: wire station execution config api feature flag
03cfd2e "docs: record station execution config api smoke"
116ef77 "feat: add station execution config read api"
```

Pre-smoke worktree:

```text
## main...origin/main [ahead 1]
```

## Enabled Pass-Through Setup

Command:

```powershell
$env:MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED="true"
docker-compose -f docker\mes\compose.portable.yaml up -d --no-deps mes_web
```

Result:

```text
mes_web recreated and started
docker compose down -v not run
volume removal not run
```

Health:

```text
status = ok
time = 2026-07-09T17:45:48.481+00:00
```

## Enabled Endpoint Smoke

Base URL:

```text
http://127.0.0.1:8080
```

Items endpoint:

```text
GET /api/v2/station-execution/items
items_count = 3
item_codes = PACKAGED_PRODUCT, RAW_BOX, COLOR_CLASSIFIED_BOX
```

Route operations endpoint:

```text
GET /api/v2/station-execution/route-operations?station_code=ASSEMBLY_01
ASSEMBLY_01 route operation count = 1
```

Station execution config endpoint:

```text
GET /api/v2/stations/ASSEMBLY_01/execution-config
ASSEMBLY_01 execution config route_operations count = 1
```

## Disabled Restore

Command:

```powershell
Remove-Item Env:\MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED -ErrorAction SilentlyContinue
docker-compose -f docker\mes\compose.portable.yaml up -d --no-deps mes_web
```

Result:

```text
mes_web recreated and started
default disabled behavior restored
```

Disabled endpoint check:

```text
GET /api/v2/station-execution/items
status = 503
detail = STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED
```

Post-restore health:

```text
status = ok
time = 2026-07-09T17:46:09.050+00:00
```

## Kiosk Static Regression

```text
GET /kiosk -> 200
GET /static/kiosk.js -> 200
GET /static/kiosk.css -> 200
```

## Files Changed

- `docs/runbooks/station_execution_config_read_api_feature_flag_wiring_smoke_20260709.md`
- `docs/architecture/CURRENT_STATE.md`

## Not Performed

- `docker compose down -v` was not run.
- Docker volume removal was not run.
- DB write was not performed.
- `psql` was not run.
- Seed apply was not run.
- Migration apply was not run.
- POST/PUT/PATCH/DELETE requests were not run.
- Kiosk action POST was not run.
- Runtime engine implementation was not changed.
- IoT adapter implementation was not changed.
- OEE/KPI implementation was not changed.
- MESQL push/pull was not run.
- Operation lifecycle mutation was not performed.
- Work order or queue mutation was not performed.
- Commit/push was not run for this smoke evidence.

## Result

PASS
