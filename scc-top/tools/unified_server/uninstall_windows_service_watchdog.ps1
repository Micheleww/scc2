# Uninstall Unified Server Watchdog Windows Service (requires Administrator).

$ErrorActionPreference = "Stop"

function Assert-Admin {
  $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: Administrator privileges required. Re-run in an elevated PowerShell." -ForegroundColor Red
    exit 1
  }
}

Assert-Admin

$serviceName = "QuantSysUnifiedServerWatchdog"

$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\\..")
$pythonExe = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
$servicePy = Join-Path $repoRoot "tools\\unified_server\\windows_service_watchdog.py"
$serviceModule = "tools.unified_server.windows_service_watchdog"

if ((Test-Path $pythonExe) -and (Test-Path $servicePy)) {
  Write-Host "Stopping/removing service (pywin32)..." -ForegroundColor Cyan
  & $pythonExe -m $serviceModule stop *> $null
  & $pythonExe -m $serviceModule remove *> $null
}

sc.exe query $serviceName *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Host "Deleting leftover service entry..." -ForegroundColor Yellow
  sc.exe stop $serviceName | Out-Null
  Start-Sleep -Seconds 1
  sc.exe delete $serviceName | Out-Null
}

Write-Host "OK: service removed." -ForegroundColor Green
