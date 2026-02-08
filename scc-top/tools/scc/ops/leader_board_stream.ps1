param(
  [int]$EveryS = 60,
  [int]$LimitRuns = 20,
  [switch]$Once
)

$ErrorActionPreference = "Continue"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot | Out-Null

function Tick() {
  $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  Write-Host ("[leader_board] tick_utc=" + $ts)
  python -u tools\scc\ops\leader_board.py --limit-runs $LimitRuns --write-latest
  Write-Host ""
  if (Test-Path "docs\REPORT\control_plane\LEADER_BOARD__LATEST.md") {
    Write-Host ("[leader_board] latest=" + (Resolve-Path "docs\REPORT\control_plane\LEADER_BOARD__LATEST.md").Path)
  }
  if (Test-Path "docs\DERIVED\dispatch\watchdog_events.jsonl") {
    Write-Host "[watchdog] tail:"
    Get-Content "docs\DERIVED\dispatch\watchdog_events.jsonl" -Tail 8 | ForEach-Object { Write-Host ("  " + $_) }
  }
  Write-Host ("-" * 60)
}

Tick
if ($Once) { exit 0 }

while ($true) {
  Start-Sleep -Seconds ([Math]::Max(5, $EveryS))
  Tick
}

