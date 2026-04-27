@echo off
title EV MODU AKTIFLESTIRICI
color 0B

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
echo         EV MODU AKTIFLESTIRILIYOR
echo ========================================
echo.

echo [1/2] Ethernet IP adresi otomatiğe (DHCP) aliniyor...
netsh interface ipv4 set address name="Ethernet" source=dhcp
netsh interface ipv4 set dnsservers name="Ethernet" source=dhcp

echo [2/2] Internet Paylasimi (ICS) kapatiliyor...
powershell -NoProfile -Command "$NetShare = New-Object -ComObject HNetCfg.HNetShare; foreach($conn in $NetShare.EnumEveryConnection) { $config = $NetShare.INetSharingConfigurationForINetConnection.Invoke($conn); if($config.SharingEnabled -eq $True) { $config.DisableSharing() } }"

echo.
echo Islem tamam! Ethernet kablosunu Kablonet'e baglayip hizli interneti kullanabilirsin.
pause