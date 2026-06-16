<#
.SYNOPSIS
    MES SQL MVP - Runtime Backup
.DESCRIPTION
    Creates a timestamped backup of all MVP runtime artefacts:
      - PostgreSQL full dump (pg_dump via container)
      - .env
      - compose.yaml / compose.portable.yaml
      - data/logs/oee_runtime_state.json
      - app_source (snapshot copy)
    Backups land in:  deploy_backups/mvp_runtime_<timestamp>/
.NOTES
    SAFE: Does NOT stop services, does NOT run docker down.
    Run from the MES Docker project root:
      powershell -ExecutionPolicy Bypass -File tools/mvp_backup_runtime.ps1
      powershell -ExecutionPolicy Bypass -File tools/mvp_backup_runtime.ps1 -DryRun
#>

[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Paths -------------------------------------------------------------------
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Timestamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupName  = "mvp_runtime_$Timestamp"
$BackupDir   = Join-Path (Join-Path $ProjectRoot "deploy_backups") $BackupName

# -- Helpers ------------------------------------------------------------------
$script:StepCount = 0
$script:Errors    = @()

function Write-Step {
    param([string]$Message)
    $script:StepCount++
    $prefix = if ($DryRun) { "[DRY-RUN]" } else { "[BACKUP]" }
    Write-Host "  $prefix $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Write-Err {
    param([string]$Message)
    $script:Errors += $Message
    Write-Host "    ERROR: $Message" -ForegroundColor Red
}

function Safe-Copy {
    param(
        [string]$Source,
        [string]$DestDir,
        [string]$Label
    )
    if (-not (Test-Path $Source)) {
        Write-Err "$Label not found: $Source"
        return
    }
    if ($DryRun) {
        Write-Ok "$Label would copy to $DestDir"
        return
    }
    if (-not (Test-Path $DestDir)) {
        New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    }
    Copy-Item -Path $Source -Destination $DestDir -Force
    Write-Ok "$Label copied"
}

function Safe-CopyDir {
    param(
        [string]$Source,
        [string]$DestDir,
        [string]$Label
    )
    if (-not (Test-Path $Source)) {
        Write-Err "$Label not found: $Source"
        return
    }
    if ($DryRun) {
        $itemCount = (Get-ChildItem -Path $Source -Recurse -File).Count
        Write-Ok "$Label ($itemCount files) would copy to $DestDir"
        return
    }
    Copy-Item -Path $Source -Destination $DestDir -Recurse -Force
    Write-Ok "$Label copied"
}

# -- Banner -------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  MES SQL MVP - Runtime Backup" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
if ($DryRun) {
    Write-Host "  MODE: DRY-RUN (no files will be written)" -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Target: deploy_backups/$BackupName/" -ForegroundColor White
Write-Host ""

# -- Create backup dir --------------------------------------------------------
if (-not $DryRun) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

# ============================================================================
# 1. PostgreSQL dump
# ============================================================================
Write-Step "PostgreSQL dump (pg_dump)"

$dumpFile  = "mes_full_$Timestamp.sql"
$dumpDest  = Join-Path $BackupDir $dumpFile

if ($DryRun) {
    Write-Ok "Would run: docker exec mes_postgres pg_dump ... to $dumpFile"
} else {
    try {
        # Dump inside container to /backups, then copy out
        docker exec mes_postgres pg_dump -U mes -d mes --no-owner --no-acl `
            -f "/backups/$dumpFile" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "pg_dump exit code: $LASTEXITCODE"
        }
        $containerDump = Join-Path (Join-Path (Join-Path $ProjectRoot "data") "db_backups") $dumpFile
        if (Test-Path $containerDump) {
            Move-Item -Path $containerDump -Destination $dumpDest -Force
            $dumpSize = (Get-Item $dumpDest).Length / 1KB
            Write-Ok "$dumpFile ($([math]::Round($dumpSize, 1)) KB)"
        } else {
            throw "Dump file not found at expected path: $containerDump"
        }
    } catch {
        Write-Err "pg_dump failed: $_"
    }
}

# ============================================================================
# 2. Configuration files
# ============================================================================
Write-Step "Configuration files"

$configFiles = @(
    @{ Path = ".env";                   Label = ".env" },
    @{ Path = "compose.yaml";           Label = "compose.yaml" },
    @{ Path = "compose.portable.yaml";  Label = "compose.portable.yaml" }
)

foreach ($cf in $configFiles) {
    $src = Join-Path $ProjectRoot $cf.Path
    Safe-Copy -Source $src -DestDir $BackupDir -Label $cf.Label
}

# ============================================================================
# 3. OEE runtime state
# ============================================================================
Write-Step "OEE runtime state"

$oeeSrc = Join-Path (Join-Path (Join-Path $ProjectRoot "data") "logs") "oee_runtime_state.json"
Safe-Copy -Source $oeeSrc -DestDir $BackupDir -Label "oee_runtime_state.json"

# ============================================================================
# 4. App source snapshot
# ============================================================================
Write-Step "App source snapshot"

$appSrcDir = Join-Path $ProjectRoot "app_source"
$appDst    = Join-Path $BackupDir "app_source"
Safe-CopyDir -Source $appSrcDir -DestDir $appDst -Label "app_source"

# ============================================================================
# 5. Backup manifest
# ============================================================================
Write-Step "Writing backup manifest"

$manifest = @{
    backup_name = $BackupName
    created_at  = (Get-Date -Format "o")
    dry_run     = [bool]$DryRun
    items       = @(
        $dumpFile,
        ".env",
        "compose.yaml",
        "compose.portable.yaml",
        "oee_runtime_state.json",
        "app_source/"
    )
}

if ($DryRun) {
    Write-Ok "Would write manifest.json"
} else {
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $BackupDir "manifest.json") -Encoding UTF8
    Write-Ok "manifest.json"
}

# ============================================================================
# SUMMARY
# ============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  BACKUP SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($script:Errors.Count -eq 0) {
    if ($DryRun) {
        Write-Host "  RESULT: DRY-RUN COMPLETE - No errors detected" -ForegroundColor Green
    } else {
        Write-Host "  RESULT: BACKUP COMPLETE" -ForegroundColor Green
        Write-Host "  Location: deploy_backups/$BackupName/" -ForegroundColor White
        $totalSize = (Get-ChildItem -Path $BackupDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
        $sizeMB = [math]::Round($totalSize / 1MB, 1)
        Write-Host "  Total size: $sizeMB MB" -ForegroundColor White
    }
} else {
    Write-Host "  RESULT: BACKUP COMPLETED WITH ERRORS" -ForegroundColor Red
    Write-Host "  Errors:" -ForegroundColor Red
    foreach ($e in $script:Errors) {
        Write-Host "    - $e" -ForegroundColor Red
    }
}

Write-Host ""
exit $script:Errors.Count
