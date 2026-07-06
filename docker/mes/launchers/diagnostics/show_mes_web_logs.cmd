@echo off
setlocal

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

docker logs --tail 100 mes_web
exit /b %errorlevel%
