# Station Execution Config Read API Smoke Evidence

## Summary

Result: PASS

Station execution config read-only API HTTP smoke was rerun with the correct DB
password source. The temporary enabled smoke container copied the DB password
from the active `mes_web` config without printing it to the terminal.

The new read-only GET endpoints returned the expected seeded station execution
config data, error behavior matched the route contract, no-write baseline counts
were unchanged before/after smoke, and existing default-disabled API and Kiosk
static GET regressions passed.

## Files / Commit

- Implementation commit: `116ef77 "feat: add station execution config read api"`
- Changed implementation files in the commit:
  - `mes_web/__main__.py`
  - `tests/test_mes_web_station_execution_config_api.py`
- Smoke evidence:
  - `docs/runbooks/station_execution_config_read_api_smoke_evidence_20260709.md`
- Diagnosis evidence:
  - `docs/runbooks/station_execution_config_read_api_500_diagnosis_20260709.md`

Precheck:

```text
git status -sb:
## main...origin/main
?? docs/runbooks/station_execution_config_read_api_500_diagnosis_20260709.md
?? docs/runbooks/station_execution_config_read_api_smoke_evidence_20260709.md

implementation files uncommitted: no
mes_web\__main__.py: exists
tests\test_mes_web_station_execution_config_api.py: exists
```

## Prior Failure and Diagnosis

Prior enabled smoke failed because the temporary smoke container used the wrong
DB password:

```text
MES_WEB_DB_PASSWORD=change_me_local_only
```

Diagnosis file:

```text
docs/runbooks/station_execution_config_read_api_500_diagnosis_20260709.md
```

Diagnosis result:

```text
Root cause class: A) Wrong DB env / wrong password / wrong host
```

Corrected rerun used the DB password from the active `mes_web` config without
printing it:

```powershell
$DbPassword = docker exec mes_web python -c "from mes_web.app import config; print(config.db_password, end='')"
```

No API code bug was identified.

## Unit Regression

Command:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_station_execution_config_api tests.test_mes_web_station_location_api tests.test_mes_web_mesql_v2
```

Result:

```text
Ran 77 tests in 0.976s
OK
```

## Corrected Feature Flag Enabled Setup

Active `mes_web` DB config check:

```text
db_enabled True
db_host mes_postgres
db_port 5432
db_name mes
db_user mes
db_password_set True
db_fail_open False
```

Active `mes_web` helper check:

```text
items_count 3
```

No previous temporary smoke container existed before rerun:

```text
docker ps -a --filter name=mes_web_config_api_smoke -> no rows
```

Temporary enabled read-only smoke container:

```powershell
docker run -d --rm --name mes_web_config_api_smoke --network mes_net -p 18080:8080 `
  -e MES_WEB_HOST=0.0.0.0 `
  -e MES_WEB_PORT=8080 `
  -e MES_WEB_DB_ENABLED=true `
  -e MES_WEB_DB_HOST=mes_postgres `
  -e MES_WEB_DB_PORT=5432 `
  -e MES_WEB_DB_NAME=mes `
  -e MES_WEB_DB_USER=mes `
  -e MES_WEB_DB_PASSWORD="$DbPassword" `
  -e MES_WEB_DB_FAIL_OPEN=false `
  -e MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=true `
  mes_web_portable:latest
```

Temporary container id:

```text
4ac1158eb508657cbd648006c0cf59e2b0ac5a0330c2cd6ed515dd4765bbf087
```

Temporary container health:

```text
status = ok
time = 2026-07-09T17:30:07.006+00:00
```

## Feature Flag Disabled Smoke

The normal `mes_web:8080` service retained default-disabled behavior for the
new feature flag:

```text
GET http://127.0.0.1:8080/api/v2/station-execution/items
status = 503
detail = STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED
```

## Enabled HTTP GET Smoke

Base URL:

```text
http://127.0.0.1:18080
```

Items:

```text
GET /api/v2/station-execution/items
status = 200
ok = true
count = 3
item_codes = PACKAGED_PRODUCT, RAW_BOX, COLOR_CLASSIFIED_BOX
```

Get item:

```text
GET /api/v2/station-execution/items/raw_box
status = 200
item.item_code = RAW_BOX
```

Routes:

```text
GET /api/v2/station-execution/routes?item_code=PACKAGED_PRODUCT
status = 200
ROUTE_BOX_PACKAGING_V1 exists = True
```

Get route:

```text
GET /api/v2/station-execution/routes/route_box_packaging_v1?version=1
status = 200
route.route_code = ROUTE_BOX_PACKAGING_V1
route.version = 1
```

Route operations:

```text
GET /api/v2/station-execution/route-operations?station_code=ASSEMBLY_01
ASSEMBLY_01 count = 1

GET /api/v2/station-execution/route-operations?station_code=PACKAGING_01
PACKAGING_01 count = 1
```

Get route operation:

```text
GET /api/v2/station-execution/route-operations/route_box_packaging_v1_op10
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP10

GET /api/v2/station-execution/route-operations/route_box_packaging_v1_op20
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP20
```

Station event sources:

```text
GET /api/v2/stations/ASSEMBLY_01/execution-event-sources
ASSEMBLY_01 count = 3

GET /api/v2/stations/PACKAGING_01/execution-event-sources
PACKAGING_01 count = 1
```

Operation steps:

```text
GET /api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP10/steps
OP10 count = 3

GET /api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP20/steps
OP20 count = 2
```

Route operation aggregate config:

```text
GET /api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP10/config
validation:
missing_items=0
missing_station=0
missing_event_sources=0
invalid_step_source_refs=0
invalid_auto_mode_refs=0

GET /api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP20/config
validation:
missing_items=0
missing_station=0
missing_event_sources=0
invalid_step_source_refs=0
invalid_auto_mode_refs=0
```

Station execution aggregate config:

```text
GET /api/v2/stations/ASSEMBLY_01/execution-config
route_operations count = 1
missing_station warnings = 0

GET /api/v2/stations/PACKAGING_01/execution-config
route_operations count = 1
missing_station warnings = 0
```

## Error Behavior Smoke

Invalid `active_only`:

```text
GET /api/v2/station-execution/items?active_only=maybe
status = 400
detail = INVALID_QUERY_PARAM
```

Invalid `version`:

```text
GET /api/v2/station-execution/routes/ROUTE_BOX_PACKAGING_V1?version=0
status = 400
detail = INVALID_QUERY_PARAM
```

Missing item:

```text
GET /api/v2/station-execution/items/DOES_NOT_EXIST
status = 404
detail = ITEM_NOT_FOUND
```

Missing route operation:

```text
GET /api/v2/station-execution/route-operations/DOES_NOT_EXIST
status = 404
detail = ROUTE_OPERATION_NOT_FOUND
```

## No-Write Baseline Check

Before smoke:

```text
items=3
process_routes=1
route_operations=2
station_event_sources=4
operation_steps=5
work_order_operation_execution_state=0
work_order_operation_steps=0
operation_events=0
operation_approvals=0
production_flow_events=0
locations=8
active_station_location_bindings=8
```

After smoke:

```text
items=3
process_routes=1
route_operations=2
station_event_sources=4
operation_steps=5
work_order_operation_execution_state=0
work_order_operation_steps=0
operation_events=0
operation_approvals=0
production_flow_events=0
locations=8
active_station_location_bindings=8
```

Result:

```text
before/after counts identical = true
runtime/event/flow tables remained 0 = true
locations = 8
active_station_location_bindings = 8
```

## Existing API / Kiosk Regression

Station/location default-disabled behavior:

```text
GET http://127.0.0.1:8080/api/v2/locations
status = 503
detail = STATION_LOCATION_READ_MODEL_DISABLED
```

Kiosk static GET regression:

```text
GET /kiosk -> 200
GET /static/kiosk.js -> 200
GET /static/kiosk.css -> 200
```

## Temporary Container Cleanup

The temporary container was stopped after smoke:

```text
docker stop mes_web_config_api_smoke -> mes_web_config_api_smoke
```

Because the container was started with `--rm`, it was removed after stop.

Cleanup verification:

```text
docker ps -a --filter name=mes_web_config_api_smoke -> no rows
```

## Guardrails

- SQL INSERT was not run.
- SQL UPDATE was not run.
- SQL DELETE was not run.
- SQL DROP/TRUNCATE/ALTER/CREATE was not run.
- Seed apply was not run.
- Migration apply was not run.
- API implementation was not changed.
- Python/API/JS/HTML/CSS code was not changed.
- Kiosk implementation was not changed.
- Runtime engine implementation was not changed.
- IoT adapter implementation was not changed.
- OEE/KPI implementation was not changed.
- Inventory movement/balance implementation was not changed.
- MESQL push/pull was not run.
- Operation start/complete lifecycle smoke was not run.
- POST/PUT/PATCH/DELETE HTTP requests were not run.
- Kiosk action POST was not run.
- Work order create/change was not run.
- Queue mutation was not run.
- `docker compose down -v` was not run.
- Docker volume removal was not run.
- Commit/push was not run.
- `.agents/` was not read, modified, staged, deleted, moved, or created.

## Result

PASS
