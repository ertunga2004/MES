<#
.SYNOPSIS
    MES SQL MVP - read-only DB consistency checks.
.DESCRIPTION
    Checks the PostgreSQL MVP tables for source-of-truth cutover risks.
    SAFE: read-only. Does not update, delete, truncate, or migrate data.
#>

[CmdletBinding()]
param(
    [string]$PostgresContainer = "mes_postgres",
    [string]$DbUser = "mes",
    [string]$DbName = "mes"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$script:PassCount = 0
$script:FailCount = 0
$script:WarnCount = 0

function Write-Check {
    param(
        [string]$Name,
        [ValidateSet("PASS","FAIL","WARN")]
        [string]$Status,
        [string]$Detail = ""
    )
    $color = switch ($Status) {
        "PASS" { "Green" }
        "FAIL" { "Red" }
        "WARN" { "Yellow" }
    }
    $line = "[$Status] $Name"
    if ($Detail) { $line += " : $Detail" }
    Write-Host $line -ForegroundColor $color
    switch ($Status) {
        "PASS" { $script:PassCount++ }
        "FAIL" { $script:FailCount++ }
        "WARN" { $script:WarnCount++ }
    }
}

function Invoke-PsqlScalar {
    param([string]$Query)
    $raw = docker exec $PostgresContainer psql -U $DbUser -d $DbName -t -A -c $Query 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Check -Name "psql query" -Status "FAIL" -Detail ($raw | Out-String).Trim()
        return $null
    }
    return ($raw | Out-String).Trim()
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

function Write-PsqlRows {
    param([string]$Title, [string]$Query)
    Write-Host ""
    Write-Host $Title -ForegroundColor White
    $rows = docker exec $PostgresContainer psql -U $DbUser -d $DbName -c $Query 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ($rows | Out-String)
    } else {
        Write-Check -Name $Title -Status "FAIL" -Detail ($rows | Out-String).Trim()
    }
}

Write-Host ""
Write-Host "MES SQL MVP - DB Consistency Check" -ForegroundColor Cyan
Write-Host (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -ForegroundColor DarkGray
Write-Host ""

Check-Zero `
    -Name "work_orders duplicate order_id" `
    -Query "SELECT count(*) FROM (SELECT order_id FROM mes.work_orders GROUP BY order_id HAVING count(*) > 1) d;"

Check-Zero `
    -Name "eligible WIP missing source_work_order_id" `
    -Query "SELECT count(*) FROM mes.package_component_wip WHERE status = 'available' AND quality_status = 'GOOD' AND COALESCE(btrim(source_work_order_id), '') = '';"

$missingStationQuery = "SELECT count(*) FROM mes.work_orders WHERE status IN ('active', 'pending_approval') AND COALESCE(btrim(metadata->>'station_code'), '') = '';"
$missingStation = Invoke-PsqlScalar $missingStationQuery
if ($null -eq $missingStation -or $missingStation -eq "") {
    Write-Check -Name "active/pending missing metadata.station_code" -Status "FAIL" -Detail "query failed"
} elseif ([int]$missingStation -eq 0) {
    Write-Check -Name "active/pending missing metadata.station_code" -Status "PASS" -Detail "0"
} else {
    Write-Check -Name "active/pending missing metadata.station_code" -Status "FAIL" -Detail $missingStation
    Write-PsqlRows `
        -Title "Active/pending rows missing metadata.station_code" `
        -Query "SELECT order_id, status, payload->>'stationCode' AS payload_station_code, metadata->>'station_code' AS metadata_station_code, updated_at FROM mes.work_orders WHERE status IN ('active', 'pending_approval') AND COALESCE(btrim(metadata->>'station_code'), '') = '' ORDER BY updated_at DESC;"
}

Check-Zero `
    -Name "station active/pending conflicts" `
    -Query "SELECT count(*) FROM (SELECT COALESCE(NULLIF(metadata->>'station_code', ''), 'UNKNOWN') AS station_code FROM mes.work_orders WHERE status IN ('active', 'pending_approval') GROUP BY 1 HAVING count(*) > 1) d;"

Check-Zero `
    -Name "consumed WIP missing consumed_by_package_id" `
    -Query "SELECT count(*) FROM mes.package_component_wip WHERE status = 'consumed' AND COALESCE(btrim(consumed_by_package_id), '') = '';"

Check-Zero `
    -Name "reserved WIP missing reserved_by_session_id" `
    -Query "SELECT count(*) FROM mes.package_component_wip WHERE status = 'reserved' AND COALESCE(btrim(reserved_by_session_id), '') = '';"

Check-Zero `
    -Name "package_started without package_finished session" `
    -Query "WITH started AS (SELECT payload->'package_process'->>'session_id' AS session_id FROM mes.work_order_events WHERE event_type = 'package_started'), finished AS (SELECT payload->'package_process'->>'session_id' AS session_id FROM mes.work_order_events WHERE event_type = 'package_finished') SELECT count(*) FROM started s LEFT JOIN finished f ON f.session_id = s.session_id WHERE COALESCE(s.session_id, '') <> '' AND f.session_id IS NULL;"

Write-Host ""
Write-Host "Recent work_order_events" -ForegroundColor White
$recent = docker exec $PostgresContainer psql -U $DbUser -d $DbName -c "SELECT event_at, event_type, order_id, external_ref FROM mes.work_order_events ORDER BY event_at DESC NULLS LAST, event_pk DESC LIMIT 20;" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host ($recent | Out-String)
} else {
    Write-Check -Name "recent work_order_events" -Status "FAIL" -Detail ($recent | Out-String).Trim()
}

Write-Host ""
Write-Host "Summary: PASS=$script:PassCount WARN=$script:WarnCount FAIL=$script:FailCount" -ForegroundColor Cyan
if ($script:FailCount -gt 0) {
    exit 1
}
exit 0
