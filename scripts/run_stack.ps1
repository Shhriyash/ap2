$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$gatewayScript = Join-Path $PSScriptRoot "run_gateway.ps1"
$agentScript = Join-Path $PSScriptRoot "run_agent.ps1"

if (-not (Test-Path $gatewayScript)) {
    throw "Missing script: $gatewayScript"
}
if (-not (Test-Path $agentScript)) {
    throw "Missing script: $agentScript"
}

Write-Host "Starting gateway service in a new PowerShell window..." -ForegroundColor Cyan
$gatewayProc = Start-Process \
    -FilePath "powershell.exe" \
    -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", $gatewayScript) \
    -WorkingDirectory $root \
    -PassThru

Write-Host "Starting agent service in a new PowerShell window..." -ForegroundColor Cyan
$agentProc = Start-Process \
    -FilePath "powershell.exe" \
    -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", $agentScript) \
    -WorkingDirectory $root \
    -PassThru

$statePath = Join-Path $root ".stack.pids.json"
$state = @{
    gateway_pid = $gatewayProc.Id
    agent_pid = $agentProc.Id
    started_at = (Get-Date).ToString("o")
}
$state | ConvertTo-Json | Set-Content -Path $statePath -Encoding UTF8

Write-Host "Services launched." -ForegroundColor Green
Write-Host "Gateway window PID: $($gatewayProc.Id)"
Write-Host "Agent window PID:   $($agentProc.Id)"
Write-Host "PID file: $statePath"
Write-Host "Use scripts/stop_stack.ps1 to stop both windows quickly."
