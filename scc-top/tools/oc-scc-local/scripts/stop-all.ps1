$ErrorActionPreference = "Stop"

function Stop-ListenersOnPort([int]$port) {
  $procIds = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($p in $procIds) {
    try {
      Stop-Process -Id $p -Force -ErrorAction Stop
      Write-Host "Stopped PID $p (port $port)"
    } catch {
      Write-Warning "Failed to stop PID $p (port $port): $($_.Exception.Message)"
    }
  }
}

Write-Host "== Stop Gateway (18788) =="
Stop-ListenersOnPort 18788

Write-Host "== Stop OpenCode upstream (18790) =="
Stop-ListenersOnPort 18790

Write-Host "== Stop SCC (Docker) =="
$repo = $env:SCC_REPO
if (-not $repo) {
  $pkg = Split-Path -Parent $PSScriptRoot
  $repoRoot = Resolve-Path (Join-Path $pkg "..\\..\\..")
  $repo = Join-Path $repoRoot "scc-top"
}
$compose = Join-Path $repo "docker-compose.scc.yml"
if (Test-Path $compose) {
  Push-Location $repo
  try {
    $env:SCC_HOST_PORT = $env:SCC_HOST_PORT
    if (-not $env:SCC_HOST_PORT) { $env:SCC_HOST_PORT = "18789" }
    docker compose -f $compose down | Out-Null
    Write-Host "SCC compose down issued"
  } catch {
    Write-Warning "Failed to stop SCC (Docker may be unavailable): $($_.Exception.Message)"
  } finally {
    Pop-Location
  }
}
