[CmdletBinding()]
param(
    [ValidateSet('Demo', 'Observe', 'Physical')]
    [string]$Mode = 'Demo',
    [ValidateRange(1024, 65535)]
    [int]$Port = 8081
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Proje Python ortami bulunamadi: .venv\Scripts\python.exe'
}

# Ignore inherited settings from the active SQL MES installation.
Get-ChildItem Env: | Where-Object { $_.Name -like 'MES_WEB_*' } | ForEach-Object {
    Remove-Item -LiteralPath ('Env:' + $_.Name)
}
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:MES_WEB_HOST = '127.0.0.1'
$env:MES_WEB_PORT = [string]$Port
$env:MES_WEB_TOPIC_ROOT = 'sau/iot/mega/konveyor'
$env:MES_WEB_MQTT_HOST = '127.0.0.1'
$env:MES_WEB_MQTT_PORT = '18883'
$env:MES_WEB_COMMAND_MODE = 'read_only'
$env:MES_WEB_PUBLISH_ENABLED = 'false'
$env:MES_WEB_MANUAL_COMMAND_ENABLED = 'false'
$env:MES_WEB_VISION_INGEST_ENABLED = 'false'
$env:MES_WEB_VISION_UI_VISIBLE = 'false'
$env:MES_WEB_EXCEL_ENABLED = 'true'
$env:MES_WEB_OEE_RUNTIME_STATE_PATH = Join-Path $projectRoot 'logs\oee_runtime_state.json'
$env:MES_WEB_EXCEL_TEMPLATE_PATH = Join-Path $projectRoot 'MES_Konveyor_Veritabani_Sablonu.xlsx'
$env:MES_WEB_FERP_IMPORT_DIR = Join-Path $projectRoot 'mes_web\ferp_import'
$env:MES_WEB_WORK_ORDERS_DIR = $env:MES_WEB_FERP_IMPORT_DIR
$env:MES_WEB_FERP_EXPORT_PENDING_DIR = Join-Path $projectRoot 'logs\ferp_exports\pending'
$env:MES_WEB_FERP_EXPORT_EXAMPLES_DIR = Join-Path $projectRoot 'logs\ferp_exports\examples\ferp_xls_seeded'
$env:MES_WORKBOOK_SCHEMA_VALIDATION_ENABLED = 'false'
$env:MES_MASTERDATA_VALIDATION_ENABLED = 'false'

if ($Mode -in @('Observe', 'Physical')) {
    $env:MES_WEB_MQTT_HOST = 'broker.emqx.io'
    $env:MES_WEB_MQTT_PORT = '1883'
}
if ($Mode -eq 'Physical') {
    $env:MES_WEB_COMMAND_MODE = 'full_live'
    $env:MES_WEB_PUBLISH_ENABLED = 'true'
    $env:MES_WEB_MANUAL_COMMAND_ENABLED = 'true'
}

Write-Host ('SQL oncesi MES - Mod: {0}' -f $Mode)
Write-Host ('Dashboard : http://127.0.0.1:{0}/' -f $Port)
Write-Host ('Kiosk     : http://127.0.0.1:{0}/kiosk/kiosk-test-1' -f $Port)
Write-Host ('Teknisyen : http://127.0.0.1:{0}/technician/tech-1' -f $Port)
Write-Host ('MQTT      : {0}:{1}' -f $env:MES_WEB_MQTT_HOST, $env:MES_WEB_MQTT_PORT)
Write-Host 'Raspberry Pi gerekli degil. Durdurmak icin Ctrl+C.'
if ($Mode -eq 'Demo') {
    Write-Host 'Yerel test brokeri acik degilse Broker Offline normaldir; web ekranlari calisir.'
} elseif ($Mode -eq 'Observe') {
    Write-Host 'Fiziksel hat dinlenir; MQTT komut gonderimi kapali.'
} else {
    Write-Host 'FIZIKSEL KONTROL: Ekrandaki komutlar ESP32/Mega uzerinden donanimi hareket ettirebilir.'
}

Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m mes_web
    $runtimeExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $runtimeExitCode
