@echo off
setlocal

set "MES_PORTABLE_PATHS_NO_CREATE=1"
call "%~dp0..\common\portable_paths.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%MES_DOCKER_CONTROL_ROOT%"

docker version >nul 2>nul
if errorlevel 1 (
    echo Docker calismiyor veya docker komutu erisilemiyor.
    exit /b 1
)

docker inspect mes_web >nul 2>nul
if errorlevel 1 (
    echo mes_web container bulunamadi.
    exit /b 1
)

for /f "usebackq delims=" %%R in (`docker inspect -f "{{.State.Running}}" mes_web 2^>nul`) do set "MES_WEB_RUNNING=%%R"
if /I not "%MES_WEB_RUNNING%"=="true" (
    echo mes_web container calismiyor.
    exit /b 1
)

docker exec mes_web python -c "from mes_web.db import mesql_v2; sql=getattr(mesql_v2,'SELECT_SUCCESSOR_OPERATION_SQL',''); print('has_successor_sql', bool(sql)); print('orders_by_sequence_operation', 'ORDER BY sequence_no ASC, operation_no ASC' in sql); print('skips_terminal', 'status NOT IN' in sql)"
exit /b %errorlevel%
