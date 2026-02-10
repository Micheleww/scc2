$ErrorActionPreference = "Stop"

$repo = $env:SCC_REPO
if (-not $repo) {
  $ocRoot = Split-Path -Parent $PSScriptRoot
  $repoRoot = Split-Path -Parent $ocRoot
  $repo = Join-Path $repoRoot "scc-top"
}
if (-not (Test-Path $repo)) { throw "SCC repo not found: $repo (set SCC_REPO to override)" }

$compose = Join-Path $repo "docker-compose.scc.yml"
if (-not (Test-Path $compose)) { throw "Compose file not found: $compose" }

$port = $env:SCC_HOST_PORT
if (-not $port) { $port = "18789" }

Push-Location $repo
try {
  $env:SCC_HOST_PORT = $port
  Write-Host "Starting SCC Docker (host port $port -> container 18788)"
  docker compose -f $compose up -d
} finally {
  Pop-Location
}

