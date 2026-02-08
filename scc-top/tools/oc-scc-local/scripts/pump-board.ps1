$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$MaxDispatchPerTick = if ($env:MAX_DISPATCH_PER_TICK) { [int]$env:MAX_DISPATCH_PER_TICK } else { 6 }
$TickSeconds = if ($env:PUMP_TICK_SECONDS) { [int]$env:PUMP_TICK_SECONDS } else { 20 }

function Post-Json($url, $obj) {
  $json = ($obj | ConvertTo-Json -Depth 8 -Compress)
  (Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $json -TimeoutSec 30 $url).Content | ConvertFrom-Json
}

function Try-Post($url, $obj) {
  try { Post-Json $url $obj } catch { $null }
}

Write-Host "pump-board.ps1 starting. base=$Base tick=${TickSeconds}s maxDispatchPerTick=$MaxDispatchPerTick"

while ($true) {
  try {
    $board = Invoke-RestMethod -UseBasicParsing "$Base/board"
    $tasks = @($board.tasks)

    # 1) Apply finished parent splits automatically
    $parents = @($tasks | Where-Object { $_.kind -eq "parent" -and $_.status -eq "in_progress" -and $_.lastJobId })
    foreach ($p in $parents) {
      $jobId = [string]$p.lastJobId
      $job = Invoke-RestMethod -UseBasicParsing "$Base/executor/jobs/$jobId"
      if ($job.status -eq "done") {
        $resp = Try-Post "$Base/board/tasks/$($p.id)/split/apply" @{ jobId = $jobId }
        if ($resp) {
          Write-Host ("[{0}] applied split parent={1} created={2}" -f (Get-Date -Format "HH:mm:ss"), $p.id, (($resp.created | Measure-Object).Count))
        }
      }
    }

    # 2) Dispatch ready/backlog atomic tasks automatically (best-effort)
    $board2 = Invoke-RestMethod -UseBasicParsing "$Base/board"
    $atomicReady = @($board2.tasks | Where-Object { $_.kind -eq "atomic" -and ($_.status -eq "ready" -or $_.status -eq "backlog") })
    $dispatched = 0
    foreach ($t in $atomicReady) {
      if ($dispatched -ge $MaxDispatchPerTick) { break }
      $resp = Try-Post "$Base/board/tasks/$($t.id)/dispatch" @{}
      if ($resp) {
        $dispatched += 1
        Write-Host ("[{0}] dispatched task={1} job={2}" -f (Get-Date -Format "HH:mm:ss"), $t.id, $resp.job.id)
      }
    }

    # 3) Lightweight heartbeat summary for humans
    if ($board2.counts) {
      $c = $board2.counts
      $ip = if ($c.byStatus -and $c.byStatus.in_progress) { $c.byStatus.in_progress } else { 0 }
      $rd = if ($c.byStatus -and $c.byStatus.ready) { $c.byStatus.ready } else { 0 }
      $bl = if ($c.byStatus -and $c.byStatus.backlog) { $c.byStatus.backlog } else { 0 }
      Write-Host ("[{0}] board total={1} parent={2} atomic={3} in_progress={4} ready={5} backlog={6}" -f (Get-Date -Format "HH:mm:ss"), $c.total, $c.parent, $c.atomic, $ip, $rd, $bl)
    }
  } catch {
    Write-Host ("[{0}] pump error: {1}" -f (Get-Date -Format "HH:mm:ss"), $_.Exception.Message)
  }

  Start-Sleep -Seconds $TickSeconds
}
