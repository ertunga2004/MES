@echo off
setlocal EnableExtensions

set "MES_DOCKER_CONTROL_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_CONTROL_ROOT%") do set "MES_DOCKER_CONTROL_ROOT=%%~fI"

set "MES_REPO_ROOT=%MES_DOCKER_CONTROL_ROOT%\..\.."
for %%I in ("%MES_REPO_ROOT%") do set "MES_REPO_ROOT=%%~fI"

if "%MES_PORTABLE_RUNTIME_ROOT%"=="" set "MES_PORTABLE_RUNTIME_ROOT=C:\Users\ertun\Documents\.CODE\.DOCKER\MES"
for %%I in ("%MES_PORTABLE_RUNTIME_ROOT%") do set "MES_PORTABLE_RUNTIME_ROOT=%%~fI"

if not "%MES_PORTABLE_PATHS_NO_CREATE%"=="1" (
    if not exist "%MES_PORTABLE_RUNTIME_ROOT%\data\logs" mkdir "%MES_PORTABLE_RUNTIME_ROOT%\data\logs"
    if not exist "%MES_PORTABLE_RUNTIME_ROOT%\data\work_orders" mkdir "%MES_PORTABLE_RUNTIME_ROOT%\data\work_orders"
    if not exist "%MES_PORTABLE_RUNTIME_ROOT%\data\db_backups" mkdir "%MES_PORTABLE_RUNTIME_ROOT%\data\db_backups"
)

endlocal & (
    set "MES_DOCKER_CONTROL_ROOT=%MES_DOCKER_CONTROL_ROOT%"
    set "MES_DOCKER_ROOT=%MES_DOCKER_CONTROL_ROOT%"
    set "MES_REPO_ROOT=%MES_REPO_ROOT%"
    set "MES_PORTABLE_RUNTIME_ROOT=%MES_PORTABLE_RUNTIME_ROOT%"
)
exit /b 0
