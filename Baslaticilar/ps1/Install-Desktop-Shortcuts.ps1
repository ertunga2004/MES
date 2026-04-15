[CmdletBinding()]
param(
    [string]$TargetDir = [Environment]::GetFolderPath("Desktop")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$supportRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcherRoot = Split-Path -Parent $supportRoot

if (-not (Test-Path -LiteralPath $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir | Out-Null
}

$wrappers = Get-ChildItem -LiteralPath $launcherRoot -Filter "*.cmd" |
    Where-Object { $_.Name -ne "Install Desktop Shortcuts.cmd" } |
    Sort-Object Name

if (-not $wrappers) {
    throw "Kisayol olusturulacak .cmd dosyasi bulunamadi."
}

$shell = New-Object -ComObject WScript.Shell

foreach ($wrapper in $wrappers) {
    $shortcutName = "MES - {0}.lnk" -f [System.IO.Path]::GetFileNameWithoutExtension($wrapper.Name)
    $shortcutPath = Join-Path $TargetDir $shortcutName
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $wrapper.FullName
    $shortcut.WorkingDirectory = $launcherRoot
    $shortcut.Description = "MES launcher: {0}" -f [System.IO.Path]::GetFileNameWithoutExtension($wrapper.Name)
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $shortcut.Save()
    Write-Host ("Olusturuldu: {0}" -f $shortcutPath)
}

Write-Host ""
Write-Host ("Toplam {0} kisayol hazir." -f $wrappers.Count)
