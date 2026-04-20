[CmdletBinding()]
param(
    [string]$App,
    [switch]$ListApps,
    [switch]$PrintCommand
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$supportRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcherRoot = Split-Path -Parent $supportRoot
$repoRoot = Split-Path -Parent $launcherRoot

function Resolve-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDir
    )

    $candidatePaths = @(
        (Join-Path $WorkingDir ".venv\Scripts\python.exe"),
        (Join-Path $repoRoot ".venv\Scripts\python.exe"),
        (Join-Path (Split-Path -Parent $WorkingDir) ".venv\Scripts\python.exe")
    ) | Select-Object -Unique

    function Test-PythonCommand {
        param(
            [Parameter(Mandatory = $true)]
            [string]$Exe,
            [string[]]$Prefix = @()
        )

        try {
            & $Exe @Prefix -c "import sys" *> $null
            $exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
            return $exitCode -eq 0
        } catch {
            return $false
        }
    }

    foreach ($candidate in $candidatePaths) {
        if ($candidate -and (Test-Path -LiteralPath $candidate) -and (Test-PythonCommand -Exe $candidate)) {
            return @{
                Exe = $candidate
                Prefix = @()
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonCommand -Exe $python.Source)) {
        return @{
            Exe = $python.Source
            Prefix = @()
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py -and (Test-PythonCommand -Exe $py.Source -Prefix @("-3"))) {
        return @{
            Exe = $py.Source
            Prefix = @("-3")
        }
    }

    throw "Python bulunamadi. Bir .venv veya sistem Python kurulumu gerekli."
}

function Invoke-RaspberryClockSync {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $syncScript = Join-Path $RepoRoot "raspberry\tools\publish_time_sync.ps1"
    if (-not (Test-Path -LiteralPath $syncScript)) {
        throw "Saat senkron scripti bulunamadi: $syncScript"
    }

    Write-Host "Observer ve Raspberry Pi saati guncelleniyor..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript -ApplySystemClock
    $syncExitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
    if ($syncExitCode -ne 0) {
        throw "Saat senkronu basarisiz oldu. Cikis kodu: $syncExitCode"
    }
    Write-Host "Saat senkronu tamamlandi."
    Write-Host ""
}

function Get-AppCatalog {
    return [ordered]@{
        "mes_web" = @{
            DisplayName = "MES Web"
            WorkingDir = $repoRoot
            EntryKind = "module"
            Entry = "mes_web"
            Args = @()
            Requirements = Join-Path $repoRoot "mes_web\requirements.txt"
            Url = "http://127.0.0.1:8080"
            UrlHints = @(
                "Lokal panel: http://127.0.0.1:8080",
                "Kiosk ornegi: http://127.0.0.1:8080/kiosk/kiosk-test-1",
                "Ag erisimi: http://<BU_BILGISAYAR_IP>:8080/kiosk/kiosk-test-1"
            )
            Env = @{
                "MES_WEB_HOST" = "0.0.0.0"
                "MES_WEB_PORT" = "8080"
            }
        }
        "picktolight" = @{
            DisplayName = "Pick To Light"
            WorkingDir = Join-Path $repoRoot "picktolight"
            EntryKind = "script"
            Entry = "app.py"
            Args = @()
            Requirements = Join-Path $repoRoot "picktolight\requirements.txt"
            Url = $null
        }
        "giyotin_kontrol" = @{
            DisplayName = "Giyotin Kontrol"
            WorkingDir = Join-Path $repoRoot "Giyotin_kontrol\pc_app"
            EntryKind = "script"
            Entry = "cli.py"
            Args = @()
            Requirements = Join-Path $repoRoot "Giyotin_kontrol\pc_app\requirements.txt"
            Url = $null
        }
        "raspberry_observer_gui" = @{
            DisplayName = "Raspberry Observer GUI"
            WorkingDir = Join-Path $repoRoot "raspberry"
            EntryKind = "script"
            Entry = "run_observer.py"
            Args = @("--config", "config/observer.example.json", "--boxes", "config/boxes.example.json")
            Requirements = Join-Path $repoRoot "raspberry\requirements.txt"
            Url = $null
            SyncClock = $true
        }
        "raspberry_observer_headless" = @{
            DisplayName = "Raspberry Observer Headless"
            WorkingDir = Join-Path $repoRoot "raspberry"
            EntryKind = "script"
            Entry = "run_observer.py"
            Args = @("--config", "config/observer.example.json", "--boxes", "config/boxes.example.json", "--no-gui")
            Requirements = Join-Path $repoRoot "raspberry\requirements.txt"
            Url = $null
            SyncClock = $true
        }
        "raspberry_hsv_calibration" = @{
            DisplayName = "Raspberry HSV Kalibrasyon"
            WorkingDir = Join-Path $repoRoot "raspberry"
            EntryKind = "script"
            Entry = "calibrate_hsv.py"
            Args = @("--source", "0")
            Requirements = Join-Path $repoRoot "raspberry\requirements.txt"
            Url = $null
            SyncClock = $true
        }
        "raspberry_clock_sync" = @{
            DisplayName = "Raspberry Saat Senkronu"
            WorkingDir = Join-Path $repoRoot "raspberry"
            EntryKind = "sync_only"
            Entry = ""
            Args = @()
            Requirements = $null
            Url = $null
            SyncClock = $true
        }
    }
}

function Quote-Args {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Parts
    )

    return ($Parts | ForEach-Object {
        if ($_ -match "\s") {
            '"' + $_ + '"'
        } else {
            $_
        }
    }) -join " "
}

$catalog = Get-AppCatalog

if ($ListApps) {
    foreach ($key in $catalog.Keys) {
        Write-Host ("{0,-28} {1}" -f $key, $catalog[$key].DisplayName)
    }
    exit 0
}

if (-not $App) {
    Write-Host "Kullanim: Start-MesApp.ps1 -App <uygulama_kodu>"
    Write-Host ""
    Write-Host "Mevcut uygulamalar:"
    foreach ($key in $catalog.Keys) {
        Write-Host ("  {0,-28} {1}" -f $key, $catalog[$key].DisplayName)
    }
    exit 2
}

if (-not $catalog.Contains($App)) {
    throw "Bilinmeyen uygulama kodu: $App"
}

$config = $catalog[$App]
$workingDir = [string]$config.WorkingDir
$entryKind = [string]$config.EntryKind
$entry = [string]$config.Entry
$requirements = [string]$config.Requirements
$url = [string]$config.Url
$syncClock = if ($config.Contains("SyncClock")) { [bool]$config["SyncClock"] } else { $false }
$urlHints = if ($config.Contains("UrlHints")) { [string[]]$config["UrlHints"] } else { @() }
$envMap = if ($config.Contains("Env")) { [hashtable]$config["Env"] } else { @{} }
$bindHost = if ($envMap.Contains("MES_WEB_HOST")) { [string]$envMap["MES_WEB_HOST"] } else { "" }
$bindPort = if ($envMap.Contains("MES_WEB_PORT")) { [string]$envMap["MES_WEB_PORT"] } else { "" }
$bindAddress = if ($bindHost -and $bindPort) { "{0}:{1}" -f $bindHost, $bindPort } else { "" }

if (-not (Test-Path -LiteralPath $workingDir)) {
    throw "Calisma klasoru bulunamadi: $workingDir"
}

$entryPath = if ($entryKind -eq "script") {
    Join-Path $workingDir $entry
} else {
    $null
}

if ($entryPath -and -not (Test-Path -LiteralPath $entryPath)) {
    throw "Giris dosyasi bulunamadi: $entryPath"
}

$commandPreview = ""
$python = $null
$commandArgs = @()

if ($entryKind -ne "sync_only") {
    $python = Resolve-PythonCommand -WorkingDir $workingDir
    $commandArgs += $python.Prefix

    switch ($entryKind) {
        "module" {
            $commandArgs += "-m"
            $commandArgs += $entry
        }
        "script" {
            $commandArgs += $entry
        }
        default {
            throw "Desteklenmeyen entry tipi: $entryKind"
        }
    }

    $commandArgs += [string[]]$config.Args
    $commandPreview = "{0} {1}" -f $python.Exe, (Quote-Args -Parts $commandArgs)
} else {
    $syncScript = Join-Path $repoRoot "raspberry\tools\publish_time_sync.ps1"
    $commandPreview = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$syncScript`" -ApplySystemClock"
}

if ($PrintCommand) {
    Write-Host ("Uygulama      : {0}" -f $config.DisplayName)
    Write-Host ("Calisma klasoru: {0}" -f $workingDir)
    Write-Host ("Komut         : {0}" -f $commandPreview)
    if ($syncClock) {
        Write-Host "Saat senkronu : Observer + Raspberry Pi (otomatik)"
    }
    if ($requirements -and (Test-Path -LiteralPath $requirements)) {
        Write-Host ("Requirements  : {0}" -f $requirements)
    }
    if ($url) {
        Write-Host ("URL           : {0}" -f $url)
    }
    if ($bindAddress) {
        Write-Host ("Dinleme       : {0}" -f $bindAddress)
    }
    foreach ($hint in $urlHints) {
        Write-Host ("URL           : {0}" -f $hint)
    }
    foreach ($key in $envMap.Keys) {
        Write-Host ("ENV           : {0}={1}" -f $key, $envMap[$key])
    }
    exit 0
}

Write-Host ("Baslatiliyor: {0}" -f $config.DisplayName)
Write-Host ("Calisma klasoru: {0}" -f $workingDir)
if ($url) {
    Write-Host ("Hazir olunca tarayicidan ac: {0}" -f $url)
}
if ($bindAddress) {
    Write-Host ("Ag dinleme adresi: {0}" -f $bindAddress)
}
foreach ($hint in $urlHints) {
    Write-Host ("Kiosk         : {0}" -f $hint)
}
if ($requirements -and (Test-Path -LiteralPath $requirements)) {
    Write-Host ("Bagimlilik gerekirse: python -m pip install -r {0}" -f $requirements)
}
Write-Host ""

if ($syncClock) {
    Invoke-RaspberryClockSync -RepoRoot $repoRoot
}

if ($entryKind -eq "sync_only") {
    exit 0
}

Push-Location $workingDir
try {
    foreach ($key in $envMap.Keys) {
        [System.Environment]::SetEnvironmentVariable($key, [string]$envMap[$key], "Process")
    }
    & $python.Exe @commandArgs
    $exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
} finally {
    Pop-Location
}

exit $exitCode
