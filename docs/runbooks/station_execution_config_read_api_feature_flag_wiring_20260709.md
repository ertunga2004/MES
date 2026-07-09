# Station Execution Config Read API Feature Flag Wiring

## Summary

Result: PASS

This change is not an API implementation. It is not a database migration. It
only makes the existing station execution config read-only API feature flag
available to the portable `mes_web` container through normal Docker environment
pass-through.

Default behavior remains disabled:

```text
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=false
```

## Motivation

Station execution config read-only API implementation and corrected local HTTP
smoke passed. During the smoke work, the standard portable `mes_web` service did
not receive `MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED`, so an
extra temporary smoke container was needed for enabled API validation.

This wiring lets future portable runs enable the read-only API through `.env` or
host environment without changing Python code or compose behavior unrelated to
environment pass-through.

## Files Changed

- `docker/mes/compose.portable.yaml`
- `docker/mes/.env.example`
- `docs/runbooks/station_execution_config_read_api_feature_flag_wiring_20260709.md`

Not changed:

- `.env`
- `mes_web/__main__.py`
- `mes_web/db/mesql_v2.py`
- `docs/architecture/CURRENT_STATE.md`
- Kiosk files
- migration/seed files

## Compose Pass-Through

Added under `mes_web.environment`:

```yaml
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED: ${MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED:-false}
```

Behavior:

```text
Default: false
Enabled when .env or host env sets MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=true
```

Unchanged:

```text
DB password behavior
ports
volumes
networks
image/build context
restart policy
existing station/location feature flag behavior
```

## Example Env

`docker/mes/.env.example` now documents:

```text
# Enables read-only station execution config API endpoints. Default: false.
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=false
```

The real `.env` file was not changed.

## MES_CONTROL Diagnostic

`docker/mes/MES_CONTROL.cmd` was inspected. It is a menu dispatcher and does not
directly render feature flag diagnostic output. Diagnostic implementation lives
under launcher scripts, which were outside this task's allowed change scope.

No `MES_CONTROL.cmd` change was made.

## Validation

Static validation:

```text
git diff --check -- docker/mes/compose.portable.yaml docker/mes/.env.example docs/runbooks/station_execution_config_read_api_feature_flag_wiring_20260709.md
PASS
```

Compose render validation:

```text
docker-compose -f docker\mes\compose.portable.yaml config
PASS
```

Rendered `mes_web.environment` includes:

```text
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED: "false"
```

Note:

```text
The compose render command emitted a Docker config access warning for
C:\Users\ertun\.docker\config.json, but returned exit code 0 and rendered the
compose configuration successfully.
```

## Not Performed

- DB connection was not opened for this task.
- `psql` was not run.
- Seed apply was not run.
- Migration apply was not run.
- Container restart was not run.
- HTTP smoke was not run.
- Runtime engine implementation was not changed.
- Kiosk implementation was not changed.
- MESQL push/pull was not run.
- OEE/KPI implementation was not changed.
- IoT adapter implementation was not changed.

## Result

PASS
