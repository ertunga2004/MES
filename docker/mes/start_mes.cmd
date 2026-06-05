@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    echo .env bulunamadi. Varsayilan degerlerle baslatiliyor.
    echo Kalici yerel ayar icin: copy .env.example .env
    echo.
)

docker compose up -d --build
if errorlevel 1 exit /b %errorlevel%

docker compose ps
endlocal
