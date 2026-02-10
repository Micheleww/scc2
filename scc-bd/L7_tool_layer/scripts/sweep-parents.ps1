param(
  [string]$BaseUrl = "http://127.0.0.1:18788",
  [int]$MaxSplit = 12
)

$ErrorActionPreference = "Stop"

function Invoke-Json([string]$Method, [string]$Url, $Body = $null) {
  $params = @{
    Method          = $Method
    Uri             = $Url
    TimeoutSec      = 30
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

$parents = $tasks | Where-Object { $_.kind -eq "parent" -and $_.status -eq "ready" }
if ($parents.Count -eq 0) {
  Write-Host "No ready parent tasks."
  exit 0
}

$n = [Math]::Min($MaxSplit, $parents.Count)
Write-Host "Splitting $n parent task(s) (set runner=internal so they don't depend on external codex workers)..."

for ($i=0; $i -lt $n; $i++) {
  $t = $parents[$i]
  try {
    # Ensure internal runner (designer split is hard-gated to codex+gpt-5.2; this avoids external codex requirement).
    Invoke-Json POST "$BaseUrl/board/tasks/$($t.id)/update" @{ runner = "internal" } | Out-Null
  } catch {}

  try {
    Invoke-Json POST "$BaseUrl/board/tasks/$($t.id)/split" @{} | Out-Null
    Write-Host ("split started: {0} {1}" -f $t.id, $t.title)
  } catch {
    Write-Host ("split failed: {0} {1}" -f $t.id, $_.Exception.Message)
  }
}

Write-Host "OK"
