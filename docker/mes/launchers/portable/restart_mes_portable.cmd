@echo off
setlocal

call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

call "%~dp0stop_mes_portable.cmd"
if errorlevel 1 exit /b %errorlevel%

call "%~dp0start_mes_portable.cmd"
exit /b %errorlevel%
