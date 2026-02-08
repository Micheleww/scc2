param(
  [string]$TaskName = "SCC-WebGPT-Autosync",
  [string]$RepoRoot = "d:\\quantsys",
  [int]$EveryHours = 6,
  [string]$BaseUrl = "http://127.0.0.1:18788"
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $RepoRoot "tools\\scc\\ops\\webgpt_autosync_once.ps1"
if (-not (Test-Path $scriptPath)) {
  throw "missing_script: $scriptPath"
}

$hours = [Math]::Max(1, $EveryHours)
$ps = "$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
if (-not (Test-Path $ps)) { $ps = "powershell.exe" }

$tr = "`"$ps`" -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -BaseUrl `"$BaseUrl`""

Write-Host "[webgpt_autosync_install_schtask] creating scheduled task '$TaskName' every ${hours}h"
schtasks.exe /Create `
  /TN $TaskName `
  /TR $tr `
  /SC HOURLY `
  /MO $hours `
  /F `
  /RL LIMITED | Out-Null

Write-Host "[webgpt_autosync_install_schtask] done."
Write-Host "[webgpt_autosync_install_schtask] run now: schtasks.exe /Run /TN `"$TaskName`""
Write-Host "[webgpt_autosync_install_schtask] query:   schtasks.exe /Query /TN `"$TaskName`" /V /FO LIST"
