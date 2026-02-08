# Create Windows logon startup task (User-level, no admin required)
# Goal: start unified_server watchdog on user logon (health check + auto restart)

$ErrorActionPreference = "Stop"

Write-Host "=== Enable logon autostart (Unified Server Watchdog / User) ===" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$unifiedServerDir = $scriptDir
$cmdPath = Join-Path $unifiedServerDir "run_watchdog.cmd"

if (-not (Test-Path $cmdPath)) {
  Write-Host "ERROR: not found: $cmdPath" -ForegroundColor Red
  exit 1
}

$taskName = "QuantSysUnifiedServerWatchdogUser"

# Prefer Startup folder (no admin needed). schtasks is often blocked in corp policies for non-admin users.
$startupDir = [Environment]::GetFolderPath("Startup")
if (-not $startupDir) {
  Write-Host "ERROR: cannot resolve Startup folder path" -ForegroundColor Red
  exit 1
}

$startupVbs = Join-Path $startupDir "QuantSysUnifiedServerWatchdog.vbs"

# VBS runs the watchdog CMD hidden (0) and returns immediately (false)
$vbs = @(
  'Set oShell = CreateObject("Wscript.Shell")'
  'oShell.Run "cmd.exe /c ""' + $cmdPath + '""", 0, False'
)

if (Test-Path $startupVbs) {
  Write-Host "Startup entry exists; overwriting..." -ForegroundColor Yellow
}

Set-Content -Path $startupVbs -Value $vbs -Encoding ASCII

Write-Host "OK: enabled logon autostart via Startup folder" -ForegroundColor Green
Write-Host "Startup dir: $startupDir" -ForegroundColor Gray
Write-Host "Entry file:  $startupVbs" -ForegroundColor Gray
Write-Host "Command:     $cmdPath" -ForegroundColor Gray
Write-Host ""
Write-Host "Manage:" -ForegroundColor Yellow
Write-Host "  Run now:    `"$cmdPath`"" -ForegroundColor Gray
Write-Host "  Disable:    del `"$startupVbs`"" -ForegroundColor Gray
