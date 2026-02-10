$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$DesiredCodex = if ($env:DESIRED_CODEX) { [int]$env:DESIRED_CODEX } else { 4 }
$DesiredOccli = if ($env:DESIRED_OPENCODECLI) { [int]$env:DESIRED_OPENCODECLI } else { 6 }
$MinRunning = if ($env:MIN_RUNNING) { [int]$env:MIN_RUNNING } else { 4 }
$SeenWindowMs = if ($env:SEEN_WINDOW_MS) { [int]$env:SEEN_WINDOW_MS } else { 120000 }
$TickSeconds = if ($env:TICK_SECONDS) { [int]$env:TICK_SECONDS } else { 20 }

$ModelsCodex = $env:WORKER_MODELS_CODEX
if (-not $ModelsCodex) { $ModelsCodex = "gpt-5.3-codex,gpt-5.2,gpt-5.1-codex-max" }
$ModelsOc = $env:WORKER_MODELS_OPENCODECLI
if (-not $ModelsOc) { $ModelsOc = "opencode/glm-4.7-free,opencode/kimi-k2.5-free,opencode/gpt-5-nano,opencode/minimax-m2.1-free,opencode/trinity-large-preview-free,opencode/big-pickle" }

$MaxSpawnCodexPerTick = if ($env:MAX_SPAWN_CODEX_PER_TICK) { [int]$env:MAX_SPAWN_CODEX_PER_TICK } else { 2 }
$MaxSpawnOccliPerTick = if ($env:MAX_SPAWN_OPENCODECLI_PER_TICK) { [int]$env:MAX_SPAWN_OPENCODECLI_PER_TICK } else { 4 }

$ScaleDownEnabled = if ($env:SCALE_DOWN_ENABLED) { [string]$env:SCALE_DOWN_ENABLED } else { "true" }
$ScaleDownEnabled = $ScaleDownEnabled.ToLower() -ne "false"
$MaxPruneCodexPerTick = if ($env:MAX_PRUNE_CODEX_PER_TICK) { [int]$env:MAX_PRUNE_CODEX_PER_TICK } else { 2 }
$MaxPruneOccliPerTick = if ($env:MAX_PRUNE_OPENCODECLI_PER_TICK) { [int]$env:MAX_PRUNE_OPENCODECLI_PER_TICK } else { 3 }
$PruneOnlyWhenIdle = if ($env:PRUNE_ONLY_WHEN_IDLE) { [string]$env:PRUNE_ONLY_WHEN_IDLE } else { "true" }
$PruneOnlyWhenIdle = $PruneOnlyWhenIdle.ToLower() -ne "false"
$PruneGraceMs = if ($env:PRUNE_GRACE_MS) { [int]$env:PRUNE_GRACE_MS } else { 180000 }

$repo = Split-Path -Parent $PSScriptRoot
$WorkerCodex = Join-Path $repo "scripts\\worker-codex.ps1"
$WorkerOccli = Join-Path $repo "scripts\\worker-opencodecli.ps1"

Write-Host "ensure-workers starting base=$Base desired codex=$DesiredCodex occli=$DesiredOccli minRunning=$MinRunning tick=${TickSeconds}s"

$repoRoot = Split-Path -Parent $repo
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
    $suffix = ([Guid]::NewGuid().ToString("n")).Substring(0, 6)
    $name = "autoscale-codex-" + (Get-Date -Format "HHmmss") + "-$i-$suffix"
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
    $suffix = ([Guid]::NewGuid().ToString("n")).Substring(0, 6)
    $name = "autoscale-occli-" + (Get-Date -Format "HHmmss") + "-$i-$suffix"
    Start-Process -WindowStyle Hidden -FilePath powershell -ArgumentList @(
      "-NoProfile",
      "-ExecutionPolicy","Bypass",
      "-Command",
      "`$env:WORKER_NAME='$name'; `$env:WORKER_MODELS='$ModelsOc'; & '$WorkerOccli'"
    ) | Out-Null
  }
}

function Prune-Workers([string]$scriptPath, [int]$count, [int]$maxPerTick, [int]$runningJobs) {
  if (-not $ScaleDownEnabled) { return 0 }
  if ($count -le 0) { return 0 }
  if ($PruneOnlyWhenIdle -and $runningJobs -gt 0) { return 0 }

  $toKill = [math]::Min($count, $maxPerTick)
  if ($toKill -le 0) { return 0 }

  $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $needle = $scriptPath.Replace("\\","/").ToLower()

  $procs = @()
  try {
    $procs = Get-CimInstance Win32_Process | Where-Object {
      $_.CommandLine -and ($_.CommandLine.ToLower().Replace("\\","/") -like "*$needle*")
    } | ForEach-Object {
      $pid = $_.ProcessId
      $cd = $_.CreationDate
      $createdMs = 0
      try { $createdMs = [DateTimeOffset]([Management.ManagementDateTimeConverter]::ToDateTime($cd)).ToUnixTimeMilliseconds() } catch {}
      [PSCustomObject]@{ ProcessId=$pid; CreatedMs=$createdMs; CommandLine=$_.CommandLine }
    }
  } catch {
    return 0
  }

  # Only prune processes older than a grace window to avoid killing freshly spawned workers.
  $candidates = $procs | Where-Object { $_.ProcessId -and ($_.CreatedMs -gt 0) -and ($now - $_.CreatedMs -ge $PruneGraceMs) } | Sort-Object CreatedMs
  $killed = 0
  foreach ($p in $candidates) {
    if ($killed -ge $toKill) { break }
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      $killed += 1
    } catch {}
  }
  return $killed
}

while ($true) {
  try {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()

    $workersResp = Invoke-RestMethod -UseBasicParsing "$Base/executor/workers" -TimeoutSec 15
    $workers = @()
    if ($workersResp -and ($workersResp.PSObject.Properties.Name -contains "value")) {
      $workers = @($workersResp.value)
    } else {
      $workers = @($workersResp)
    }
    $active = $workers | Where-Object { $_.lastSeen -ge ($now - $SeenWindowMs) }

    $activeCodex = @($active | Where-Object { ($_.executors -contains "codex") }).Count
    $activeOccli = @($active | Where-Object { ($_.executors -contains "opencodecli") }).Count

    $jobsResp = Invoke-RestMethod -UseBasicParsing "$Base/executor/jobs" -TimeoutSec 15
    $jobs = @()
    if ($jobsResp -and ($jobsResp.PSObject.Properties.Name -contains "value")) {
      $jobs = @($jobsResp.value)
    } else {
      $jobs = @($jobsResp)
    }
    $running = @($jobs | Where-Object { $_.status -eq "running" }).Count

    $needCodex = [math]::Max(0, $DesiredCodex - $activeCodex)
    $needOccli = [math]::Max(0, $DesiredOccli - $activeOccli)

    if ($running -lt $MinRunning) {
      # If we're under-running and have no active codex workers, bring at least one up.
      # Do not keep spawning codex indefinitely when desired count is already met.
      if ($activeCodex -lt 1) { $needCodex = [math]::Max($needCodex, 1) }
    }

    # Hard safety cap to prevent runaway spawns if the gateway response shape changes.
    $needCodex = [math]::Min($needCodex, $MaxSpawnCodexPerTick)
    $needOccli = [math]::Min($needOccli, $MaxSpawnOccliPerTick)

    if ($needCodex -gt 0) { Spawn-Codex $needCodex }
    if ($needOccli -gt 0) { Spawn-Occli $needOccli }

    $extraCodex = [math]::Max(0, $activeCodex - $DesiredCodex)
    $extraOccli = [math]::Max(0, $activeOccli - $DesiredOccli)
    $prunedCodex = Prune-Workers $WorkerCodex $extraCodex $MaxPruneCodexPerTick $running
    $prunedOccli = Prune-Workers $WorkerOccli $extraOccli $MaxPruneOccliPerTick $running

    Write-Host ("[{0}] active codex={1}/{2} occli={3}/{4} runningJobs={5} spawned codex={6} occli={7} pruned codex={8} occli={9}" -f (Get-Date -Format "HH:mm:ss"), $activeCodex, $DesiredCodex, $activeOccli, $DesiredOccli, $running, $needCodex, $needOccli, $prunedCodex, $prunedOccli)
  } catch {
    Write-Host ("[{0}] ensure-workers error: {1}" -f (Get-Date -Format "HH:mm:ss"), $_.Exception.Message)
  }
  Start-Sleep -Seconds $TickSeconds
}
