@echo off
setlocal
cd /d "%~dp0"

:menu
cls
echo =========================================
echo MES Docker Control Menu
echo =========================================
echo [ PORTABLE MODE ]
echo 1. Start MES portable
echo 2. Stop MES portable
echo 3. Restart MES portable
echo 4. Status MES portable
echo 5. Build MES portable
echo.
echo [ MAINTENANCE ]
echo 6. Backup PostgreSQL DB
echo 7. Export portable bundle
echo.
echo [ DEVELOPMENT MODE ]
echo 8. Start MES development
echo 9. Stop MES development
echo 10. Status MES development
echo.
echo 11. Exit
echo =========================================
set /p choice="Seciminiz (1-11): "

if "%choice%"=="1" call "%~dp0launchers\portable\start_mes_portable.cmd"
if "%choice%"=="2" call "%~dp0launchers\portable\stop_mes_portable.cmd"
if "%choice%"=="3" call "%~dp0launchers\portable\restart_mes_portable.cmd"
if "%choice%"=="4" call "%~dp0launchers\portable\status_mes_portable.cmd"
if "%choice%"=="5" call "%~dp0launchers\portable\build_mes_portable.cmd"
if "%choice%"=="6" call "%~dp0launchers\maintenance\backup_mes_db.cmd"
if "%choice%"=="7" call "%~dp0launchers\maintenance\export_mes_portable_bundle.cmd"
if "%choice%"=="8" call "%~dp0launchers\development\start_mes.cmd"
if "%choice%"=="9" call "%~dp0launchers\development\stop_mes.cmd"
if "%choice%"=="10" call "%~dp0launchers\development\status_mes.cmd"
if "%choice%"=="11" goto end

echo.
pause
goto menu

:end
endlocal
