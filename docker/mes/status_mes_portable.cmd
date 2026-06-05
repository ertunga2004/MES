@echo off
setlocal
cd /d "%~dp0"

docker compose -f compose.portable.yaml ps
echo.
docker volume ls
endlocal
