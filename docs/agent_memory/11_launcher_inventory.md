# Launcher Inventory and Path-Safe Strategy

This document describes the inventory and organizational strategy for the `.cmd` launcher files located in the `docker/mes` directory and its `launchers/` subdirectory.

## Current Strategy: Central Menu & Path-Safe Subdirectories

To keep the `docker/mes` root directory clean, all individual `.cmd` launcher scripts have been moved to the `launchers/` subdirectory, categorized by their purpose (`development`, `portable`, `maintenance`). A single, unified `MES_CONTROL.cmd` file resides in the root to provide an interactive menu for running these scripts.

### Path-Safe Refactoring

Moving the scripts required robust path refactoring to ensure they still function exactly as if they were in the root directory. Every script in the `launchers/` folder calculates the `docker/mes` root dynamically and sets it as the Current Working Directory (CWD).

This is achieved using the following template at the beginning of every moved script:

```bat
@echo off
setlocal

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"
```

This ensures that:
1. `compose.yaml` and `.env` files are found correctly.
2. Cross-script references (e.g., `build_mes_portable.cmd` calling `sync_mes_source.cmd`) use robust paths based on `%MES_DOCKER_ROOT%`.
3. The `app_source/` target in `sync_mes_source.cmd` correctly resolves to `%MES_DOCKER_ROOT%\app_source`, maintaining the integrity of the `Dockerfile.mes_web.portable` build context (`COPY app_source/ /app/`).

## Launcher Inventory

### Root Control Menu
- **`MES_CONTROL.cmd`**: The interactive menu that provides options to execute all the underlying scripts without needing to navigate into the `launchers/` subdirectories.

### Development Group (`launchers/development/`)
These scripts use `compose.yaml` with local bind mounts for live development.
- `start_mes.cmd`: Starts the development containers.
- `stop_mes.cmd`: Stops the development containers.
- `restart_mes.cmd`: Restarts the development containers.
- `status_mes.cmd`: Shows the status and logs of the development containers.

### Portable Group (`launchers/portable/`)
These scripts use `compose.portable.yaml` and rely on a pre-built Docker image.
- `start_mes_portable.cmd`: Starts the portable containers.
- `stop_mes_portable.cmd`: Stops the portable containers.
- `restart_mes_portable.cmd`: Calls `stop_mes_portable.cmd` then `start_mes_portable.cmd`.
- `status_mes_portable.cmd`: Shows portable container statuses and volumes.
- `build_mes_portable.cmd`: Calls `sync_mes_source.cmd` and builds the portable image.
- `sync_mes_source.cmd`: **CRITICAL**. Copies the external MES source code into `%MES_DOCKER_ROOT%\app_source`.

### Maintenance Group (`launchers/maintenance/`)
- `backup_mes_db.cmd`: Creates a `.sql` dump of the PostgreSQL database, saving it to `%MES_DOCKER_ROOT%\data\db_backups\`.
- `export_mes_portable_bundle.cmd`: Calls `build_mes_portable.cmd` and `backup_mes_db.cmd`, then packages everything into a `.tar` bundle in `%MES_DOCKER_ROOT%\exports\`.
