$ErrorActionPreference = "Stop"

param(
  [Parameter(Mandatory = $true)][string]$TenantRoot
)

$TenantRoot = (Resolve-Path $TenantRoot).Path
$envFile = Join-Path $TenantRoot "runtime.env"
if (-not (Test-Path $envFile)) { throw "missing env file: $envFile" }

$execLogDir = Join-Path $TenantRoot "artifacts\\executor_logs"
$gatewayPid = Join-Path $execLogDir "gateway.pid"
$workersPid = Join-Path $execLogDir "ensure-workers.pid"

function Stop-PidFile([string]$path, [string]$name) {
  if (-not (Test-Path $path)) { return }
  try {
    $raw = (Get-Content -Raw $path).Trim()
    if (-not $raw) { return }
    $pid = [int]$raw
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($p) {
      Write-Host "Stopping $name pid=$pid"
      Stop-Process -Id $pid -Force
    }
  } catch {}
  try { Remove-Item -Force $path } catch {}
}

Stop-PidFile $workersPid "ensure-workers"
Stop-PidFile $gatewayPid "gateway"

Write-Host "OK"

