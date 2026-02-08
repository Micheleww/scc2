$ErrorActionPreference = "Stop"

function Read-Json([string]$path) {
  if (-not (Test-Path $path)) { return $null }
  $raw = Get-Content -Raw -Encoding UTF8 $path
  if (-not $raw) { return $null }
  return $raw | ConvertFrom-Json
}

function Write-Json([string]$path, $obj) {
  $obj | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $path
}

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) # tools/unified_server/docker -> tools/unified_server -> tools
$RepoRoot = Split-Path -Parent $RepoRoot # repo root
Push-Location $RepoRoot
try {
  $stampPath = "tools/unified_server/docker/build_stamp.json"
  $stamp = Read-Json $stampPath
  if (-not $stamp) { throw "missing build_stamp.json: $stampPath" }

  $head = (git rev-parse HEAD).Trim()
  $base = $stamp.lastBuiltCommit
  if (-not $base) {
    Write-Host "No lastBuiltCommit; will rebuild and set stamp."
    $needs = $true
  } else {
    $commitsAhead = [int]((git rev-list --count "$base..HEAD") | Select-Object -First 1)
    $filesChanged = [int]((git diff --name-only "$base..HEAD" | Measure-Object).Count)
    $short = (git diff --shortstat "$base..HEAD")
    $linesChanged = 0
    if ($short -match "(\\d+) insertion") { $linesChanged += [int]$Matches[1] }
    if ($short -match "(\\d+) deletion") { $linesChanged += [int]$Matches[1] }

    $pol = $stamp.policy
    $needs =
      ($commitsAhead -ge [int]$pol.rebuildIfCommitsAheadGte) -or
      ($filesChanged -ge [int]$pol.rebuildIfFilesChangedGte) -or
      ($linesChanged -ge [int]$pol.rebuildIfLinesChangedGte)

    Write-Host ("commitsAhead={0} filesChanged={1} linesChanged={2} needsRebuild={3}" -f $commitsAhead, $filesChanged, $linesChanged, $needs)
  }

  if (-not $needs) {
    Write-Host "Skip rebuild."
    exit 0
  }

  $compose = "docker-compose.scc.yml"
  if (-not (Test-Path $compose)) { throw "missing compose: $compose" }

  Write-Host "Rebuilding image scc-unified:local ..."
  docker compose -f $compose build scc-server
  docker compose -f $compose up -d --no-deps scc-server scc-daemon

  $stamp.lastBuiltCommit = $head
  $stamp.lastBuiltAt = (Get-Date).ToUniversalTime().ToString("o")
  Write-Json $stampPath $stamp
  Write-Host "Updated stamp: $stampPath"
} finally {
  Pop-Location
}

