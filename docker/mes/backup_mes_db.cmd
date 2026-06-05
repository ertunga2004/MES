@echo off
setlocal
cd /d "%~dp0"

if not exist "data\db_backups" mkdir "data\db_backups"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%i
set BACKUP_PATH=data\db_backups\mes_postgres_%STAMP%.sql

docker compose exec -T mes_postgres sh -c "pg_dump -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"" > "%BACKUP_PATH%"
if errorlevel 1 (
    echo PostgreSQL backup basarisiz oldu.
    exit /b 1
)

echo PostgreSQL backup yazildi: %BACKUP_PATH%
endlocal
