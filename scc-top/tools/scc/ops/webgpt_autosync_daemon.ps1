param(
  [string]$BaseUrl = "http://127.0.0.1:18788",
  [int]$EveryHours = 6,
  [int]$BackfillLimit = 200,
  [int]$ScrollSteps = 30,
  [int]$SidebarScrollSteps = 120,
  [int]$ScrollDelayMs = 240,
  [int]$PerConvWaitMs = 18000,
  [int]$ExportAllLimit = 2000,
  [int]$CaptureMemory = 1
)

$ErrorActionPreference = "Stop"

function Invoke-Once() {
  & $PSScriptRoot\\webgpt_autosync_once.ps1 `
    -BaseUrl $BaseUrl `
    -BackfillLimit $BackfillLimit `
    -ScrollSteps $ScrollSteps `
    -SidebarScrollSteps $SidebarScrollSteps `
    -ScrollDelayMs $ScrollDelayMs `
    -PerConvWaitMs $PerConvWaitMs `
    -ExportAllLimit $ExportAllLimit `
    -CaptureMemory $CaptureMemory
}

while ($true) {
  $started = Get-Date
  Write-Host "[webgpt_autosync_daemon] tick at $started"
  try {
    Invoke-Once
  } catch {
    Write-Host "[webgpt_autosync_daemon] run failed: $($_.Exception.Message)"
  }

  $hours = [Math]::Max(1, $EveryHours)
  $next = $started.AddHours($hours)
  $sleep = [int][Math]::Max(60, ($next - (Get-Date)).TotalSeconds)
  Write-Host "[webgpt_autosync_daemon] sleeping ${sleep}s until $next"
  Start-Sleep -Seconds $sleep
}
