@echo off
setlocal

powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 5; $r | ConvertTo-Json -Depth 5 } catch { Write-Host 'mes_web health kontrolu basarisiz:' $_.Exception.Message; exit 1 }"
exit /b %errorlevel%
