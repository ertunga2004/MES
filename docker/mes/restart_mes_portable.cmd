@echo off
setlocal
cd /d "%~dp0"

call "%~dp0stop_mes_portable.cmd"
if errorlevel 1 exit /b %errorlevel%

call "%~dp0start_mes_portable.cmd"
exit /b %errorlevel%
