@echo off
setlocal EnableDelayedExpansion

set "MES_PORTABLE_PATHS_NO_CREATE=1"
call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

docker version >nul 2>nul
if errorlevel 1 (
    echo Docker calismiyor veya docker komutu erisilemiyor.
    exit /b 1
)

for %%C in (mes_web mes_postgres mes_adminer) do (
    echo.
    echo [%%C]
    docker inspect %%C >nul 2>nul
    if errorlevel 1 (
        echo Container bulunamadi.
    ) else (
        docker inspect -f "{{range .Mounts}}{{println .Source .Destination}}{{end}}" %%C
    )
)
exit /b 0
