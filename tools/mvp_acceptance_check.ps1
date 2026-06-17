<#
.SYNOPSIS
    MESQL MVP Acceptance Pack.
.DESCRIPTION
    Runs the read-only MVP acceptance checks from one command.
    It checks web health, smoke, DB consistency, table presence, row counts,
    operational consistency, and recent operational summaries.
#>

[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$PostgresContainer = "mes_postgres",
    [string]$DbUser = "mes",
    [string]$DbName = "mes",
    [int]$TimeoutSec = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0

function Write-Check {
    param(
        [string]$Name,
        [ValidateSet("PASS","WARN","FAIL")]
        [string]$Status,
        [string]$Detail = ""
    )
    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
    }
    $line = "[$Status] $Name"
    if ($Detail) { $line += " : $Detail" }
    Write-Host $line -ForegroundColor $color
    switch ($Status) {
        "PASS" { $script:PassCount++ }
        "WARN" { $script:WarnCount++ }
        "FAIL" { $script:FailCount++ }
    }
}

function Invoke-PsqlScalar {
    param([string]$Query)
    $raw = docker exec $PostgresContainer psql -U $DbUser -d $DbName -t -A -c $Query 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Check -Name "psql scalar" -Status "FAIL" -Detail (($raw | Out-String).Trim())
        return $null
    }
    return ($raw | Out-String).Trim()
}

function Write-PsqlRows {
    param([string]$Title, [string]$Query)
    Write-Host ""
    Write-Host $Title -ForegroundColor White
    $rows = docker exec $PostgresContainer psql -U $DbUser -d $DbName -c $Query 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ($rows | Out-String)
        Write-Check -Name $Title -Status "PASS" -Detail "listed"
    } else {
        Write-Check -Name $Title -Status "FAIL" -Detail (($rows | Out-String).Trim())
    }
}

function Check-Zero {
    param([string]$Name, [string]$Query)
    $value = Invoke-PsqlScalar $Query
    if ($null -eq $value -or $value -eq "") {
        Write-Check -Name $Name -Status "FAIL" -Detail "query failed"
        return
    }
    if ([int]$value -eq 0) {
        Write-Check -Name $Name -Status "PASS" -Detail "0"
    } else {
        Write-Check -Name $Name -Status "FAIL" -Detail $value
    }
}

function Invoke-ChildScript {
    param([string]$Name, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Check -Name $Name -Status "FAIL" -Detail "missing script: $Path"
        return ""
    }
    Write-Host ""
    Write-Host $Name -ForegroundColor White
    $output = & powershell -ExecutionPolicy Bypass -File $Path 2>&1
    $code = $LASTEXITCODE
    Write-Host ($output | Out-String)
    if ($code -eq 0) {
        Write-Check -Name $Name -Status "PASS" -Detail "exit=0"
    } else {
        Write-Check -Name $Name -Status "FAIL" -Detail "exit=$code"
    }
    return ($output | Out-String)
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$smokeScript = Join-Path $scriptDir "mvp_smoke_check.ps1"
$consistencyScript = Join-Path $scriptDir "check_mes_db_consistency.ps1"

Write-Host ""
Write-Host "MESQL MVP Acceptance Pack" -ForegroundColor Cyan
Write-Host (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -ForegroundColor DarkGray
Write-Host ""

Write-Host "A) Web health" -ForegroundColor White
try {
    $health = Invoke-WebRequest -Uri "$BaseUrl/health" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($health.StatusCode -eq 200) {
        Write-Check -Name "/health HTTP 200" -Status "PASS" -Detail $BaseUrl
    } else {
        Write-Check -Name "/health HTTP 200" -Status "FAIL" -Detail "HTTP $($health.StatusCode)"
    }
} catch {
    Write-Check -Name "/health HTTP 200" -Status "FAIL" -Detail $_.Exception.Message
}

Write-Host ""
Write-Host "B) Smoke" -ForegroundColor White
$smokeOutput = Invoke-ChildScript -Name "tools/mvp_smoke_check.ps1" -Path $smokeScript

Write-Host ""
Write-Host "C) DB consistency" -ForegroundColor White
$consistencyOutput = Invoke-ChildScript -Name "tools/check_mes_db_consistency.ps1" -Path $consistencyScript
if ($consistencyOutput -match "Summary: PASS=(\d+) WARN=(\d+) FAIL=(\d+)") {
    if ([int]$Matches[3] -eq 0) {
        Write-Check -Name "DB consistency FAIL=0" -Status "PASS" -Detail "PASS=$($Matches[1]) WARN=$($Matches[2]) FAIL=$($Matches[3])"
    } else {
        Write-Check -Name "DB consistency FAIL=0" -Status "FAIL" -Detail "PASS=$($Matches[1]) WARN=$($Matches[2]) FAIL=$($Matches[3])"
    }
} else {
    Write-Check -Name "DB consistency summary parsed" -Status "WARN" -Detail "Summary line not found"
}

Write-Host ""
Write-Host "D) DB table presence" -ForegroundColor White
$tables = @(
    "mes.work_orders",
    "mes.station_queue",
    "mes.work_order_events",
    "mes.package_component_wip",
    "mes.package_sessions"
)
foreach ($table in $tables) {
    $exists = Invoke-PsqlScalar "SELECT CASE WHEN to_regclass('$table') IS NULL THEN 0 ELSE 1 END;"
    if ($null -eq $exists -or $exists -eq "") {
        Write-Check -Name "$table exists" -Status "FAIL" -Detail "query failed"
    } elseif ([int]$exists -eq 1) {
        Write-Check -Name "$table exists" -Status "PASS" -Detail "present"
    } else {
        Write-Check -Name "$table exists" -Status "FAIL" -Detail "missing"
    }
}

Write-Host ""
Write-Host "E) Row counts" -ForegroundColor White
foreach ($table in $tables) {
    $count = Invoke-PsqlScalar "SELECT count(*) FROM $table;"
    if ($null -eq $count -or $count -eq "") {
        Write-Check -Name "$table row count" -Status "FAIL" -Detail "query failed"
    } else {
        Write-Check -Name "$table row count" -Status "PASS" -Detail "$count rows"
    }
}

Write-Host ""
Write-Host "F) Operational consistency" -ForegroundColor White
Check-Zero `
    -Name "active/pending station conflict" `
    -Query "SELECT count(*) FROM (SELECT COALESCE(NULLIF(metadata->>'station_code', ''), 'UNKNOWN') AS station_code FROM mes.work_orders WHERE status IN ('active', 'pending_approval') GROUP BY 1 HAVING count(*) > 1) d;"
Check-Zero `
    -Name "queued work_orders missing station_queue row" `
    -Query "SELECT count(*) FROM mes.work_orders w LEFT JOIN mes.station_queue q ON q.order_id = w.order_id AND q.station_code = COALESCE(NULLIF(w.metadata->>'station_code', ''), w.payload->>'stationCode') WHERE w.status = 'queued' AND COALESCE(NULLIF(w.metadata->>'station_code', ''), w.payload->>'stationCode') IS NOT NULL AND q.order_id IS NULL;"
$packageSessionCount = Invoke-PsqlScalar "SELECT count(*) FROM mes.package_sessions;"
if ($null -eq $packageSessionCount -or $packageSessionCount -eq "") {
    Write-Check -Name "package_finished event missing package_session row" -Status "FAIL" -Detail "could not query package_sessions"
} elseif ([int]$packageSessionCount -eq 0) {
    Write-Check -Name "package_finished event missing package_session row" -Status "WARN" -Detail "package_sessions is empty"
} else {
    Check-Zero `
        -Name "package_finished event missing package_session row" `
        -Query "SELECT count(*) FROM mes.work_order_events e LEFT JOIN mes.package_sessions s ON s.session_id = e.payload->'package_process'->>'session_id' WHERE e.event_type = 'package_finished' AND COALESCE(e.payload->'package_process'->>'session_id', '') <> '' AND s.session_id IS NULL AND e.event_at >= (SELECT MIN(created_at) FROM mes.package_sessions);"
}
Check-Zero `
    -Name "package_sessions finished missing duration_seconds" `
    -Query "SELECT count(*) FROM mes.package_sessions WHERE status = 'finished' AND duration_seconds IS NULL;"
Check-Zero `
    -Name "eligible WIP missing source_work_order_id" `
    -Query "SELECT count(*) FROM mes.package_component_wip WHERE status = 'available' AND quality_status = 'GOOD' AND COALESCE(btrim(source_work_order_id), '') = '';"

Write-Host ""
Write-Host "G) Recent summaries" -ForegroundColor White
Write-PsqlRows `
    -Title "Last 10 work_orders" `
    -Query "SELECT order_id, status, metadata->>'station_code' AS station_code, metadata->>'queue_rank' AS queue_rank, updated_at FROM mes.work_orders ORDER BY updated_at DESC NULLS LAST, order_id LIMIT 10;"
Write-PsqlRows `
    -Title "Last 10 station_queue" `
    -Query "SELECT station_code, order_id, queue_rank, status, updated_at FROM mes.station_queue ORDER BY updated_at DESC NULLS LAST, station_code, queue_rank LIMIT 10;"
Write-PsqlRows `
    -Title "Last 10 package_sessions" `
    -Query "SELECT session_id, package_order_id, station_code, status, started_at, finished_at, duration_seconds, updated_at FROM mes.package_sessions ORDER BY updated_at DESC NULLS LAST LIMIT 10;"
Write-PsqlRows `
    -Title "Last 20 work_order_events" `
    -Query "SELECT event_at, event_type, order_id, payload->'package_process'->>'session_id' AS session_id, external_ref FROM mes.work_order_events ORDER BY event_at DESC NULLS LAST, event_pk DESC LIMIT 20;"
Write-PsqlRows `
    -Title "Package WIP eligible summary" `
    -Query "SELECT component_stock_code, status, quality_status, count(*) AS qty FROM mes.package_component_wip WHERE status = 'available' AND quality_status = 'GOOD' GROUP BY component_stock_code, status, quality_status ORDER BY component_stock_code;"

Write-Host ""
Write-Host "Summary: PASS=$script:PassCount WARN=$script:WarnCount FAIL=$script:FailCount" -ForegroundColor Cyan
if ($script:FailCount -gt 0) {
    exit 1
}
exit 0
