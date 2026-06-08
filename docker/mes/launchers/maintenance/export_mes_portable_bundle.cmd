@echo off
setlocal EnableDelayedExpansion

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"

if not exist "exports" mkdir "exports"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "STAMP=%%i"
set "IMAGE_TAR=exports\mes_portable_images_%STAMP%.tar"
set "NOTES_FILE=exports\mes_portable_restore_%STAMP%.txt"

docker image inspect mes_web_portable:latest >nul 2>nul
if errorlevel 1 (
    echo Portable MES image bulunamadi. Once build_mes_portable.cmd calistiriliyor.
    call "%MES_DOCKER_ROOT%\launchers\portable\build_mes_portable.cmd"
    if errorlevel 1 exit /b %errorlevel%
)

echo PostgreSQL backup deneniyor.
call "%MES_DOCKER_ROOT%\launchers\maintenance\backup_mes_db.cmd"
if errorlevel 1 (
    echo UYARI: PostgreSQL backup alinamadi. Container calismiyor olabilir.
    echo Image export devam edecek.
)

set "IMAGES=mes_web_portable:latest"
docker image inspect postgres:16-alpine >nul 2>nul
if not errorlevel 1 set "IMAGES=!IMAGES! postgres:16-alpine"
docker image inspect adminer:4 >nul 2>nul
if not errorlevel 1 set "IMAGES=!IMAGES! adminer:4"

echo Docker image export hazirlaniyor:
echo !IMAGES!
docker save -o "%IMAGE_TAR%" !IMAGES!
if errorlevel 1 exit /b %errorlevel%

(
    echo MES Portable Restore Notes
    echo Tarih: %STAMP%
    echo.
    echo 1. Yeni PC'de Docker Desktop ve WSL 2 kur.
    echo 2. Bu .DOCKER\MES klasorunu yeni PC'ye kopyala.
    echo 3. Image tar dosyasini yukle:
    echo    docker load -i %IMAGE_TAR%
    echo 4. Portable modu baslat:
    echo    start_mes_portable.cmd
    echo 5. Gerekirse data\db_backups altindaki SQL backup dosyasini PostgreSQL'e restore et.
    echo.
    echo Not: PostgreSQL verisi Docker image icinde degildir. DB tasima icin SQL backup kullan.
) > "%NOTES_FILE%"

echo.
echo Portable image export yazildi: %IMAGE_TAR%
echo Restore notu yazildi       : %NOTES_FILE%
endlocal
