$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $PSScriptRoot
$LogDir = "C:\\scc\\artifacts\\executor_logs"
try { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null } catch {}

$GatewayPid = Join-Path $LogDir "gateway.pid"
$WorkersPid = Join-Path $LogDir "ensure-workers.pid"
$GatewayOut = Join-Path $LogDir "gateway.out.log"
$GatewayErr = Join-Path $LogDir "gateway.err.log"
$WorkersOut = Join-Path $LogDir "ensure-workers.out.log"
$WorkersErr = Join-Path $LogDir "ensure-workers.err.log"

function Import-EnvFile([string]$path, [bool]$Override=$false) {
  try {
    if (-not (Test-Path $path)) { return }
    $lines = Get-Content -ErrorAction SilentlyContinue -Encoding UTF8 $path
    foreach ($line in $lines) {
      $s = [string]$line
      if (-not $s) { continue }
      $s = $s.Trim()
      if (-not $s) { continue }
      if ($s.StartsWith("#")) { continue }
      $idx = $s.IndexOf("=")
      if ($idx -le 0) { continue }
      $k = $s.Substring(0, $idx).Trim()
      $v = $s.Substring($idx + 1).Trim()
      if (-not $k) { continue }
      if (-not $Override) {
        # Don't override explicitly set env vars (defaults only).
        $existing = Get-Item -Path ("Env:{0}" -f $k) -ErrorAction SilentlyContinue
        if ($null -ne $existing -and $existing.Value) { continue }
      }
      Set-Item -Path ("Env:{0}" -f $k) -Value $v
    }
  } catch {}
}

function Read-Pid([string]$path) {
  try {
    if (-not (Test-Path $path)) { return $null }
    $raw = (Get-Content -Raw -ErrorAction SilentlyContinue $path).Trim()
    if (-not $raw) { return $null }
    $pid = [int]$raw
    if ($pid -le 0) { return $null }
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($p) { return $pid }
    return $null
  } catch { return $null }
}

function Write-Pid([string]$path, [int]$processId) {
  try { Set-Content -Encoding ASCII -NoNewline -Path $path -Value ([string]$processId) } catch {}
}

function Get-ListeningPidByPort([int]$port) {
  try {
    $c = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c -and $c.OwningProcess) { return [int]$c.OwningProcess }
  } catch {}
  try {
    $line = (netstat -ano | Select-String -Pattern (":$port\\s+LISTENING\\s+\\d+")).ToString()
    if ($line) {
      $processId = ($line -split "\\s+")[-1]
      if ($processId) { return [int]$processId }
    }
  } catch {}
  return $null
}

function Start-Gateway {
  $existing = Read-Pid $GatewayPid
  if ($existing) {
    $p = Get-Process -Id $existing -ErrorAction SilentlyContinue
    if ($p) {
      Write-Host "gateway already running pid=$existing"
      return
    }
    # Stale pidfile; recover.
    try { Remove-Item -Force -ErrorAction SilentlyContinue $GatewayPid } catch {}
  }

  # Load env once (no Windows-level install; fully local config).
  $envFile = Join-Path $Repo "config\\runtime.env"
  $envExample = Join-Path $Repo "config\\runtime.env.example"
  # Import example first, then real env so local config wins (fail-closed).
  Import-EnvFile $envExample $false
  Import-EnvFile $envFile $true

  # Ensure JS deps are installed; gateway is ESM and will hard-fail on missing packages.
  try {
    $needInstall = $false
    if (-not (Test-Path (Join-Path $Repo "node_modules"))) { $needInstall = $true }
    if (-not (Test-Path (Join-Path $Repo "node_modules\\http-proxy"))) { $needInstall = $true }
    if ($needInstall -and (Test-Path (Join-Path $Repo "package-lock.json"))) {
      Write-Host "installing gateway deps (npm ci)..."
      Push-Location $Repo
      try { npm ci | Out-Null } finally { Pop-Location }
    }
  } catch {}

  $listening = Get-ListeningPidByPort 18788
  if ($listening) {
    Write-Host "gateway already listening on 18788 pid=$listening"
    Write-Pid $GatewayPid $listening
    return
  }

  Push-Location $Repo
  try {
    # Align defaults to "fully automated" run.
    if (-not $env:GATEWAY_PORT) { $env:GATEWAY_PORT = "18788" }
    if (-not $env:EXEC_CONCURRENCY_CODEX) { $env:EXEC_CONCURRENCY_CODEX = "1" }
    if (-not $env:EXEC_CONCURRENCY_OPENCODE) { $env:EXEC_CONCURRENCY_OPENCODE = "10" }
    if (-not $env:EXEC_TIMEOUT_CODEX_MS) { $env:EXEC_TIMEOUT_CODEX_MS = "1200000" }
    if (-not $env:EXEC_TIMEOUT_OPENCODE_MS) { $env:EXEC_TIMEOUT_OPENCODE_MS = "1200000" }
    if (-not $env:OPENCODE_MODEL) { $env:OPENCODE_MODEL = "opencode/kimi-k2.5-free" }
    if (-not $env:MODEL_POOL_FREE) { $env:MODEL_POOL_FREE = "opencode/kimi-k2.5-free" }
    if (-not $env:MODEL_POOL_VISION) { $env:MODEL_POOL_VISION = "opencode/kimi-k2.5-free" }
    if (-not $env:DESIRED_RATIO_CODEX) { $env:DESIRED_RATIO_CODEX = "0" }
    if (-not $env:DESIRED_RATIO_OPENCODECLI) { $env:DESIRED_RATIO_OPENCODECLI = "10" }
    if (-not $env:EXTERNAL_MAX_CODEX) { $env:EXTERNAL_MAX_CODEX = "0" }
    if (-not $env:EXTERNAL_MAX_OPENCODECLI) { $env:EXTERNAL_MAX_OPENCODECLI = "10" }

    $p = Start-Process -WindowStyle Hidden -PassThru -FilePath node -ArgumentList @("src\\gateway.mjs") `
      -WorkingDirectory $Repo -RedirectStandardOutput $GatewayOut -RedirectStandardError $GatewayErr
    Write-Pid $GatewayPid $p.Id
    Write-Host "gateway started pid=$($p.Id) port=$($env:GATEWAY_PORT)"
  } finally {
    Pop-Location
  }
}

function Start-EnsureWorkers {
  $existing = Read-Pid $WorkersPid
  if ($existing) {
    $p = Get-Process -Id $existing -ErrorAction SilentlyContinue
    if ($p) {
      Write-Host "ensure-workers already running pid=$existing"
      return
    }
    # Stale pidfile; recover.
    try { Remove-Item -Force -ErrorAction SilentlyContinue $WorkersPid } catch {}
  }

  # Keep env consistent with gateway.
  $envFile = Join-Path $Repo "config\\runtime.env"
  $envExample = Join-Path $Repo "config\\runtime.env.example"
  Import-EnvFile $envExample $false
  Import-EnvFile $envFile $true

  $lockFile = Join-Path $LogDir "ensure_workers.lock.json"
  try {
    if (Test-Path $lockFile) {
      $raw = Get-Content -Raw -ErrorAction SilentlyContinue $lockFile
      if ($raw) {
        $lock = $raw | ConvertFrom-Json
        $processId = [int]($lock.pid)
        if ($processId -gt 0) {
          $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
          if ($p) {
            Write-Host "ensure-workers already running (lock pid=$processId)"
            Write-Pid $WorkersPid $processId
            return
          }
        }
      }
    }
  } catch {}

  $script = Join-Path $Repo "scripts\\ensure-workers.ps1"
  $args = @(
    "-NoProfile",
    "-ExecutionPolicy","Bypass",
    "-File", $script
  )

  $p = Start-Process -WindowStyle Hidden -PassThru -FilePath powershell -ArgumentList $args `
    -WorkingDirectory $Repo -RedirectStandardOutput $WorkersOut -RedirectStandardError $WorkersErr
  Write-Pid $WorkersPid $p.Id
  Write-Host "ensure-workers started pid=$($p.Id)"
}

Start-Gateway
Start-EnsureWorkers

Write-Host "OK. Health:"
Write-Host "  http://127.0.0.1:18788/pools"
Write-Host "  http://127.0.0.1:18788/board"
