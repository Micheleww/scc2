param(
  [int]$Hours = 2,
  [int]$IntervalSec = 20
)

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:18788"
$logDir = "C:\scc\artifacts\executor_logs"
$log = Join-Path $logDir "pump-2h.log"

if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

function Log($msg) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -Path $log -Value $line
}

$end = (Get-Date).AddHours($Hours)
Log "pump_start hours=$Hours interval=$IntervalSec"

while ((Get-Date) -lt $end) {
  try {
    $board = Invoke-RestMethod -Uri "$base/board"

    $parentsInProgress = $board.tasks | Where-Object { $_.kind -eq "parent" -and $_.status -eq "in_progress" }
    foreach ($p in $parentsInProgress) {
      try {
        Invoke-RestMethod -Method Post -Uri ("$base/board/tasks/{0}/split/apply" -f $p.id) -ContentType "application/json" -Body "{}" | Out-Null
      } catch {}
    }

    $parentsToSplit = $board.tasks | Where-Object { $_.kind -eq "parent" -and ($_.status -eq "ready" -or $_.status -eq "needs_split") }
    foreach ($p in $parentsToSplit) {
      try {
        Invoke-RestMethod -Method Post -Uri ("$base/board/tasks/{0}/split" -f $p.id) -ContentType "application/json" -Body "{}" | Out-Null
      } catch {}
    }

    $board2 = Invoke-RestMethod -Uri "$base/board"
    $atomicReady = $board2.tasks | Where-Object { $_.kind -eq "atomic" -and ($_.status -eq "ready" -or $_.status -eq "backlog") }
    foreach ($a in $atomicReady) {
      try {
        Invoke-RestMethod -Method Post -Uri ("$base/board/tasks/{0}/dispatch" -f $a.id) -ContentType "application/json" -Body "{}" | Out-Null
      } catch {}
    }

    $counts = $board2.counts
    Log ("tick parents_ready={0} parents_in_progress={1} atomic_ready={2} atomic_in_progress={3}" -f `
      ($parentsToSplit.Count), ($parentsInProgress.Count), ($atomicReady.Count), `
      (($board2.tasks | Where-Object { $_.kind -eq "atomic" -and $_.status -eq "in_progress" }).Count))
  } catch {
    Log ("tick_error {0}" -f $_.Exception.Message)
  }
  Start-Sleep -Seconds $IntervalSec
}

Log "pump_end"
