@echo off
setlocal

set "MES_DOCKER_ROOT=%~dp0..\.."
for %%I in ("%MES_DOCKER_ROOT%") do set "MES_DOCKER_ROOT=%%~fI"
cd /d "%MES_DOCKER_ROOT%"

call "%~dp0stop_mes_portable.cmd"
if errorlevel 1 exit /b %errorlevel%

call "%~dp0start_mes_portable.cmd"
exit /b %errorlevel%
