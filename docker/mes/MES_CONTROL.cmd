@echo off
setlocal
cd /d "%~dp0"

:menu
cls
echo =========================================
echo MES Docker Control Menu
echo =========================================
echo [ PORTABLE RUNTIME ]
echo 1. Start MES portable
echo 2. Stop MES portable
echo 3. Restart MES portable
echo 4. Status MES portable
echo 5. Build MES portable
echo.
echo [ DIAGNOSTICS ]
echo 6. Verify container code version
echo 7. Show compose build source
echo 8. Show active Docker mounts
echo 9. Show runtime root
echo 10. Show portable data folders
echo 11. Check mes_web health
echo 12. Show mes_web logs
echo 13. Open dashboard
echo 14. Open Adminer
echo.
echo [ MAINTENANCE ]
echo 15. Backup PostgreSQL DB
echo 16. Export portable bundle
echo.
echo [ DEVELOPMENT ]
echo 17. Start MES development
echo 18. Stop MES development
echo 19. Status MES development
echo.
echo 20. Exit
echo =========================================
set /p choice="Seciminiz (1-20): "

if "%choice%"=="1" call "%~dp0launchers\portable\start_mes_portable.cmd"
if "%choice%"=="2" call "%~dp0launchers\portable\stop_mes_portable.cmd"
if "%choice%"=="3" call "%~dp0launchers\portable\restart_mes_portable.cmd"
if "%choice%"=="4" call "%~dp0launchers\portable\status_mes_portable.cmd"
if "%choice%"=="5" call "%~dp0launchers\portable\build_mes_portable.cmd"
if "%choice%"=="6" call "%~dp0launchers\diagnostics\verify_container_code_version.cmd"
if "%choice%"=="7" call "%~dp0launchers\diagnostics\show_compose_build_source.cmd"
if "%choice%"=="8" call "%~dp0launchers\diagnostics\show_active_docker_mounts.cmd"
if "%choice%"=="9" call "%~dp0launchers\diagnostics\show_runtime_root.cmd"
if "%choice%"=="10" call "%~dp0launchers\diagnostics\show_portable_data_folders.cmd"
if "%choice%"=="11" call "%~dp0launchers\diagnostics\check_mes_web_health.cmd"
if "%choice%"=="12" call "%~dp0launchers\diagnostics\show_mes_web_logs.cmd"
if "%choice%"=="13" call "%~dp0launchers\diagnostics\open_dashboard.cmd"
if "%choice%"=="14" call "%~dp0launchers\diagnostics\open_adminer.cmd"
if "%choice%"=="15" call "%~dp0launchers\maintenance\backup_mes_db.cmd"
if "%choice%"=="16" call "%~dp0launchers\maintenance\export_mes_portable_bundle.cmd"
if "%choice%"=="17" call "%~dp0launchers\development\start_mes.cmd"
if "%choice%"=="18" call "%~dp0launchers\development\stop_mes.cmd"
if "%choice%"=="19" call "%~dp0launchers\development\status_mes.cmd"
if "%choice%"=="20" goto end

if not "%choice%"=="1" if not "%choice%"=="2" if not "%choice%"=="3" if not "%choice%"=="4" if not "%choice%"=="5" if not "%choice%"=="6" if not "%choice%"=="7" if not "%choice%"=="8" if not "%choice%"=="9" if not "%choice%"=="10" if not "%choice%"=="11" if not "%choice%"=="12" if not "%choice%"=="13" if not "%choice%"=="14" if not "%choice%"=="15" if not "%choice%"=="16" if not "%choice%"=="17" if not "%choice%"=="18" if not "%choice%"=="19" if not "%choice%"=="20" echo Gecersiz secim: %choice%

echo.
pause
goto menu

:end
endlocal
