param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$agentVenv = Join-Path $root ".venv-agent"
$gatewayVenv = Join-Path $root ".venv-gateway"

function New-Or-RebuildVenv {
    param(
        [string]$Path
    )
    if ($Recreate -and (Test-Path $Path)) {
        Remove-Item -Recurse -Force -LiteralPath $Path
    }
    if (-not (Test-Path $Path)) {
        python -m venv $Path
    }
}

function Install-Req {
    param(
        [string]$VenvPath,
        [string]$ReqPath
    )
    $pip = Join-Path $VenvPath "Scripts\\pip.exe"
    $reqDir = Split-Path -Parent $ReqPath
    $reqFile = Split-Path -Leaf $ReqPath
    & $pip install --upgrade pip
    Push-Location $reqDir
    try {
        & $pip install -r $reqFile
    }
    finally {
        Pop-Location
    }
}

New-Or-RebuildVenv -Path $agentVenv
New-Or-RebuildVenv -Path $gatewayVenv

Install-Req -VenvPath $agentVenv -ReqPath (Join-Path $root "agent_service\\requirements.txt")
Install-Req -VenvPath $gatewayVenv -ReqPath (Join-Path $root "gateway_service\\requirements.txt")

Write-Host "Bootstrap complete."
Write-Host "Agent venv: $agentVenv"
Write-Host "Gateway venv: $gatewayVenv"
