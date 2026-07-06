@echo off
setlocal

set "MES_PORTABLE_PATHS_NO_CREATE=1"
call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%

call :check_folder "%MES_PORTABLE_RUNTIME_ROOT%\data\logs"
call :check_folder "%MES_PORTABLE_RUNTIME_ROOT%\data\work_orders"
call :check_folder "%MES_PORTABLE_RUNTIME_ROOT%\data\db_backups"
exit /b 0

:check_folder
if exist "%~1" (
    echo OK      %~1
) else (
    echo MISSING %~1
)
exit /b 0
