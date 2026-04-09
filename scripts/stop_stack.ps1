$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $root ".stack.pids.json"

if (-not (Test-Path $statePath)) {
    Write-Warning "No PID file found at $statePath"
    Write-Host "Nothing to stop via PID file."
    exit 0
}

$state = Get-Content -Path $statePath -Raw | ConvertFrom-Json
$pids = @()
if ($state.gateway_pid) { $pids += [int]$state.gateway_pid }
if ($state.agent_pid) { $pids += [int]$state.agent_pid }

foreach ($pid in $pids) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "Stopped process PID $pid" -ForegroundColor Yellow
    } catch {
        Write-Warning "Could not stop PID $pid (it may already be closed)."
    }
}

Remove-Item -Path $statePath -Force -ErrorAction SilentlyContinue
Write-Host "Done." -ForegroundColor Green
