@echo off
setlocal

call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

docker compose -f compose.portable.yaml ps
echo.
docker volume ls
endlocal
