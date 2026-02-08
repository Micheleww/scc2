$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$DesiredCodex = if ($env:DESIRED_CODEX) { [int]$env:DESIRED_CODEX } else { 4 }
$DesiredOccli = if ($env:DESIRED_OPENCODECLI) { [int]$env:DESIRED_OPENCODECLI } else { 6 }
$MinRunning = if ($env:MIN_RUNNING) { [int]$env:MIN_RUNNING } else { 4 }
$SeenWindowMs = if ($env:SEEN_WINDOW_MS) { [int]$env:SEEN_WINDOW_MS } else { 120000 }
$TickSeconds = if ($env:TICK_SECONDS) { [int]$env:TICK_SECONDS } else { 20 }

$ModelsCodex = $env:WORKER_MODELS_CODEX
if (-not $ModelsCodex) { $ModelsCodex = "gpt-5.1-codex-max,gpt-5.2" }
$ModelsOc = $env:WORKER_MODELS_OPENCODECLI
if (-not $ModelsOc) { $ModelsOc = "opencode/glm-4.7-free,opencode/kimi-k2.5-free,opencode/gpt-5-nano,opencode/minimax-m2.1-free,opencode/trinity-large-preview-free,opencode/big-pickle" }

$repo = Split-Path -Parent $PSScriptRoot
$WorkerCodex = Join-Path $repo "scripts\\worker-codex.ps1"
$WorkerOccli = Join-Path $repo "scripts\\worker-opencodecli.ps1"

Write-Host "ensure-workers starting base=$Base desired codex=$DesiredCodex occli=$DesiredOccli minRunning=$MinRunning tick=${TickSeconds}s"

$repoRoot = Resolve-Path (Join-Path $repo "..\\..\\..")
$lockDir = if ($env:EXEC_LOG_DIR) { $env:EXEC_LOG_DIR } else { (Join-Path $repoRoot "artifacts\\executor_logs") }
$lockFile = Join-Path $lockDir "ensure_workers.lock.json"
try { New-Item -ItemType Directory -Force -Path $lockDir | Out-Null } catch {}
try {
  if (Test-Path $lockFile) {
    $raw = Get-Content -Raw -ErrorAction SilentlyContinue $lockFile
    if ($raw) {
      try {
        $lock = $raw | ConvertFrom-Json
        $pid = [int]($lock.pid)
        $started = [string]($lock.startedAt)
        if ($pid -gt 0) {
          $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
          if ($p) {
            Write-Host "Another ensure-workers instance is running (pid=$pid startedAt=$started). Exiting."
            exit 0
          }
        }
      } catch {}
    }
  }
  @{ pid=$PID; startedAt=(Get-Date).ToString("o") } | ConvertTo-Json -Compress | Set-Content -Encoding UTF8 $lockFile
} catch {}

function Spawn-Codex([int]$n) {
  for ($i = 1; $i -le $n; $i++) {
    $name = "autoscale-codex-" + (Get-Date -Format "HHmmss") + "-$i"
    Start-Process -WindowStyle Hidden -FilePath powershell -ArgumentList @(
      "-NoProfile",
      "-ExecutionPolicy","Bypass",
      "-Command",
      "`$env:WORKER_NAME='$name'; `$env:WORKER_MODELS='$ModelsCodex'; & '$WorkerCodex'"
    ) | Out-Null
  }
}

function Spawn-Occli([int]$n) {
  for ($i = 1; $i -le $n; $i++) {
    $name = "autoscale-occli-" + (Get-Date -Format "HHmmss") + "-$i"
    Start-Process -WindowStyle Hidden -FilePath powershell -ArgumentList @(
      "-NoProfile",
      "-ExecutionPolicy","Bypass",
      "-Command",
      "`$env:WORKER_NAME='$name'; `$env:WORKER_MODELS='$ModelsOc'; & '$WorkerOccli'"
    ) | Out-Null
  }
}

while ($true) {
  try {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $workersJson = (Invoke-WebRequest -UseBasicParsing "$Base/executor/workers" -TimeoutSec 15).Content | ConvertFrom-Json
    $workers = @($workersJson)
    $active = $workers | Where-Object { $_.lastSeen -ge ($now - $SeenWindowMs) }

    $activeCodex = @($active | Where-Object { ($_.executors -contains "codex") }).Count
    $activeOccli = @($active | Where-Object { ($_.executors -contains "opencodecli") }).Count

    $jobs = Invoke-RestMethod -UseBasicParsing "$Base/executor/jobs"
    $running = @($jobs | Where-Object { $_.status -eq "running" }).Count

    $needCodex = [math]::Max(0, $DesiredCodex - $activeCodex)
    $needOccli = [math]::Max(0, $DesiredOccli - $activeOccli)

    if ($running -lt $MinRunning) {
      # Prefer adding codex workers when we're under-running; occli is supportive.
      $needCodex = [math]::Max($needCodex, 1)
    }

    if ($needCodex -gt 0) { Spawn-Codex $needCodex }
    if ($needOccli -gt 0) { Spawn-Occli $needOccli }

    Write-Host ("[{0}] active codex={1}/{2} occli={3}/{4} runningJobs={5} spawned codex={6} occli={7}" -f (Get-Date -Format "HH:mm:ss"), $activeCodex, $DesiredCodex, $activeOccli, $DesiredOccli, $running, $needCodex, $needOccli)
  } catch {
    Write-Host ("[{0}] ensure-workers error: {1}" -f (Get-Date -Format "HH:mm:ss"), $_.Exception.Message)
  }
  Start-Sleep -Seconds $TickSeconds
}
