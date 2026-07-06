@echo off
setlocal

call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

docker compose -f compose.portable.yaml build mes_web
if errorlevel 1 exit /b %errorlevel%

echo.
echo Portable MES image hazir: mes_web_portable:latest
echo Portable modu baslatmak icin: start_mes_portable.cmd
endlocal
