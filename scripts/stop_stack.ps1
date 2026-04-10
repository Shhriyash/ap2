param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $root ".stack.pids.json"
$envFile = Join-Path $root ".env.agent"

function Get-PortValue {
    param(
        [string]$Key,
        [int]$DefaultValue
    )
    if (-not (Test-Path $envFile)) {
        return $DefaultValue
    }
    $line = Get-Content -Path $envFile | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) {
        return $DefaultValue
    }
    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) {
        return $DefaultValue
    }
    $raw = $parts[1].Trim()
    $port = 0
    if ([int]::TryParse($raw, [ref]$port)) {
        return $port
    }
    return $DefaultValue
}

function Stop-ListeningProcessOnPort {
    param([int]$Port)
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (-not $listeners -or $listeners.Count -eq 0) {
        return
    }
    $ownerPids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ownerPid in $ownerPids) {
        try {
            Stop-Process -Id $ownerPid -Force -ErrorAction Stop
            if (-not $Quiet) {
                Write-Host "Stopped listener PID $ownerPid on port $Port" -ForegroundColor Yellow
            }
        } catch {
            if (-not $Quiet) {
                Write-Warning "Could not stop listener PID $ownerPid on port $Port."
            }
        }
    }
}

if (Test-Path $statePath) {
    $state = Get-Content -Path $statePath -Raw | ConvertFrom-Json
    $pids = @()
    if ($state.gateway_pid) { $pids += [int]$state.gateway_pid }
    if ($state.agent_pid) { $pids += [int]$state.agent_pid }

    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            if (-not $Quiet) {
                Write-Host "Stopped process PID $procId" -ForegroundColor Yellow
            }
        } catch {
            if (-not $Quiet) {
                Write-Warning "Could not stop PID $procId (it may already be closed)."
            }
        }
    }
}

$agentPort = Get-PortValue -Key "AGENT_PORT" -DefaultValue 8000
$gatewayPort = Get-PortValue -Key "GATEWAY_PORT" -DefaultValue 8100
Stop-ListeningProcessOnPort -Port $agentPort
Stop-ListeningProcessOnPort -Port $gatewayPort

Remove-Item -Path $statePath -Force -ErrorAction SilentlyContinue
if (-not $Quiet) {
    Write-Host "Done." -ForegroundColor Green
}
