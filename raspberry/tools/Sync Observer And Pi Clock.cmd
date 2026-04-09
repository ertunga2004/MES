@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%publish_time_sync.ps1"

if not exist "%PS_SCRIPT%" (
  echo Missing PowerShell script:
  echo %PS_SCRIPT%
  echo.
  pause
  exit /b 1
)

echo Sending clock sync for observer and Raspberry Pi...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -ApplySystemClock
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo Clock sync command failed with exit code %EXIT_CODE%.
  pause
  exit /b %EXIT_CODE%
)

echo Clock sync payload sent.
echo If observer is running, it will update its own timestamps and the Pi system clock.
echo.
pause
