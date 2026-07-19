# MES Docker Portable Runtime

This folder contains the Docker control files for the local MES prototype.

This README describes the current portable runtime model. It is not a database
migration guide and it does not authorize MESQL push/pull.

## Canonical Layout

```text
Git repo root:
<repo-root>

Docker control root:
<repo-root>\docker\mes

Portable runtime/data root:
<portable-runtime-root>
```

Runtime data folders:

```text
<portable-runtime-root>\data\logs
<portable-runtime-root>\data\work_orders
<portable-runtime-root>\data\db_backups
```

`docker/mes` is the control folder. It contains compose files, Dockerfiles,
launchers, and examples.

`.CODE\.DOCKER\MES` is the portable runtime/data root. Runtime logs, work order
data mounts, and SQL backups belong there, outside the git repo.

`docker/mes/data` is an old runtime location and is not the active target.

## Current Boundary

Local MES DB v2 operation lifecycle is DB-backed and is the local execution
source-of-truth for operation start, complete, successor activation, and
station queue publishing.

This does not remove all legacy/runtime file flows. JSON runtime state, Excel,
and FERP file flows still exist where the application uses them.

MESQL integration is frozen unless explicitly requested. Do not run MESQL
push/pull without explicit approval.

## Portable Build Source

Portable `mes_web` image builds from the repo-root source:

```text
<repo-root>\mes_web
```

Portable Docker build settings:

```text
compose.portable.yaml:
  build.context: ../..
  build.dockerfile: docker/mes/Dockerfile.mes_web.portable

Dockerfile.mes_web.portable:
  COPY mes_web/requirements.txt ...
  COPY mes_web/ /app/mes_web/
```

`app_source/` is not the active portable source-of-truth.

`sync_mes_source.cmd` may remain as a deprecated/internal helper, but it is not
part of the active `build_mes_portable.cmd` flow.

## Services

| Service | Container | Host access | Internal port | Purpose |
|---|---|---:|---:|---|
| `mes_web` | `mes_web` | `http://127.0.0.1:8080` | `8080` | MES Web |
| `mes_postgres` | `mes_postgres` | `localhost:5433` | `5432` | Local PostgreSQL |
| `mes_adminer` | `mes_adminer` | `http://127.0.0.1:8082` | `8080` | Adminer |

Adminer server value:

```text
mes_postgres
```

## MES_CONTROL Menu

Recommended entry point:

```cmd
MES_CONTROL.cmd
```

Menu groups:

```text
[ PORTABLE RUNTIME ]
1. Start MES portable
2. Stop MES portable
3. Restart MES portable
4. Status MES portable
5. Build MES portable

[ DIAGNOSTICS ]
6. Verify container code version
7. Show compose build source
8. Show active Docker mounts
9. Show runtime root
10. Show portable data folders
11. Check mes_web health
12. Show mes_web logs
13. Open dashboard
14. Open Adminer

[ MAINTENANCE ]
15. Backup PostgreSQL DB
16. Export portable bundle

[ DEVELOPMENT ]
17. Start MES development
18. Stop MES development
19. Status MES development

20. Exit
```

Direct launcher scripts remain available under `launchers/`, but daily use
should start from `MES_CONTROL.cmd`.

## Setup

Create a local `.env` from the example if local overrides are needed:

```cmd
copy .env.example .env
```

`.env` can contain the real local DB password. Do not commit it.

`.env.example` must contain example values only.

Key portable runtime value:

```text
MES_PORTABLE_RUNTIME_ROOT=C:/Users/ertun/Documents/.CODE/.DOCKER/MES
```

## Start, Stop, Status, Build

Preferred workflow:

```cmd
MES_CONTROL.cmd
```

Then use the portable runtime menu options.

Direct launcher alternatives:

```cmd
launchers\portable\start_mes_portable.cmd
launchers\portable\stop_mes_portable.cmd
launchers\portable\restart_mes_portable.cmd
launchers\portable\status_mes_portable.cmd
launchers\portable\build_mes_portable.cmd
```

Portable build uses repo-root `mes_web/`; it does not call
`sync_mes_source.cmd`.

## Diagnostics

Use `MES_CONTROL.cmd` diagnostics for routine checks.

Container code version check:

```cmd
docker exec mes_web python -c "from mes_web.db import mesql_v2; sql=getattr(mesql_v2,'SELECT_SUCCESSOR_OPERATION_SQL',''); print('has_successor_sql', bool(sql)); print('orders_by_sequence_operation', 'ORDER BY sequence_no ASC, operation_no ASC' in sql); print('skips_terminal', 'status NOT IN' in sql)"
```

Expected result:

```text
has_successor_sql True
orders_by_sequence_operation True
skips_terminal True
```

Health check:

```text
http://127.0.0.1:8080/health
```

Dashboard:

```text
http://127.0.0.1:8080
```

Adminer:

```text
http://127.0.0.1:8082
```

## Data Locations

Portable bind-mounted runtime data:

```text
%MES_PORTABLE_RUNTIME_ROOT%\data\logs        -> /app/logs
%MES_PORTABLE_RUNTIME_ROOT%\data\work_orders -> /data/work_orders
%MES_PORTABLE_RUNTIME_ROOT%\data\db_backups  -> /backups
```

PostgreSQL database files are stored in the named Docker volume:

```text
mes_postgres_data
```

Do not remove this volume during normal operations.

## Backup

Use the maintenance menu in `MES_CONTROL.cmd`, or run:

```cmd
launchers\maintenance\backup_mes_db.cmd
```

Backups are written under:

```text
<portable-runtime-root>\data\db_backups
```

This backs up PostgreSQL only. It does not replace JSON, Excel, FERP, or other
runtime file flows.

## Local Successor Smoke Reference

Local successor activation has been smoke-verified on real local PostgreSQL:

```text
ASSEMBLY_01 op10 complete
-> PACKAGING_01 op20 queued
-> repeated op10 complete did not create duplicate queue
-> PACKAGING_01 op20 complete
-> work_order completed
```

Detailed smoke notes are in:

```text
docs/runbooks/local_successor_activation_smoke.md
```

## Development and Legacy Notes

Development mode may still use source bind mounts and legacy/runtime file
flows. That is separate from the portable runtime model above.

`sync_mes_source.cmd` and `app_source/` are legacy/deprecated snapshot helpers.
They are not the active portable build chain.

## Guardrails

- Do not commit `.env`.
- Do not add `docker/mes/data__OLD_RUNTIME_QUARANTINE/` to git.
- Do not remove Docker volumes without explicit destructive-operation approval.
- Do not run MESQL push/pull without explicit approval.
- Do not treat `app_source/` as the portable build source-of-truth.
- Do not move or delete the repo root or portable runtime root as part of
  normal operation.
