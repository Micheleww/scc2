param(
  [Parameter(Mandatory=$true)][string]$Config,
  [string]$Model = "gpt-5.2",
  [int]$TimeoutS = 1800,
  [int]$MaxOutstanding = 1,
  [string]$BaseUrl = "http://127.0.0.1:18788",
  [int]$PollS = 60,
  [int]$StuckAfterS = 60,
  [int]$TokenCap = 20000,
  [int]$LeaderBoardPollS = 60,
  [int]$LeaderBoardLimitRuns = 10,
  [switch]$DryRunWatchdog
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot | Out-Null

$cfgPath = $Config
if (-not [System.IO.Path]::IsPathRooted($cfgPath)) {
  $cfgPath = Join-Path $repoRoot $cfgPath
}
if (-not (Test-Path $cfgPath)) {
  throw ("config not found: " + $cfgPath)
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outDir = Join-Path $repoRoot ("artifacts\scc_state\delegation\dispatch_$stamp")
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$wdStdout = Join-Path $outDir "watchdog_stdout.log"
$wdStderr = Join-Path $outDir "watchdog_stderr.log"

$lbStdout = Join-Path $outDir "leader_board_stdout.log"
$lbStderr = Join-Path $outDir "leader_board_stderr.log"

$wdArgs = @(
  "-u",
  "tools\scc\ops\dispatch_watchdog.py",
  "--base", $BaseUrl,
  "--poll-s", $PollS,
  "--stuck-after-s", $StuckAfterS
)
if ([int]$TokenCap -gt 0) { $wdArgs += @("--token-cap", [string]$TokenCap) }
if ($DryRunWatchdog) { $wdArgs += "--dry-run" }

$wd = Start-Process -FilePath "python" `
  -ArgumentList $wdArgs `
  -WorkingDirectory $repoRoot `
  -NoNewWindow `
  -PassThru `
  -RedirectStandardOutput $wdStdout `
  -RedirectStandardError $wdStderr

$lbJob = Start-Job -ScriptBlock {
  param([string]$RepoRoot, [string]$StdoutPath, [string]$StderrPath, [int]$PollS, [int]$LimitRuns)
  $ErrorActionPreference = "Continue"
  Set-Location $RepoRoot | Out-Null
  while ($true) {
    try {
      $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
      Add-Content -Encoding utf8 -Path $StdoutPath -Value ("[leader_board] tick_utc=" + $ts)
      python -u tools\scc\ops\leader_board.py --limit-runs $LimitRuns --write-latest 1>> $StdoutPath 2>> $StderrPath
    } catch {
      try { Add-Content -Encoding utf8 -Path $StderrPath -Value ("[leader_board] exception=" + $_.Exception.Message) } catch {}
    }
    Start-Sleep -Seconds ([Math]::Max(5, $PollS))
  }
} -ArgumentList $repoRoot, $lbStdout, $lbStderr, $LeaderBoardPollS, $LeaderBoardLimitRuns

try {
  $runArgs = @(
    "-u",
    "tools\scc\automation\run_batches.py",
    "--base", $BaseUrl,
    "--config", $cfgPath,
    "--model", $Model,
    "--timeout-s", $TimeoutS,
    "--max-outstanding", $MaxOutstanding
  )

  $runStdout = Join-Path $outDir "automation_stdout.log"
  $runStderr = Join-Path $outDir "automation_stderr.log"

  $p = Start-Process -FilePath "python" `
    -ArgumentList $runArgs `
    -WorkingDirectory $repoRoot `
    -NoNewWindow `
    -PassThru `
    -Wait `
    -RedirectStandardOutput $runStdout `
    -RedirectStandardError $runStderr

  $exitCode = 1
  try { $exitCode = [int]$p.ExitCode } catch { $exitCode = 1 }
  Write-Output ("exit_code=" + $exitCode)
  Write-Output ("out_dir=" + $outDir)
  exit $exitCode
} finally {
  try {
    if ($wd -and -not $wd.HasExited) {
      Stop-Process -Id $wd.Id -Force
    }
  } catch {}
  try {
    if ($lbJob) {
      Stop-Job -Job $lbJob -Force | Out-Null
      Remove-Job -Job $lbJob -Force | Out-Null
    }
  } catch {}
}
