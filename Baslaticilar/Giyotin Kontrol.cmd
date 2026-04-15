@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%ps1\Start-MesApp.ps1" -App giyotin_kontrol
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Giyotin Kontrol kapandi. Pencereyi kapatmak icin bir tusa basin.
) else (
  echo Giyotin Kontrol launcher failed with exit code %EXIT_CODE%.
  echo Pencereyi kapatmak icin bir tusa basin.
)
pause >nul

exit /b %EXIT_CODE%
