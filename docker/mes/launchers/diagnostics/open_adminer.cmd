@echo off
setlocal

set "MES_PORTABLE_PATHS_NO_CREATE=1"
call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

set "ADMINER_PORT=8082"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$raw = Get-Content -Raw -LiteralPath 'compose.portable.yaml'; if ($raw -match '(?ms)mes_adminer:.*?ports:.*?([0-9]+):8080') { $matches[1] }"`) do set "ADMINER_PORT=%%P"

start "" "http://127.0.0.1:%ADMINER_PORT%"
echo Adminer aciliyor: http://127.0.0.1:%ADMINER_PORT%
exit /b 0
