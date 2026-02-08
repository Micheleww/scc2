param(
  [string]$TaskName = "SCC-WebGPT-Autosync"
)

$ErrorActionPreference = "Stop"

Write-Host "[webgpt_autosync_uninstall_schtask] deleting scheduled task '$TaskName'"
schtasks.exe /Delete /TN $TaskName /F | Out-Null
Write-Host "[webgpt_autosync_uninstall_schtask] done."
