<#
.SYNOPSIS
    Run Internet Monitor as a quick, portable connectivity test for a
    single physical location, with an isolated dataset per site and an
    auto-saved report when you're done. Windows equivalent of test-site.sh.

.DESCRIPTION
    Save this file at the ROOT of your internet-monitor project (next to
    backend\, frontend\, cli\) and run it from there.

    Each run gets its own SQLite database under .\tmp\<name>\ (inside this
    project, not your user profile) so the gateway target is freshly
    auto-detected for *that* network, and stats never mix between
    locations. .\tmp\ is git-ignored already (see .gitignore). On Ctrl+C,
    a CSV + JSON report is saved to that same folder before the server
    stops.

.PARAMETER SiteName
    A label for this test session, e.g. "Client HQ - Floor 3". If omitted,
    defaults to a timestamp-based name.

.EXAMPLE
    .\test-site.ps1 "Client HQ - Floor 3"

.EXAMPLE
    .\test-site.ps1

.NOTES
    If Windows refuses to run this at all ("running scripts is disabled
    on this system"), either run it as:
        powershell -ExecutionPolicy Bypass -File .\test-site.ps1 "Site Name"
    or, once, allow local scripts for your own account:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>
param(
    [Parameter(Position = 0)]
    [string]$SiteName = "site-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
)

$ErrorActionPreference = "Stop"

$ScriptDir  = $PSScriptRoot
$BackendDir = Join-Path $ScriptDir "backend"
$SafeName   = ($SiteName -replace '[ /\\]', '-')
$DataDir    = Join-Path (Join-Path $ScriptDir "tmp") $SafeName
$Port       = if ($env:INTERNET_MONITOR_PORT) { $env:INTERNET_MONITOR_PORT } else { "8765" }

$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "No venv found at $BackendDir\.venv - set that up first (see README)."
    exit 1
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:INTERNET_MONITOR_DATA_DIR = $DataDir

Write-Host "==> Testing:  $SiteName"
Write-Host "==> Data dir: $DataDir"

$serverProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port) `
    -WorkingDirectory $BackendDir `
    -NoNewWindow -PassThru

function Save-Report {
    Write-Host ""
    Write-Host "==> Saving report for `"$SiteName`"..."
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/export/measurements.csv" `
            -OutFile (Join-Path $DataDir "measurements.csv") -ErrorAction SilentlyContinue | Out-Null
    } catch {}
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/export/report.json?range=24h" `
            -OutFile (Join-Path $DataDir "report.json") -ErrorAction SilentlyContinue | Out-Null
    } catch {}
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "    $DataDir\measurements.csv"
    Write-Host "    $DataDir\report.json"
}

try {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:$Port" -ErrorAction SilentlyContinue

    Write-Host "==> Dashboard open in your browser. Let it run a few minutes, then Ctrl+C to finish and save the report."
    Wait-Process -Id $serverProcess.Id
}
finally {
    Save-Report
}
