@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Start-PreSql.ps1" -Mode Demo
if errorlevel 1 pause
