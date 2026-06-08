@echo off
setlocal EnableExtensions

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"

if "%MES_SOURCE_ROOT%"=="" set "MES_SOURCE_ROOT=C:\Users\ertun\Documents\.CODE\codex\MES"
if not "%~1"=="" set "MES_SOURCE_ROOT=%~1"

set "SNAPSHOT_ROOT=%MES_DOCKER_ROOT%\app_source"

for %%I in ("%SNAPSHOT_ROOT%") do set "SNAPSHOT_ROOT=%%~fI"
for %%I in ("%MES_DOCKER_ROOT%\app_source") do set "EXPECTED_SNAPSHOT_ROOT=%%~fI"

if /I not "%SNAPSHOT_ROOT%"=="%EXPECTED_SNAPSHOT_ROOT%" (
    echo Guvenlik hatasi: snapshot hedefi beklenen klasor degil.
    echo Hedef: %SNAPSHOT_ROOT%
    exit /b 1
)

if not exist "%MES_SOURCE_ROOT%\mes_web\__main__.py" (
    echo MES kaynak klasoru dogrulanamadi:
    echo %MES_SOURCE_ROOT%
    echo Beklenen dosya yok: mes_web\__main__.py
    exit /b 1
)

if not exist "%SNAPSHOT_ROOT%" mkdir "%SNAPSHOT_ROOT%"

echo MES kaynak snapshot hazirlaniyor.
echo Kaynak : %MES_SOURCE_ROOT%
echo Hedef  : %SNAPSHOT_ROOT%
echo.

robocopy "%MES_SOURCE_ROOT%" "%SNAPSHOT_ROOT%" /MIR /R:2 /W:2 ^
  /XD ".git" ".venv" "venv" "__pycache__" ".pytest_cache" ".mypy_cache" "node_modules" "dist" "build" "logs" ".tmp-tests" "network_reports" "network_backups" ^
  /XF ".env" "*.log" "*.tmp" "*.bak" "*.bak.xlsx" "~$*.xlsx" "*.pyc" "_css_dump.txt" "_current_css.txt" "_node_red_current_summary.json" "_ui_nodes_snapshot.json"

set "ROBOCOPY_EXIT=%ERRORLEVEL%"
if %ROBOCOPY_EXIT% GEQ 8 (
    echo Snapshot kopyalama basarisiz oldu. Robocopy exit code: %ROBOCOPY_EXIT%
    exit /b %ROBOCOPY_EXIT%
)

echo.
echo MES kaynak snapshot tamamlandi: %SNAPSHOT_ROOT%
exit /b 0
