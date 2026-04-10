param(
    [string]$AgentUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-agent\\Scripts\\python.exe"
$envFile = Join-Path $root ".env.agent"
$scriptPath = Join-Path $PSScriptRoot "cli_voice.py"

if (-not (Test-Path $venv)) {
    throw "Agent venv not found. Run scripts/bootstrap.ps1 first."
}
if (-not (Test-Path $envFile)) {
    throw ".env.agent not found. Copy from .env.agent.example."
}
if (-not (Test-Path $scriptPath)) {
    throw "Voice CLI script not found: $scriptPath"
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match "^\s*#") { return }
    if ($_ -match "^\s*$") { return }
    $pair = $_ -split "=", 2
    if ($pair.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($pair[0], $pair[1])
    }
}

$args = @($scriptPath, "--agent-url", $AgentUrl)

& $venv @args
