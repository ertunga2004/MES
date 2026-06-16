<#
.SYNOPSIS
    MES SQL MVP - Smoke Check
.DESCRIPTION
    Production-readiness smoke test for the MES SQL MVP stack.
    Checks Docker services, health endpoint, DB flags, row counts,
    duplicate detection, dashboard / kiosk accessibility, and work order visibility.
    Exits with 0 on PASS, 1 on FAIL.
.NOTES
    SAFE: Read-only. Does NOT modify .env, DB, or containers.
    Run from the MES Docker project root:
      powershell -ExecutionPolicy Bypass -File tools/mvp_smoke_check.ps1
#>

[CmdletBinding()]
param(
    [string]$ComposeFile = "compose.yaml",
    [string]$BaseUrl     = "http://localhost:8080",
    [int]   $TimeoutSec  = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# -- Helpers -----------------------------------------------------------------
$script:PassCount = 0
$script:FailCount = 0
$script:WarnCount = 0
$script:Results   = @()

function Write-Check {
    param(
        [string]$Name,
        [ValidateSet("PASS","FAIL","WARN","SKIP")]
        [string]$Status,
        [string]$Detail = ""
    )
    $color = switch ($Status) {
        "PASS" { "Green"  }
        "FAIL" { "Red"    }
        "WARN" { "Yellow" }
        "SKIP" { "DarkGray" }
    }
    $icon = switch ($Status) {
        "PASS" { "+" }
        "FAIL" { "X" }
        "WARN" { "!" }
        "SKIP" { "-" }
    }
    $line = "  [$icon] $Name"
    if ($Detail) { $line += " : $Detail" }
    Write-Host $line -ForegroundColor $color

    switch ($Status) {
        "PASS" { $script:PassCount++ }
        "FAIL" { $script:FailCount++ }
        "WARN" { $script:WarnCount++ }
    }
    $script:Results += [PSCustomObject]@{
        Check  = $Name
        Status = $Status
        Detail = $Detail
    }
}

function Invoke-Psql {
    param([string]$Query)
    $raw = docker exec mes_postgres psql -U mes -d mes -t -A -c $Query 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($raw | Out-String).Trim()
}

# -- Banner ------------------------------------------------------------------
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  MES SQL MVP - Smoke Check" -ForegroundColor Cyan
Write-Host "  $ts" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# 1. DOCKER SERVICES
# ============================================================================
Write-Host "[1/7] Docker Services" -ForegroundColor White

$requiredContainers = @("mes_web", "mes_postgres", "mes_adminer")
foreach ($c in $requiredContainers) {
    $state = (docker inspect --format '{{.State.Status}}' $c 2>$null)
    if ($state -eq "running") {
        Write-Check -Name "Container $c" -Status "PASS" -Detail "running"
    } else {
        Write-Check -Name "Container $c" -Status "FAIL" -Detail "state=$state"
    }
}

# Postgres health status
$pgHealth = (docker inspect --format '{{.State.Health.Status}}' mes_postgres 2>$null)
if ($pgHealth -eq "healthy") {
    Write-Check -Name "PostgreSQL health" -Status "PASS" -Detail "healthy"
} else {
    Write-Check -Name "PostgreSQL health" -Status "FAIL" -Detail "health=$pgHealth"
}

Write-Host ""

# ============================================================================
# 2. HEALTH ENDPOINT
# ============================================================================
Write-Host "[2/7] Health Endpoint" -ForegroundColor White

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        $body = $resp.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        Write-Check -Name "/health HTTP 200" -Status "PASS" -Detail "status=$($body.status)"
    } else {
        Write-Check -Name "/health HTTP 200" -Status "FAIL" -Detail "HTTP $($resp.StatusCode)"
    }
} catch {
    Write-Check -Name "/health HTTP 200" -Status "FAIL" -Detail $_.Exception.Message
}

Write-Host ""

# ============================================================================
# 3. CONTAINER DB FLAGS
# ============================================================================
Write-Host "[3/7] Container DB Flags" -ForegroundColor White

$criticalFlags = @{
    "MES_WEB_DB_ENABLED"                    = "true"
    "MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS"= "true"
    "MES_WEB_DB_HOOK_STATION_EVENTS"        = "true"
    "MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS"= "true"
    "MES_WEB_DB_READ_WORK_ORDERS"           = "true"
    "MES_WEB_DB_FAIL_OPEN"                  = "true"
    "MES_WEB_DB_LOG_FAILURES"               = "true"
}
$dryRunFlags = @(
    "MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN",
    "MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN",
    "MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS_DRY_RUN"
)

foreach ($kv in $criticalFlags.GetEnumerator()) {
    $val = (docker exec mes_web printenv $kv.Key 2>$null)
    if ($val -eq $kv.Value) {
        Write-Check -Name $kv.Key -Status "PASS" -Detail $val
    } else {
        Write-Check -Name $kv.Key -Status "FAIL" -Detail "expected=$($kv.Value), got=$val"
    }
}

foreach ($flag in $dryRunFlags) {
    $val = (docker exec mes_web printenv $flag 2>$null)
    if ($val -eq "false" -or [string]::IsNullOrEmpty($val)) {
        Write-Check -Name "$flag" -Status "PASS" -Detail "off ($val)"
    } else {
        Write-Check -Name "$flag" -Status "WARN" -Detail "DRY_RUN is ON ($val)"
    }
}

Write-Host ""

# ============================================================================
# 4. TABLE ROW COUNTS
# ============================================================================
Write-Host "[4/7] Table Row Counts" -ForegroundColor White

$tableNames = @("mes.work_orders", "mes.work_order_events", "mes.production_completions", "mes.item_station_events")

foreach ($tbl in $tableNames) {
    $count = Invoke-Psql "SELECT count(*) FROM $tbl;"
    if ($null -eq $count) {
        Write-Check -Name "$tbl count" -Status "FAIL" -Detail "query failed"
    } else {
        $n = [int]$count
        Write-Check -Name "$tbl count" -Status "PASS" -Detail "$n rows"
    }
}

Write-Host ""

# ============================================================================
# 5. DUPLICATE DETECTION
# ============================================================================
Write-Host "[5/7] Duplicate Detection" -ForegroundColor White

# 5a. production_completions - duplicate external_ref
$pcDupQuery = "SELECT count(*) FROM (SELECT external_ref FROM mes.production_completions WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY external_ref HAVING count(*) > 1) sub;"
$pcDups = Invoke-Psql $pcDupQuery
if ($null -eq $pcDups) {
    Write-Check -Name "production_completions dup external_ref" -Status "FAIL" -Detail "query failed"
} elseif ([int]$pcDups -eq 0) {
    Write-Check -Name "production_completions dup external_ref" -Status "PASS" -Detail "0 duplicates"
} else {
    Write-Check -Name "production_completions dup external_ref" -Status "FAIL" -Detail "$pcDups duplicate groups"
}

# 5b. item_station_events - duplicate source + external_ref
$iseDupQuery = "SELECT count(*) FROM (SELECT source, external_ref FROM mes.item_station_events WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY source, external_ref HAVING count(*) > 1) sub;"
$iseDups = Invoke-Psql $iseDupQuery
if ($null -eq $iseDups) {
    Write-Check -Name "item_station_events dup source/external_ref" -Status "FAIL" -Detail "query failed"
} elseif ([int]$iseDups -eq 0) {
    Write-Check -Name "item_station_events dup source/external_ref" -Status "PASS" -Detail "0 duplicates"
} else {
    Write-Check -Name "item_station_events dup source/external_ref" -Status "FAIL" -Detail "$iseDups duplicate groups"
}

# 5c. work_order_events - duplicate external_ref
$woeDupQuery = "SELECT count(*) FROM (SELECT external_ref FROM mes.work_order_events WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY external_ref HAVING count(*) > 1) sub;"
$woeDups = Invoke-Psql $woeDupQuery
if ($null -eq $woeDups) {
    Write-Check -Name "work_order_events dup external_ref" -Status "FAIL" -Detail "query failed"
} elseif ([int]$woeDups -eq 0) {
    Write-Check -Name "work_order_events dup external_ref" -Status "PASS" -Detail "0 duplicates"
} else {
    Write-Check -Name "work_order_events dup external_ref" -Status "FAIL" -Detail "$woeDups duplicate groups"
}

Write-Host ""

# ============================================================================
# 6. DASHBOARD & KIOSK ACCESSIBILITY
# ============================================================================
Write-Host "[6/7] Dashboard & Kiosk Accessibility" -ForegroundColor White

# Dashboard - GET /api/modules/konveyor_main/dashboard
try {
    $dashResp = Invoke-WebRequest -Uri "$BaseUrl/api/modules/konveyor_main/dashboard" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($dashResp.StatusCode -eq 200) {
        Write-Check -Name "Dashboard konveyor_main" -Status "PASS" -Detail "HTTP 200"
    } else {
        Write-Check -Name "Dashboard konveyor_main" -Status "FAIL" -Detail "HTTP $($dashResp.StatusCode)"
    }
} catch {
    Write-Check -Name "Dashboard konveyor_main" -Status "FAIL" -Detail $_.Exception.Message
}

# Kiosk - GET /kiosk/konveyor_main
try {
    $kioskResp = Invoke-WebRequest -Uri "$BaseUrl/kiosk/konveyor_main" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($kioskResp.StatusCode -eq 200) {
        Write-Check -Name "Kiosk konveyor_main" -Status "PASS" -Detail "HTTP 200"
    } else {
        Write-Check -Name "Kiosk konveyor_main" -Status "FAIL" -Detail "HTTP $($kioskResp.StatusCode)"
    }
} catch {
    Write-Check -Name "Kiosk konveyor_main" -Status "FAIL" -Detail $_.Exception.Message
}

Write-Host ""

# ============================================================================
# 7. ACTIVE / PENDING WORK ORDERS VISIBLE
# ============================================================================
Write-Host "[7/7] Active / Pending Work Orders" -ForegroundColor White

try {
    $woResp = Invoke-WebRequest -Uri "$BaseUrl/api/modules/konveyor_main/dashboard" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($woResp.StatusCode -eq 200) {
        $woData = $woResp.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        # Dashboard work_orders may have: active_order, ordered, queue
        $activeCount  = 0
        $queuedCount  = 0
        $orderedCount = 0
        $woProps = @()
        if ($woData -and $woData.PSObject.Properties["work_orders"]) {
            $woSection = $woData.work_orders
            if ($woSection.PSObject.Properties["active_order"] -and $woSection.active_order) { $activeCount = 1 }
            if ($woSection.PSObject.Properties["ordered"]) { $orderedCount = @($woSection.ordered).Count }
            if ($woSection.PSObject.Properties["queue"])   { $queuedCount  = @($woSection.queue).Count }
        }
        $totalVisible = $activeCount + $orderedCount + $queuedCount

        if ($totalVisible -gt 0) {
            Write-Check -Name "Work orders visible" -Status "PASS" -Detail "total=$totalVisible active=$activeCount ordered=$orderedCount queued=$queuedCount"
        } else {
            Write-Check -Name "Work orders visible" -Status "WARN" -Detail "0 work orders in dashboard (may be expected outside shift)"
        }
    } else {
        Write-Check -Name "Work orders visible" -Status "FAIL" -Detail "HTTP $($woResp.StatusCode)"
    }
} catch {
    Write-Check -Name "Work orders visible" -Status "FAIL" -Detail $_.Exception.Message
}

Write-Host ""

# ============================================================================
# VERDICT
# ============================================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  PASS : $script:PassCount" -ForegroundColor Green
Write-Host "  FAIL : $script:FailCount" -ForegroundColor Red
Write-Host "  WARN : $script:WarnCount" -ForegroundColor Yellow
Write-Host ""

if ($script:FailCount -eq 0) {
    Write-Host "  >>> SMOKE CHECK: PASS <<<" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host "  >>> SMOKE CHECK: FAIL <<<" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Failed checks:" -ForegroundColor Red
    $script:Results | Where-Object { $_.Status -eq "FAIL" } | ForEach-Object {
        Write-Host "    - $($_.Check): $($_.Detail)" -ForegroundColor Red
    }
    Write-Host ""
    exit 1
}
