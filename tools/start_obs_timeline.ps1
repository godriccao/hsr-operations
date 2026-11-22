param(
    [Parameter(Mandatory = $true)]
    [int[]] $OffsetsMs
)

$ErrorActionPreference = 'Stop'
$previous = 0
if ($OffsetsMs.Count -gt 24) {
    throw 'Provide up to 24 observation offsets.'
}
foreach ($offset in $OffsetsMs) {
    if ($offset -le $previous -or $offset -gt 16000) {
        throw 'Observation offsets must be increasing milliseconds from 1 to 16000.'
    }
    $previous = $offset
}

$node = (Get-Command node -CommandType Application | Select-Object -First 1).Source
$observer = Join-Path $PSScriptRoot 'observe_obs_timeline.mjs'
$folder = Join-Path ([IO.Path]::GetTempPath()) ('hsr-obs-timeline-' + [Guid]::NewGuid().ToString('N'))
New-Item -Path $folder -ItemType Directory | Out-Null
$arguments = @(('"{0}"' -f $observer), ('"{0}"' -f $folder)) + @($OffsetsMs)
$ready = Join-Path $folder 'ready.json'
$timer = [Diagnostics.Stopwatch]::StartNew()
$process = Start-Process -FilePath $node -ArgumentList $arguments -WindowStyle Hidden -PassThru

try {
    while (-not (Test-Path -LiteralPath $ready)) {
        if ($process.HasExited) {
            throw "OBS observer exited before it was ready. Directory: $folder"
        }
        if ($timer.ElapsedMilliseconds -ge 5000) {
            throw "OBS observer did not become ready in five seconds. Directory: $folder"
        }
        Start-Sleep -Milliseconds 30
    }
    $details = Get-Content -LiteralPath $ready -Raw | ConvertFrom-Json
    if ($details.pid -ne $process.Id -or $process.HasExited) {
        throw "OBS observer readiness could not be verified. Directory: $folder"
    }
    [pscustomobject]@{
        folder = $folder
        pid = $process.Id
        readyAt = $details.readyAt
        startupMs = $timer.ElapsedMilliseconds
    } | ConvertTo-Json -Compress
} catch {
    if (-not $process.HasExited) {
        New-Item -Path (Join-Path $folder 'cancel') -ItemType File | Out-Null
    }
    throw
}
