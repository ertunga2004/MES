@echo off
title MES (ATOLYE) MODU AKTIFLESTIRICI
color 0A

:: Yonetici izinlerini otomatik isteme bloğu
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Yonetici izni gerekiyor, lutfen onay verin...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B
:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )

echo ========================================
echo      MES (ATOLYE) MODU AKTIFLESTIRILIYOR
echo ========================================
echo.

echo [1/2] Ethernet IP adresi 192.168.137.1 olarak sabitleniyor...
netsh interface ipv4 set address name="Ethernet" static 192.168.137.1 255.255.255.0

echo [2/2] Internet Paylasimi (ICS) aciliyor... (Wi-Fi'dan Ethernet'e)
powershell -NoProfile -Command "$NetShare = New-Object -ComObject HNetCfg.HNetShare; $Connections = $NetShare.EnumEveryConnection; foreach($conn in $Connections) { $Props = $NetShare.NetConnectionProps.Invoke($conn); $Config = $NetShare.INetSharingConfigurationForINetConnection.Invoke($conn); if ($Props.Name -eq 'Wi-Fi') { $Config.EnableSharing(0) }; if ($Props.Name -eq 'Ethernet') { $Config.EnableSharing(1) } }"

echo.
echo Islem tamam! TP-Link modemi takabilirsin. ESP32'ler ve mes_web agda hazir!
pause