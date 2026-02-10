$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

function Post-Json($url, $obj) {
  $json = ($obj | ConvertTo-Json -Depth 8 -Compress)
  (Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $json -TimeoutSec 30 $url).Content | ConvertFrom-Json
}

$board = Invoke-RestMethod -UseBasicParsing "$Base/board"
$parents = @($board.tasks | Where-Object { $_.kind -eq "parent" })

if ($parents.Count -eq 0) {
  Write-Host "No parent tasks found."
  exit 0
}

$applied = @()
$skipped = @()

foreach ($t in $parents) {
  $jobId = $t.lastJobId
  if (-not $jobId) {
    $skipped += [pscustomobject]@{ parentId = $t.id; title = $t.title; reason = "no_lastJobId" }
    continue
  }
  $job = Invoke-RestMethod -UseBasicParsing "$Base/executor/jobs/$jobId"
  if ($job.status -ne "done") {
    $skipped += [pscustomobject]@{ parentId = $t.id; title = $t.title; jobId = $jobId; jobStatus = $job.status }
    continue
  }
  try {
    $resp = Post-Json "$Base/board/tasks/$($t.id)/split/apply" @{ jobId = $jobId }
    $applied += [pscustomobject]@{ parentId = $t.id; title = $t.title; jobId = $jobId; created = ($resp.created | Measure-Object).Count }
  } catch {
    $skipped += [pscustomobject]@{ parentId = $t.id; title = $t.title; jobId = $jobId; jobStatus = $job.status; reason = "apply_failed"; error = $_.Exception.Message }
  }
}

Write-Host "== Applied =="
$applied | Format-Table -AutoSize
Write-Host "`n== Skipped =="
$skipped | Format-Table -AutoSize

