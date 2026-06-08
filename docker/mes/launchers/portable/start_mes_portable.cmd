@echo off
setlocal

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"

echo Portable MES modu baslatiliyor.
echo Kullanilacak portlar:
echo   MES Web    : http://127.0.0.1:8080
echo   Adminer    : http://127.0.0.1:8082
echo   PostgreSQL : localhost:5433
echo.
echo Not: 8080 portunu kullanan Faz 1 veya manuel MES Web calisiyorsa once durdurulmalidir.
echo.

docker compose -f compose.portable.yaml up -d
if errorlevel 1 exit /b %errorlevel%

docker compose -f compose.portable.yaml ps
echo.
echo MES Web : http://127.0.0.1:8080
echo Adminer : http://127.0.0.1:8082
endlocal
