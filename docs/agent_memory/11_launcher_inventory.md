# Launcher Inventory and NO-MOVE Strategy

This document describes the inventory and organizational strategy for the `.cmd` launcher files located in the `docker/mes` directory.

## Current Strategy: NO-MOVE

The `.cmd` files are kept in the `docker/mes` root folder instead of being grouped into a `launchers/` subdirectory. This **NO-MOVE** strategy was established to avoid critical build failures and cross-script reference breakages.

### Why NO-MOVE?

1. **Docker Build Context Dependency (`app_source/`)**: `sync_mes_source.cmd` copies the MES source code into `docker/mes/app_source`. `Dockerfile.mes_web.portable` uses `COPY app_source/ /app/`, which is relative to the Docker build context (the `docker/mes` root). If `sync_mes_source.cmd` is moved and the path is slightly miscalculated, the portable build will completely fail.
2. **Cross-Script Call Chain**: The portable and export flows are highly interdependent. For example: `export_mes_portable_bundle.cmd` -> `build_mes_portable.cmd` -> `sync_mes_source.cmd` -> `backup_mes_db.cmd`. They use `%~dp0` to reference each other. Moving one requires moving and refactoring the paths for all of them.
3. **Current Working Directory (CWD)**: `compose.yaml` and `.env` expect commands to be run from the `docker/mes` root. Changing the script locations would necessitate robust CWD refactoring (e.g., `cd /d "%~dp0..\.."`).

Keeping them in the root maintains stability and preserves the existing, working user workflow.

## Launcher Inventory

### Development Group
These scripts use `compose.yaml` with local bind mounts for live development.
- `start_mes.cmd`: Starts the development containers (`docker compose up -d --build`).
- `stop_mes.cmd`: Stops the development containers (`docker compose down`).
- `restart_mes.cmd`: Restarts the development containers.
- `status_mes.cmd`: Shows the status and logs of the development containers.

### Portable Group
These scripts use `compose.portable.yaml` and rely on a pre-built Docker image (`mes_web_portable:latest`), simulating a production/deployment environment without live source code bind mounts.
- `start_mes_portable.cmd`: Starts the portable containers.
- `stop_mes_portable.cmd`: Stops the portable containers.
- `restart_mes_portable.cmd`: Restarts the portable containers.
- `status_mes_portable.cmd`: Shows the status and volumes of the portable containers.
- `build_mes_portable.cmd`: Builds the portable Docker image. This calls `sync_mes_source.cmd` first to prepare the build context.

### Internal / Utility Group
These are called by other scripts or are used for specific maintenance tasks.
- `sync_mes_source.cmd`: **CRITICAL**. Copies the external MES source code into the `app_source/` directory for the Docker build context. Do not modify its target path without updating `Dockerfile.mes_web.portable`.
- `backup_mes_db.cmd`: Creates a `.sql` dump of the PostgreSQL database, saving it to `data/db_backups/`.
- `export_mes_portable_bundle.cmd`: Packages the portable Docker image (`.tar`) and the latest database backup into a deployment bundle inside the `exports/` directory.

## Future Path Refactoring

If a future architectural requirement necessitates moving these scripts into a `launchers/` subdirectory, the following pattern **must** be used in every script to safely calculate the `docker/mes` root:

```cmd
@echo off
setlocal
for %%I in ("%~dp0..\..\") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"
```

Furthermore, all cross-script `call` commands must be updated to use absolute paths based on `%MES_DOCKER_ROOT%`, and the `app_source` path logic in `sync_mes_source.cmd` must be carefully verified against the `Dockerfile.mes_web.portable` build context.
