@echo off
setlocal
cd /d "%~dp0"

call "%~dp0sync_mes_source.cmd"
if errorlevel 1 exit /b %errorlevel%

docker compose -f compose.portable.yaml build mes_web
if errorlevel 1 exit /b %errorlevel%

echo.
echo Portable MES image hazir: mes_web_portable:latest
echo Portable modu baslatmak icin: start_mes_portable.cmd
endlocal
