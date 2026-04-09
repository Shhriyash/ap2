$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-gateway\\Scripts\\python.exe"
$envFile = Join-Path $root ".env.gateway"

if (-not (Test-Path $venv)) {
    throw "Gateway venv not found. Run scripts/bootstrap.ps1 first."
}
if (-not (Test-Path $envFile)) {
    throw ".env.gateway not found. Copy from .env.gateway.example."
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match "^\s*#") { return }
    if ($_ -match "^\s*$") { return }
    $pair = $_ -split "=", 2
    if ($pair.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($pair[0], $pair[1])
    }
}

Push-Location (Join-Path $root "gateway_service")
& $venv -m uvicorn app.main:app --host $env:GATEWAY_HOST --port $env:GATEWAY_PORT --reload
Pop-Location
