@echo off
setlocal
cd /d "%~dp0"

docker compose restart
if errorlevel 1 exit /b %errorlevel%

docker compose ps
endlocal
