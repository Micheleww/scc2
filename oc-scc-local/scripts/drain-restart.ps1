$ErrorActionPreference = "Continue"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$Repo = Split-Path -Parent $PSScriptRoot
$LogDir = "C:\\scc\\artifacts\\executor_logs"
try { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null } catch {}
$Log = Join-Path $LogDir "drain_restart.log"

function Log([string]$msg) {
  $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
  try { Add-Content -Encoding UTF8 -Path $Log -Value $line } catch {}
  Write-Host $line
}

function Get-RunningCount() {
  try {
    $jobs = Invoke-RestMethod -UseBasicParsing "$Base/executor/jobs" -TimeoutSec 10
    # Only drain external jobs: internal jobs are tied to the gateway process and will be terminated on restart anyway.
    $running = @($jobs | Where-Object { $_.status -eq "running" -and $_.runner -eq "external" })
    return $running.Count
  } catch {
    return -1
  }
}

Log "drain-restart starting. base=$Base"

# Wait for all running jobs to finish to avoid killing work mid-flight.
$stableZero = 0
while ($true) {
  $n = Get-RunningCount
  if ($n -lt 0) {
    Log "gateway unreachable; waiting..."
    Start-Sleep -Seconds 5
    continue
  }
  Log "running_jobs=$n"
  if ($n -eq 0) {
    $stableZero += 1
    if ($stableZero -ge 3) { break } # 3 consecutive polls at 0
  } else {
    $stableZero = 0
  }
  Start-Sleep -Seconds 10
}

Log "drain reached. stopping daemon..."
try { & (Join-Path $Repo "scripts\\daemon-stop.ps1") } catch {}
Start-Sleep -Seconds 2

Log "starting daemon..."
try { & (Join-Path $Repo "scripts\\daemon-start.ps1") } catch {}

Log "done."
