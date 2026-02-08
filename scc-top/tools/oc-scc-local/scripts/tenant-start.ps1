$ErrorActionPreference = "Stop"

param(
  [Parameter(Mandatory = $true)][string]$TenantRoot
)

function Import-EnvFile([string]$path) {
  if (-not (Test-Path $path)) { throw "missing env file: $path" }
  $lines = Get-Content -ErrorAction Stop -Encoding UTF8 $path
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
    Set-Item -Path ("Env:{0}" -f $k) -Value $v
  }
}

$TenantRoot = (Resolve-Path $TenantRoot).Path
$envFile = Join-Path $TenantRoot "runtime.env"
Import-EnvFile $envFile

if (-not $env:GATEWAY_PORT) { throw "GATEWAY_PORT missing in $envFile" }
if (-not $env:EXEC_LOG_DIR) { $env:EXEC_LOG_DIR = (Join-Path $TenantRoot "artifacts\\executor_logs") }

$logDir = $env:EXEC_LOG_DIR
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$gatewayPid = Join-Path $logDir "gateway.pid"
$workersPid = Join-Path $logDir "ensure-workers.pid"
$gatewayOut = Join-Path $logDir "gateway.out.log"
$gatewayErr = Join-Path $logDir "gateway.err.log"
$workersOut = Join-Path $logDir "ensure-workers.out.log"
$workersErr = Join-Path $logDir "ensure-workers.err.log"

$repo = "C:\\scc\\scc-top\\tools\\oc-scc-local"

Push-Location $repo
try {
  $p = Start-Process -WindowStyle Hidden -PassThru -FilePath node -ArgumentList @("src\\gateway.mjs") `
    -WorkingDirectory $repo -RedirectStandardOutput $gatewayOut -RedirectStandardError $gatewayErr
  Set-Content -Encoding ASCII -NoNewline -Path $gatewayPid -Value ([string]$p.Id)

  $script = Join-Path $repo "scripts\\ensure-workers.ps1"
  $args = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$script)
  $p2 = Start-Process -WindowStyle Hidden -PassThru -FilePath powershell -ArgumentList $args `
    -WorkingDirectory $repo -RedirectStandardOutput $workersOut -RedirectStandardError $workersErr
  Set-Content -Encoding ASCII -NoNewline -Path $workersPid -Value ([string]$p2.Id)
} finally {
  Pop-Location
}

Write-Host "OK"
Write-Host "  tenant: $TenantRoot"
Write-Host "  health: http://127.0.0.1:$($env:GATEWAY_PORT)/health"
Write-Host "  board:  http://127.0.0.1:$($env:GATEWAY_PORT)/board"

