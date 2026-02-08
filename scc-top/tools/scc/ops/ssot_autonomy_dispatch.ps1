# SSOT autonomy delegation: dispatch 5 workstreams to Codex CLI executor (gpt-5.2-codex).
#
# Output:
# - artifacts/scc_state/delegation/<dispatch_id>/{automation_stdout.log,automation_stderr.log,meta.json}
#
# Notes:
param(
  [switch]$DangerouslyBypass
)

$ErrorActionPreference = "Stop"

# - This script DOES NOT modify SSOT registry; delegated tasks are restricted in their own prompts.

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path
Set-Location $repoRoot | Out-Null

$dispatchId = "ssot_autonomy_" + (Get-Date -Format "yyyyMMdd_HHmmss")
$outDir = Join-Path $repoRoot ("artifacts\\scc_state\\delegation\\" + $dispatchId)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$cfg = "configs\\scc\\ssot_autonomy_batches__v0.1.0__20260201.json"

$args = @(
  "tools\\scc\\automation\\run_batches.py",
  "--config", $cfg,
  "--model", "gpt-5.2",
  "--timeout-s", "1800",
  "--max-outstanding", "3"
)
if ($DangerouslyBypass) {
  $args += "--dangerously-bypass"
}

$meta = @{
  dispatch_id = $dispatchId
  started_utc = (Get-Date).ToUniversalTime().ToString("o")
  config = $cfg
  args = $args
  repo_root = $repoRoot
}
$meta | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $outDir "meta.json")

Write-Output "RUNNING"
Write-Output ("dispatch_id=" + $dispatchId)
Write-Output ("out_dir=" + $outDir)

$stdoutLog = Join-Path $outDir "automation_stdout.log"
$stderrLog = Join-Path $outDir "automation_stderr.log"

$p = Start-Process -FilePath "python" `
  -ArgumentList $args `
  -WorkingDirectory $repoRoot `
  -NoNewWindow `
  -PassThru `
  -Wait `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog

$exitCode = 1
try { $exitCode = [int]$p.ExitCode } catch { $exitCode = 1 }

# Try to locate automation run_id/out_dir from stdout.
$automationRunId = $null
$automationOutDir = $null
try {
  $hit = Select-String -Path $stdoutLog -Pattern "\\[automation\\] done run_id=(\\S+) out_dir=(.+)$" | Select-Object -Last 1
  if ($hit -and $hit.Matches -and $hit.Matches.Count -gt 0) {
    $automationRunId = $hit.Matches[0].Groups[1].Value
    $automationOutDir = $hit.Matches[0].Groups[2].Value
  }
} catch {}

# Extract codex server run_id from automation response file.
$codexRunId = $null
$codexArtifactsDir = $null
try {
  if ($automationRunId) {
    $respPath = Join-Path $repoRoot (Join-Path "artifacts\\scc_state\\automation_runs" (Join-Path $automationRunId "01__ssot_autonomy_v0_1_0__response.json"))
    if (Test-Path $respPath) {
      $j = Get-Content $respPath -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($j -and $j.response) {
        $codexRunId = $j.response.run_id
        $codexArtifactsDir = $j.response.server_artifacts_dir
      }
    }
  }
} catch {}

$meta2 = @{
  dispatch_id = $dispatchId
  ended_utc = (Get-Date).ToUniversalTime().ToString("o")
  exit_code = $exitCode
  automation_stdout = $stdoutLog
  automation_stderr = $stderrLog
  automation_run_id = $automationRunId
  automation_out_dir = $automationOutDir
  codex_run_id = $codexRunId
  codex_server_artifacts_dir = $codexArtifactsDir
}

try {
  $merged = @{}
  foreach ($k in $meta.Keys) { $merged[$k] = $meta[$k] }
  foreach ($k in $meta2.Keys) { $merged[$k] = $meta2[$k] }
  $merged | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $outDir "meta.json")
} catch {}

Write-Output "DONE"
Write-Output ("exit_code=" + $exitCode)
if ($automationRunId) { Write-Output ("automation_run_id=" + $automationRunId) }
if ($automationOutDir) { Write-Output ("automation_out_dir=" + $automationOutDir) }
if ($codexRunId) { Write-Output ("codex_run_id=" + $codexRunId) }
if ($codexArtifactsDir) { Write-Output ("codex_server_artifacts_dir=" + $codexArtifactsDir) }
