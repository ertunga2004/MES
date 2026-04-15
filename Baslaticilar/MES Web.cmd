@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%ps1\Start-MesApp.ps1" -App mes_web
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo MES Web launcher failed with exit code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
