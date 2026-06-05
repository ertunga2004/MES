@echo off
setlocal
cd /d "%~dp0"

docker compose -f compose.portable.yaml down
exit /b %errorlevel%
