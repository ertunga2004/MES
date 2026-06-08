@echo off
setlocal

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"

call "%~dp0sync_mes_source.cmd"
if errorlevel 1 exit /b %errorlevel%

docker compose -f compose.portable.yaml build mes_web
if errorlevel 1 exit /b %errorlevel%

echo.
echo Portable MES image hazir: mes_web_portable:latest
echo Portable modu baslatmak icin: start_mes_portable.cmd
endlocal
