$ErrorActionPreference = "Continue"

$LogDir = "C:\\scc\\artifacts\\executor_logs"
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

# Best-effort: stop any orphaned worker processes (spawned by ensure-workers).
function Stop-WorkersByScriptNeedle([string]$needle, [string]$label) {
  try {
    if (-not $needle) { return }
    $n = $needle.Replace("\\","/").ToLower()
    $procs = @()
    try {
      $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and ($_.CommandLine.ToLower().Replace("\\","/") -like "*$n*")
      }
    } catch { $procs = @() }
    foreach ($p in $procs) {
      try {
        $pid = [int]($p.ProcessId)
        if ($pid -gt 0) {
          Write-Host "Stopping $label pid=$pid"
          try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
        }
      } catch {}
    }
  } catch {}
}

Stop-WorkersByScriptNeedle "scripts/worker-codex.ps1" "codex worker"
Stop-WorkersByScriptNeedle "scripts/worker-opencodecli.ps1" "opencodecli worker"

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
