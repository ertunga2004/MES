<#
.SYNOPSIS
    MESQL MQTT Raw Capture Replay Tool
.DESCRIPTION
    Safely replays a raw MQTT capture file to a target broker.
.PARAMETER LogPath
    Path to the raw MQTT log file.
.PARAMETER Broker
    MQTT Broker address. Default: broker.emqx.io
.PARAMETER Port
    MQTT Broker port. Default: 1883
.PARAMETER TopicRoot
    Topic root. Default: sau/iot/mega/konveyor
.PARAMETER Speed
    Replay speed multiplier. Default: 1.0 (realtime).
.PARAMETER DryRun
    If set, shows the first 20 messages that would be published without actually publishing.
.PARAMETER MaxMessages
    Maximum number of messages to process.
.PARAMETER IncludeVision
    If set, includes vision topics.
.PARAMETER IncludeStatus
    If set, includes status topics.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$LogPath,
    [string]$Broker = "broker.emqx.io",
    [int]$Port = 1883,
    [string]$TopicRoot = "sau/iot/mega/konveyor",
    [double]$Speed = 1.0,
    [switch]$DryRun,
    [int]$MaxMessages = 0,
    [switch]$IncludeVision,
    [switch]$IncludeStatus
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Prerequisites check
if (-not $DryRun) {
    if (-not (Get-Command "mosquitto_pub" -ErrorAction SilentlyContinue)) {
        Write-Error "ERROR: mosquitto_pub is not found in PATH. Please install Mosquitto clients to publish messages."
        exit 1
    }
}

if (-not (Test-Path $LogPath)) {
    Write-Error "ERROR: Log file not found at $LogPath"
    exit 1
}

# Configuration
$Allowlist = @(
    "$TopicRoot/status",
    "$TopicRoot/logs",
    "$TopicRoot/heartbeat",
    "$TopicRoot/bridge/status",
    "$TopicRoot/vision/status",
    "$TopicRoot/vision/tracks",
    "$TopicRoot/vision/events",
    "$TopicRoot/vision/heartbeat"
)

# Statistics
$stats = @{
    Read = 0
    Published = 0
    Skipped = 0
    SkipReasons = @{}
}

function Add-SkipReason([string]$Reason) {
    $stats.Skipped++
    if (-not $stats.SkipReasons.ContainsKey($Reason)) {
        $stats.SkipReasons[$Reason] = 0
    }
    $stats.SkipReasons[$Reason]++
}

function Is-SafeTopic([string]$Topic) {
    # 1. Hard blacklists
    if ($Topic -match "/cmd") { return "Blacklisted: Contains /cmd" }
    if ($Topic -match "time_sync") { return "Blacklisted: Contains time_sync" }

    # 2. Whitelist
    if ($Allowlist -notcontains $Topic) { return "Not in Allowlist" }

    # 3. Optional filters
    if ($Topic -match "/vision/" -and -not $IncludeVision) { return "Vision topic skipped (-IncludeVision not set)" }
    if ($Topic -match "/status$" -and -not $IncludeStatus) { return "Status topic skipped (-IncludeStatus not set)" }

    return "SAFE"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " MESQL MQTT REPLAY TOOL" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Log File : $LogPath"
Write-Host "Broker   : $($Broker):$Port"
Write-Host "Speed    : $Speed x"
if ($DryRun) { Write-Host "MODE     : DRY-RUN (Will print max 20 messages, NO publish)" -ForegroundColor Yellow }

# Read file
# We use StreamReader to handle potentially large files and UTF-16
$reader = [System.IO.StreamReader]::new($LogPath, $true) # $true enables BOM detection

$lastTime = $null

try {
    while (($line = $reader.ReadLine()) -ne $null) {
        $stats.Read++
        
        if ($MaxMessages -gt 0 -and $stats.Published -ge $MaxMessages) {
            Write-Host "MaxMessages ($MaxMessages) reached. Stopping." -ForegroundColor Yellow
            break
        }
        if ($DryRun -and $stats.Published -ge 20) {
            Write-Host "DryRun limit (20) reached. Stopping." -ForegroundColor Yellow
            break
        }

        if ($line -match "^(\S+)\s+(\S+)\s+(.*)$") {
            $tsStr = $matches[1]
            $topic = $matches[2]
            $payload = $matches[3]

            $safetyCheck = Is-SafeTopic $topic
            if ($safetyCheck -ne "SAFE") {
                Add-SkipReason $safetyCheck
                continue
            }

            # Valid message to publish
            $time = $null
            try {
                # Format is usually 2026-06-16T12:12:32.4708000+03:00
                $time = [datetime]::Parse($tsStr)
            } catch {
                # Time parse failed, skip delay calculation
            }

            if ($DryRun) {
                Write-Host "[DRY-RUN] Would publish to $topic : $payload" -ForegroundColor Green
                $stats.Published++
            } else {
                if ($null -ne $lastTime -and $null -ne $time -and $Speed -gt 0) {
                    $delta = ($time - $lastTime).TotalMilliseconds
                    if ($delta -gt 0) {
                        $sleepMs = $delta / $Speed
                        if ($sleepMs -gt 0 -and $sleepMs -lt 10000) { # Max sleep 10s between messages to prevent hanging indefinitely
                            $sleepMsInt = [int][Math]::Max(0, [Math]::Round($sleepMs))
                            if ($sleepMsInt -gt 0) {
                                Start-Sleep -Milliseconds $sleepMsInt
                            }
                        }
                    }
                }

                # Publish using mosquitto_pub reading from stdin
                try {
                    # This safely avoids any escaping issues with quotes in the payload
                    $payload | & mosquitto_pub -h $Broker -p $Port -t $topic -s
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "Publish failed for topic $topic (Exit Code: $LASTEXITCODE)" -ForegroundColor Red
                    } else {
                        Write-Host "Published to $topic" -ForegroundColor DarkGray
                    }
                } catch {
                    Write-Host "Publish failed: $_" -ForegroundColor Red
                }
                
                $stats.Published++
            }
            $lastTime = $time
        } else {
            Add-SkipReason "Invalid Line Format"
        }
    }
} finally {
    $reader.Close()
    $reader.Dispose()
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " REPLAY SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total Lines Read   : $($stats.Read)"
Write-Host "Messages Published : $($stats.Published)"
Write-Host "Messages Skipped   : $($stats.Skipped)"
if ($stats.Skipped -gt 0) {
    Write-Host "Skip Reasons:"
    foreach ($reason in $stats.SkipReasons.Keys) {
        Write-Host "  - $($reason): $($stats.SkipReasons[$reason])"
    }
}
Write-Host "========================================" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "DryRun completed safely." -ForegroundColor Green
} else {
    Write-Host "Replay finished." -ForegroundColor Green
}
