@echo off
setlocal

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"

if not exist ".env" (
    echo .env bulunamadi. Varsayilan degerlerle baslatiliyor.
    echo Kalici yerel ayar icin: copy .env.example .env
    echo.
)

docker compose up -d --build
if errorlevel 1 exit /b %errorlevel%

docker compose ps
endlocal
