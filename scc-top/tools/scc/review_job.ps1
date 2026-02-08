Param(
  [string]$TasksRoot = "artifacts/scc_tasks",
  [string]$RunsRoot = "artifacts/scc_runs",
  [string]$ProgressDoc = "docs/CANONICAL/PROGRESS.md",
  [string]$RawbDir = "docs/INPUTS/raw-b",
  [switch]$DryRun
)

$scriptPath = Join-Path $PSScriptRoot "review_job.py"
if (-not (Test-Path $scriptPath)) {
  throw "review_job.py not found at $scriptPath"
}

$cmd = @(
  "python",
  $scriptPath,
  "--tasks-root", $TasksRoot,
  "--runs-root", $RunsRoot,
  "--progress-doc", $ProgressDoc,
  "--rawb-dir", $RawbDir
)
if ($DryRun) { $cmd += "--dry-run" }

& $cmd
