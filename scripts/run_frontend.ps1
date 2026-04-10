param(
    [int]$Port = 5173
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $root "onboarding_dashboard"

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

$baseUrl = "http://localhost:$Port"

Write-Host "Starting Agent2Pay frontend server..." -ForegroundColor Cyan
Write-Host "Serving directory: $frontendDir"
Write-Host ""
Write-Host "Open these URLs:" -ForegroundColor Green
Write-Host "- Landing:    $baseUrl/index.html"
Write-Host "- Signup:     $baseUrl/signup.html"
Write-Host "- Agent Logs: $baseUrl/agent-logs.html"
Write-Host ""
Write-Host "Shortcut URL: $baseUrl" -ForegroundColor Yellow
Write-Host ""

python -m http.server $Port --directory $frontendDir
