@echo off
setlocal

call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%i
set "BACKUP_PATH=%MES_PORTABLE_RUNTIME_ROOT%\data\db_backups\mes_postgres_%STAMP%.sql"

docker compose -f compose.portable.yaml exec -T mes_postgres sh -c "pg_dump -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"" > "%BACKUP_PATH%"
if errorlevel 1 (
    echo PostgreSQL backup basarisiz oldu.
    exit /b 1
)

echo PostgreSQL backup yazildi: %BACKUP_PATH%
endlocal
