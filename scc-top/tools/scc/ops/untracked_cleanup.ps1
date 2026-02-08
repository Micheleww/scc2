# Removes untracked files created by accidental large-scale writes.
# Keeps SSOT trunk and SCC automation deliverables.
#
# Evidence:
# - artifacts/scc_state/cleanup/<stamp>/untracked_to_remove.txt
# - artifacts/scc_state/cleanup/<stamp>/remove_failures.txt (optional)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path
Set-Location $repoRoot | Out-Null

$keep = @(
  "docs/ssot/",
  "docs/START_HERE.md",
  "docs/INPUTS/",
  "docs/DERIVED/",
  "docs/CANONICAL/",
  "evidence/",
  "contracts/examples/",
  "configs/scc/ssot_autonomy_batches__v0.1.0__20260201.json",
  "tools/scc/ops/ssot_autonomy_dispatch.ps1",
  "tools/scc/raw_to_task_tree.py",
  "tools/scc/review_job.py",
  "tools/scc/review_job.ps1"
)

function Normalize([string]$p) {
  return ($p -replace "\\\\", "/")
}

function ShouldKeep([string]$p) {
  $p2 = Normalize $p
  foreach ($k in $keep) {
    if ($k.EndsWith("/")) {
      if ($p2.StartsWith($k)) { return $true }
    } else {
      if ($p2 -eq $k) { return $true }
    }
  }
  return $false
}

$untracked = & git ls-files -o --exclude-standard
$toRemove = @()
foreach ($p in $untracked) {
  if (-not (ShouldKeep $p)) { $toRemove += $p }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportDir = Join-Path "artifacts\\scc_state\\cleanup" $stamp
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$toRemove | Set-Content -Encoding UTF8 (Join-Path $reportDir "untracked_to_remove.txt")

Write-Output ("untracked_total=" + $untracked.Count)
Write-Output ("remove_count=" + $toRemove.Count)
Write-Output ("report_dir=" + (Resolve-Path $reportDir).Path)

foreach ($p in $toRemove) {
  $full = Join-Path $repoRoot $p
  try {
    if (Test-Path $full) {
      try {
        Remove-Item -Force -Recurse $full
      } catch {
        Add-Content -Encoding UTF8 (Join-Path $reportDir "remove_failures.txt") ($p + " :: " + $_.Exception.Message)
      }
    }
  } catch {
    Add-Content -Encoding UTF8 (Join-Path $reportDir "remove_failures.txt") ($p + " :: " + $_.Exception.Message)
  }
}

$remaining = (& git ls-files -o --exclude-standard).Count
Write-Output ("after_remove_untracked_count=" + $remaining)
