# Restart the SCC unified server (default port 18788) in a robust way.
# Avoids `cmd /c start ...` quoting/UNC issues on Windows.

[CmdletBinding()]
param(
  [int]$Port = 18788,
  [string]$Host = "127.0.0.1",
  [int]$HealthTimeoutSec = 20
)

$ErrorActionPreference = "Stop"

function Get-ListenPid([int]$p) {
  try {
    return (Get-NetTCPConnection -LocalPort $p -State Listen | Select-Object -First 1 -ExpandProperty OwningProcess)
  } catch {
    return $null
  }
}

function Wait-Healthy([string]$baseUrl, [int]$timeoutSec) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-RestMethod -TimeoutSec 2 "$baseUrl/api/health"
      if ($resp -and $resp.status -eq "healthy") {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 300
      continue
    }
    Start-Sleep -Milliseconds 300
  }
  return $false
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$artifactsDir = Join-Path $repoRoot "artifacts"
New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null

$logPath = Join-Path $artifactsDir ("unified_server_{0}.log" -f $Port)
$pidPath = Join-Path $artifactsDir ("unified_server_{0}.pid" -f $Port)

$existingPid = Get-ListenPid $Port
if ($existingPid) {
  try {
    Stop-Process -Id $existingPid -Force -ErrorAction Stop
    Start-Sleep -Milliseconds 300
  } catch {
    Write-Warning "Failed to stop existing listener PID $existingPid: $($_.Exception.Message)"
  }
}

if (Test-Path $logPath) {
  Clear-Content -Path $logPath -ErrorAction SilentlyContinue
}

$python = (Get-Command python -ErrorAction Stop).Source
$scriptPath = Join-Path $repoRoot "tools\\unified_server\\start_unified_server.py"
if (!(Test-Path $scriptPath)) {
  throw "Missing: $scriptPath"
}

$baseUrl = "http://$Host`:$Port"

$proc = Start-Process -FilePath $python `
  -ArgumentList @("-u", $scriptPath) `
  -WorkingDirectory $repoRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $logPath `
  -RedirectStandardError $logPath `
  -PassThru

Set-Content -Path $pidPath -Value $proc.Id -Encoding ASCII

if (!(Wait-Healthy -baseUrl $baseUrl -timeoutSec $HealthTimeoutSec)) {
  Write-Error "Unified server did not become healthy within ${HealthTimeoutSec}s. See: $logPath"
}

Write-Output ("OK unified_server pid={0} url={1} log={2}" -f $proc.Id, $baseUrl, $logPath)

