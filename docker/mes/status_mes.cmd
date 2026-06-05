@echo off
setlocal
cd /d "%~dp0"

docker compose ps
echo.
docker compose logs --tail=80 mes_web mes_postgres mes_adminer
endlocal
