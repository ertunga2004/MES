param(
    [string]$BrokerHost = "broker.emqx.io",
    [int]$Port = 1883,
    [string]$Topic = "sau/iot/mega/konveyor/vision/time_sync",
    [switch]$ApplySystemClock
)

$timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")

if ($ApplySystemClock) {
    $payloadObject = @{
        timestamp = $timestamp
        set_system_clock = $true
    }
    $payload = $payloadObject | ConvertTo-Json -Compress
} else {
    $payload = $timestamp
}

Write-Host "Publishing time sync payload: $payload"
$tempFile = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllText($tempFile, $payload, [System.Text.UTF8Encoding]::new($false))
    mosquitto_pub -h $BrokerHost -p $Port -t $Topic -f $tempFile
} finally {
    Remove-Item -LiteralPath $tempFile -ErrorAction SilentlyContinue
}
