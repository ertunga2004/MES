@echo off
setlocal

set "MES_PORTABLE_PATHS_NO_CREATE=1"
call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

docker --version >nul 2>nul
if errorlevel 1 (
    echo Docker CLI bulunamadi.
    exit /b 1
)

docker compose -f compose.portable.yaml config | findstr /I "context: dockerfile: volumes: source: target:"
exit /b %errorlevel%
