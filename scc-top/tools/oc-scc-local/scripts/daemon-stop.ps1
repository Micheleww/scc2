$ErrorActionPreference = "Continue"

$Repo = Split-Path -Parent $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $Repo "..\\..\\..")
$LogDir = if ($env:EXEC_LOG_DIR) { $env:EXEC_LOG_DIR } else { (Join-Path $RepoRoot "artifacts\\executor_logs") }
$GatewayPid = Join-Path $LogDir "gateway.pid"
$WorkersPid = Join-Path $LogDir "ensure-workers.pid"

function Stop-ByPidFile([string]$pidFile, [string]$label) {
  try {
    if (-not (Test-Path $pidFile)) { return }
    $raw = (Get-Content -Raw -ErrorAction SilentlyContinue $pidFile).Trim()
    if (-not $raw) { return }
    $pid = [int]$raw
    if ($pid -le 0) { return }
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($p) {
      Write-Host "Stopping $label pid=$pid"
      try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
    }
    try { Remove-Item -Force -ErrorAction SilentlyContinue $pidFile } catch {}
  } catch {}
}

Stop-ByPidFile $WorkersPid "ensure-workers"
Stop-ByPidFile $GatewayPid "gateway"

# Fallback: if pidfile was stale, stop the process listening on 18788.
try {
  $c = Get-NetTCPConnection -State Listen -LocalPort 18788 -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c -and $c.OwningProcess) {
    $pid2 = [int]$c.OwningProcess
    $p2 = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
    if ($p2) {
      Write-Host "Stopping gateway (port 18788) pid=$pid2"
      try { Stop-Process -Id $pid2 -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
} catch {}

Write-Host "Stopped."
