param(
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-agent\\Scripts\\python.exe"
$envFile = Join-Path $root ".env.agent"

if (-not (Test-Path $venv)) {
    throw "Agent venv not found. Run scripts/bootstrap.ps1 first."
}
if (-not (Test-Path $envFile)) {
    throw ".env.agent not found. Copy from .env.agent.example."
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match "^\s*#") { return }
    if ($_ -match "^\s*$") { return }
    $pair = $_ -split "=", 2
    if ($pair.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($pair[0], $pair[1])
    }
}

Push-Location (Join-Path $root "agent_service")
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $env:AGENT_HOST, "--port", $env:AGENT_PORT)
if ($Reload) {
    $uvicornArgs += "--reload"
}
& $venv @uvicornArgs
Pop-Location
