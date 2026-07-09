# Station Execution Config Read API 500 Diagnosis

## Summary

Diagnosis result: DIAGNOSED

Root cause class:

```text
A) Wrong DB env / wrong password / wrong host
```

The prior enabled HTTP smoke used a hardcoded DB password value
`change_me_local_only` for the temporary `mes_web_config_api_smoke` container.
That value did not match the DB password used by the currently working
`mes_web` container. With the DB password copied from the working `mes_web`
container without printing it to the terminal, the same temporary smoke pattern
returned `200 OK` for:

```text
GET /api/v2/station-execution/items
```

No API route bug was identified. No code fix was applied.

## Prior Failure

Prior evidence:

```text
docs/runbooks/station_execution_config_read_api_smoke_evidence_20260709.md
```

Prior failure summary:

```text
GET /api/v2/station-execution/items -> 500 INTERNAL_ERROR
GET /api/v2/station-execution/items/raw_box -> 500 INTERNAL_ERROR
GET /api/v2/station-execution/routes?item_code=PACKAGED_PRODUCT -> 500 INTERNAL_ERROR
GET /api/v2/station-execution/route-operations?station_code=ASSEMBLY_01 -> 500 INTERNAL_ERROR
GET /api/v2/stations/ASSEMBLY_01/execution-config -> 500 INTERNAL_ERROR
```

The prior temporary container used:

```text
MES_WEB_DB_PASSWORD=change_me_local_only
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=true
```

## Log Findings

Temporary prior smoke container status:

```text
docker ps -a --filter "name=mes_web_config_api_smoke" -> no rows
```

The prior temporary container was no longer present, so its original error logs
were unavailable.

Current `mes_web` logs showed only expected disabled behavior for the new
feature flag:

```text
GET /api/v2/station-execution/items HTTP/1.1" 503 Service Unavailable
GET /health HTTP/1.1" 200 OK
```

New controlled repro container logs after using the correct DB password showed:

```text
GET /api/v2/station-execution/items HTTP/1.1" 200 OK
GET /health HTTP/1.1" 200 OK
```

No `OperationalError`, `relation does not exist`, `column does not exist`,
`ModuleNotFoundError`, `AttributeError`, or `TypeError` was observed in the
successful repro logs.

## Env Findings

`AppConfig` DB env names:

```text
DB enable: MES_WEB_DB_ENABLED
DB host: MES_WEB_DB_HOST
DB port: MES_WEB_DB_PORT
DB name: MES_WEB_DB_NAME
DB user: MES_WEB_DB_USER
DB password: MES_WEB_DB_PASSWORD
DB fail-open: MES_WEB_DB_FAIL_OPEN
```

`DatabaseConfig.connection_kwargs()` passes:

```text
host
port
dbname
user
sslmode
connect_timeout
password, only when non-empty
```

`database_connection()` does not convert psycopg connection/query exceptions
into `MesqlV2Error`; those raw exceptions are caught by the API route layer as
unexpected exceptions and returned as:

```text
500 INTERNAL_ERROR
```

Current `mes_web` AppConfig findings:

```text
db_enabled True
db_host mes_postgres
db_port 5432
db_name mes
db_user mes
db_password_set True
db_fail_open False
```

Current `mes_web` helper check:

```text
config_db_enabled True
items_count 3
```

Password comparison without printing the password:

```text
current mes_web db_password == 'change_me_local_only' -> False
password_set -> True
password_len -> 14
```

Postgres env values verified without printing the password:

```text
POSTGRES_DB=mes
POSTGRES_USER=mes
```

## Reproduction

Corrected narrow repro used the password from the working `mes_web` container
without printing it:

```powershell
$DbPassword = docker exec mes_web python -c "from mes_web.app import config; print(config.db_password, end='')"
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

Container id:

```text
5b62b5beae4be14f3f3560a627a51a0e04c50ba1a0e3842096ac1dd4bed45a82
```

Health:

```text
GET http://127.0.0.1:18080/health
status = ok
time = 2026-07-09T17:21:19.307+00:00
```

Endpoint repro:

```text
GET http://127.0.0.1:18080/api/v2/station-execution/items
status = 200
ok = true
items_count = 3
```

Direct helper check inside the repro container:

```text
db_enabled True
items_count 3
```

The temporary repro container was stopped after diagnosis:

```text
docker stop mes_web_config_api_smoke -> mes_web_config_api_smoke
```

## Root Cause Classification

Classification:

```text
A) Wrong DB env / wrong password / wrong host
```

Evidence:

```text
Prior smoke hardcoded MES_WEB_DB_PASSWORD=change_me_local_only.
Current working mes_web db_password == 'change_me_local_only' -> False.
Current working mes_web list_items(config) -> items_count 3.
Corrected repro container using current mes_web db_password -> GET /items 200 OK.
```

The broader API route implementation and SQL helpers are not the demonstrated
root cause for the prior `500 INTERNAL_ERROR`.

Secondary finding:

```text
docker/mes/compose.portable.yaml does not pass
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED through to mes_web.
```

That means enabling this new read-only API in the standard portable service
requires an explicit env pass-through change or a controlled temporary
container/run command. No compose change was made in this diagnosis task.

## Fix Applied / Not Applied

Applied:

```text
No code fix.
No config file fix.
No compose change.
No .env change.
```

Reason:

```text
The confirmed cause is smoke environment mismatch, not a route-layer bug.
The allowed code files mes_web/__main__.py and
tests/test_mes_web_station_execution_config_api.py do not need changes.
```

Immediate smoke fix:

```text
Do not hardcode MES_WEB_DB_PASSWORD=change_me_local_only.
Use the DB password from the active local MES environment without printing it,
or add a controlled compose/env pass-through for the new feature flag and run
the normal mes_web service with the already working DB env.
```

## Remaining Action

Recommended next step:

```text
Rerun the HTTP smoke with the correct DB password source and with
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=true.
Only after full enabled HTTP GET smoke, error behavior smoke, no-write baseline
before/after, existing API regression, and Kiosk static GET regression pass,
update CURRENT_STATE.md.
```

Permanent fix options for a later scoped task:

```text
1. Add MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED pass-through to
   docker/mes/compose.portable.yaml.
2. Add an example value to .env.example or the local runbook.
3. Add MES_CONTROL diagnostics for this new feature flag visibility.
```

## Guardrails

- SQL INSERT was not run.
- SQL UPDATE was not run.
- SQL DELETE was not run.
- SQL DROP/TRUNCATE/ALTER/CREATE was not run.
- Seed apply was not run.
- Migration apply was not run.
- POST/PUT/PATCH/DELETE HTTP requests were not run.
- Kiosk action POST was not run.
- Work order mutation was not run.
- Queue mutation was not run.
- MESQL push/pull was not run.
- Operation start/complete lifecycle smoke was not run.
- `docker compose down -v` was not run.
- Docker volume removal was not run.
- Commit/push was not run.
- `.agents/` was not read, modified, staged, deleted, moved, or created.
