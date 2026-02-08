$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:18788"
$now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")

function Get-Json($url) {
  (Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 $url).Content | ConvertFrom-Json
}

$jobs = Get-Json "$base/executor/jobs"
$board = (Get-Json "$base/board").tasks

$rows = @()
$rows += [ordered]@{ level = "total"; id = "mission"; title = "SCC automated code factory"; parentId = $null; status = "active"; kind = "mission"; source = "manual" }
$rows += [ordered]@{ level = "parent"; id = "fusion"; title = "SCC x OpenCode fusion"; parentId = "mission"; status = "in_progress"; kind = "parent"; source = "manual"; port = 18788 }

foreach ($t in $board) {
  $lvl = "child"
  if ($t.kind -eq "parent") { $lvl = "parent" }
  $parentKey = "fusion"
  if ($t.parentId) { $parentKey = [string]$t.parentId }
  $rows += [ordered]@{
    level = $lvl
    id = $t.id
    title = $t.title
    parentId = $parentKey
    status = $t.status
    kind = $t.kind
    role = $t.role
    source = "board"
    allowedExecutors = $t.allowedExecutors
    allowedModels = $t.allowedModels
    runner = $t.runner
    files = $t.files
    lastJobId = $t.lastJobId
  }
}

foreach ($j in $jobs) {
  $title = "job"
  if ($j.taskType) { $title = [string]$j.taskType }
  $rows += [ordered]@{
    level = "child"
    id = $j.id
    title = $title
    parentId = "fusion"
    status = $j.status
    kind = "executor_job"
    source = "executor"
    executor = $j.executor
    model = $j.model
    runner = $j.runner
    workerId = $j.workerId
    attempts = $j.attempts
    reason = $j.reason
    createdAt = $j.createdAt
    startedAt = $j.startedAt
    finishedAt = $j.finishedAt
  }
}

$summary = [ordered]@{
  generatedAt = $now
  counts = [ordered]@{
    queued_external_jobs = (@($jobs | Where-Object { $_.status -eq "queued" -and $_.runner -eq "external" })).Count
    running_external_jobs = (@($jobs | Where-Object { $_.status -eq "running" -and $_.runner -eq "external" })).Count
    board_tasks = @($board).Count
    executor_jobs = @($jobs).Count
    total_rows = @($rows).Count
  }
}

$out = [ordered]@{ summary = $summary; rows = $rows }
$path = "C:\\scc\\artifacts\\taskboard\\mission_fusion_table.json"
$out | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $path
Write-Host "wrote $path"
