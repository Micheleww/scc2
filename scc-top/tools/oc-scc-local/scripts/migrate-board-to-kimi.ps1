param(
  [string]$BaseUrl = "http://127.0.0.1:18788",
  [int]$MaxClone = 50,
  [int]$MaxDispatch = 20,
  [string]$Model = "opencode/kimi-k2.5-free"
)

$ErrorActionPreference = "Stop"

function Invoke-Json([string]$Method, [string]$Url, $Body = $null) {
  $params = @{
    Method      = $Method
    Uri         = $Url
    TimeoutSec  = 20
    UseBasicParsing = $true
  }
  if ($null -ne $Body) {
    $params["ContentType"] = "application/json"
    $params["Body"] = ($Body | ConvertTo-Json -Depth 10)
  }
  $resp = Invoke-WebRequest @params
  if (-not $resp.Content) { return $null }
  return ($resp.Content | ConvertFrom-Json)
}

$board = Invoke-Json GET "$BaseUrl/board"
$tasks = @($board.tasks)

$candidates = $tasks | Where-Object {
  $_.kind -eq "atomic" -and @("ready","backlog","failed") -contains $_.status
} | Where-Object { $_.role -ne "designer" }

if ($candidates.Count -eq 0) {
  Write-Host "No atomic tasks eligible for kimi migration."
  exit 0
}

$cloneN = [Math]::Min($MaxClone, $candidates.Count)
Write-Host "Cloning $cloneN task(s) to executor=opencodecli model=$Model ..."

$created = @()
for ($i=0; $i -lt $cloneN; $i++) {
  $t = $candidates[$i]
  $baseTitle = $t.title
  if (-not $baseTitle) { $baseTitle = $t.id }
  $title = "[kimi] " + [string]$baseTitle
  $payload = @{
    kind = "atomic"
    title = $title
    goal = $t.goal
    status = "ready"
    role = $t.role
    allowedExecutors = @("opencodecli")
    allowedModels = @($Model)
    files = @($t.files)
    skills = @($t.skills)
    pointers = $t.pointers
    runner = $t.runner
    timeoutMs = $t.timeoutMs
    parentId = $t.parentId
  }
  $newTask = Invoke-Json POST "$BaseUrl/board/tasks" $payload
  $created += @{ oldId = $t.id; newId = $newTask.id }

  # Block old one so autopump won't dispatch it.
  Invoke-Json POST "$BaseUrl/board/tasks/$($t.id)/status" @{ status = "blocked" } | Out-Null
  # Annotate old goal (best-effort; keep goal size bounded).
  $note = "`n`n[REPLACED_BY_KIMI] $($newTask.id)"
  $newGoal = [string]$t.goal
  if ($newGoal.Length -gt 4000) { $newGoal = $newGoal.Substring(0, 4000) }
  Invoke-Json POST "$BaseUrl/board/tasks/$($t.id)/update" @{ goal = ($newGoal + $note) } | Out-Null
}

Write-Host ("Created {0} kimi task(s)." -f $created.Count)

$dispatchN = [Math]::Min($MaxDispatch, $created.Count)
if ($dispatchN -le 0) { exit 0 }

Write-Host "Dispatching $dispatchN task(s) ..."
for ($i=0; $i -lt $dispatchN; $i++) {
  $id = $created[$i].newId
  try {
    Invoke-Json POST "$BaseUrl/board/tasks/$id/dispatch" @{} | Out-Null
  } catch {
    # ignore; autopump will pick it up
  }
}

Write-Host "OK"
