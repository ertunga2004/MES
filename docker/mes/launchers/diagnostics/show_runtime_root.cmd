@echo off
setlocal

set "MES_PORTABLE_PATHS_NO_CREATE=1"
call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%

echo MES_REPO_ROOT=%MES_REPO_ROOT%
echo MES_DOCKER_CONTROL_ROOT=%MES_DOCKER_CONTROL_ROOT%
echo MES_PORTABLE_RUNTIME_ROOT=%MES_PORTABLE_RUNTIME_ROOT%
exit /b 0
