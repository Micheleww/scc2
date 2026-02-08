$ErrorActionPreference = "Stop"

$Base = $env:SCC_GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$PollSeconds = 5
$IdleConsecutive = 2

Write-Host "restart-when-idle: waiting for gateway to become idle..."
Write-Host "  base=$Base"
Write-Host "  poll=$PollSeconds sec, idleConsecutive=$IdleConsecutive"

$idleHits = 0
while ($true) {
  try {
    $p = Invoke-RestMethod "$Base/pools"
    $running = [int]($p.jobs.byStatus.running)
    $runningExternal = [int]($p.jobs.runningExternal)
    $queued = [int]($p.jobs.byStatus.queued)
    $t = Get-Date -Format "HH:mm:ss"
    Write-Host "  [$t] running=$running runningExternal=$runningExternal queued=$queued"

    # Be conservative: only restart when *no running jobs* (external or internal).
    if ($running -eq 0 -and $runningExternal -eq 0) {
      $idleHits += 1
    } else {
      $idleHits = 0
    }

    if ($idleHits -ge $IdleConsecutive) { break }
  } catch {
    $t = Get-Date -Format "HH:mm:ss"
    Write-Host "  [$t] pools check failed: $($_.Exception.Message)"
    $idleHits = 0
  }
  Start-Sleep -Seconds $PollSeconds
}

Write-Host "restart-when-idle: idle detected, restarting daemon..."

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $here "daemon-stop.ps1")
Start-Sleep -Seconds 1
& (Join-Path $here "daemon-start.ps1")

Write-Host "restart-when-idle: done."

