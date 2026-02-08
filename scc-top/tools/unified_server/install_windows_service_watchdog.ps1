# Install Unified Server Watchdog as a Windows Service (requires Administrator).
# This keeps the unified server alive without relying on user logon.

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

$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
  $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $scriptDir) {
  Write-Host "ERROR: This script must be executed as a file (e.g. powershell -File ...), not pasted line-by-line." -ForegroundColor Red
  exit 1
}

$repoRoot = Resolve-Path (Join-Path $scriptDir "..\\..")
$serviceModule = "tools.unified_server.windows_service_watchdog"
$servicePy = Join-Path $repoRoot "tools\\unified_server\\windows_service_watchdog.py"
if (-not (Test-Path $servicePy)) {
  Write-Host "ERROR: not found: $servicePy" -ForegroundColor Red
  exit 1
}

# Common venv paths (used by multiple steps below)
$venvRoot = Join-Path $repoRoot ".venv"
$venvScripts = Join-Path $repoRoot ".venv\\Scripts"

# Prefer repo-local venv python for stability
$pythonExe = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path $pythonExe)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source) {
    $pythonExe = $cmd.Source
  }
}
if (-not (Test-Path $pythonExe)) {
  Write-Host "ERROR: python executable not found. Expected $($repoRoot.Path)\\.venv\\Scripts\\python.exe or python on PATH." -ForegroundColor Red
  exit 1
}

# Ensure venv root exists (needed for DLL copies below)
try { New-Item -ItemType Directory -Force -Path $venvRoot | Out-Null } catch { }

$serviceName = "QuantSysUnifiedServerWatchdog"
$displayName = "QuantSys Unified Server Watchdog"
$description = "Keeps QuantSys Unified Server (127.0.0.1:18788) alive via health-check + auto-restart."

# Stop any already-running unified_server watchdog/main (avoid duplicates & port fights)
try {
  $pids = @()
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
    $cmd = $_.CommandLine
    if ($cmd -and ($cmd -like "*tools\\unified_server\\watchdog.py*" -or $cmd -like "*tools\\unified_server\\main.py*")) {
      $pids += $_.ProcessId
    }
  }
  if ($pids.Count -gt 0) {
    Write-Host ("Stopping existing unified_server python processes: " + ($pids -join ",")) -ForegroundColor Yellow
    Stop-Process -Id $pids -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
  }
} catch {
  # best-effort
}

# Avoid duplicate watchdogs: disable Startup-folder autostart if present
$startupDir = [Environment]::GetFolderPath("Startup")
$startupVbs = Join-Path $startupDir "QuantSysUnifiedServerWatchdog.vbs"
if (Test-Path $startupVbs) {
  $bak = $startupVbs + ".bak_" + (Get-Date -Format "yyyyMMdd_HHmmss")
  Move-Item -Force $startupVbs $bak
  Write-Host "NOTE: moved Startup entry to: $bak" -ForegroundColor Yellow
}

# Remove existing service if present
sc.exe query $serviceName *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Host "Service already exists; stopping + deleting..." -ForegroundColor Yellow
  sc.exe stop $serviceName | Out-Null
  Start-Sleep -Seconds 1
  sc.exe delete $serviceName | Out-Null
  Start-Sleep -Seconds 1
}

# Ensure pywin32 is installed (required to register a real Windows service)
Write-Host "Ensuring pywin32..." -ForegroundColor Cyan
& $pythonExe -m pip show pywin32 *> $null
if ($LASTEXITCODE -ne 0) {
  & $pythonExe -m pip install pywin32
  if ($LASTEXITCODE -ne 0) { exit 1 }
}

# Run pywin32 postinstall as admin to register/copy required binaries for LocalSystem.
# Without this, the service host (pythonservice.exe) may fail to load pywintypes/pythoncom and hang/stop.
try {
  $postinstall = Join-Path $repoRoot ".venv\\Scripts\\pywin32_postinstall.py"
  if (Test-Path $postinstall) {
    Write-Host "Running pywin32 postinstall (admin)..." -ForegroundColor Cyan
    & $pythonExe $postinstall -install | Out-Null
  }
} catch {
  Write-Host ("WARN: pywin32 postinstall failed: " + $_.Exception.Message) -ForegroundColor Yellow
}

# pythonservice.exe needs pythonXY.dll next to it (same directory) on many setups.
# In some environments (especially newer Python builds), the venv root may not contain python314.dll,
# causing the service host to hang and SCM to time out. Copy python*.dll from the base install.
try {
  $basePrefix = & $pythonExe -c "import sys; print(sys.base_prefix)" 2>$null
  if ($basePrefix) {
    $basePrefix = $basePrefix.Trim()
    $dllCandidates = @("python3.dll")
    # Try to derive pythonXY.dll from runtime (e.g. python314.dll).
    $xy = & $pythonExe -c "import sys; print(f'python{sys.version_info.major}{sys.version_info.minor}.dll')" 2>$null
    if ($xy) { $dllCandidates += $xy.Trim() }

    foreach ($dllName in ($dllCandidates | Select-Object -Unique)) {
      $src = Join-Path $basePrefix $dllName
      if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $venvRoot $dllName)
      }
    }
  }
} catch {
  Write-Host ("WARN: failed to copy python*.dll for pythonservice.exe: " + $_.Exception.Message) -ForegroundColor Yellow
}

# Sanity: pythonservice.exe typically needs these next to it.
if (-not (Test-Path (Join-Path $venvRoot "python3.dll"))) {
  Write-Host "WARN: missing $venvRoot\\python3.dll (pythonservice.exe may fail to start)." -ForegroundColor Yellow
}
$xyDll = & $pythonExe -c "import sys; print(f'python{sys.version_info.major}{sys.version_info.minor}.dll')" 2>$null
if ($xyDll) {
  $xyDll = $xyDll.Trim()
  if ($xyDll -and (-not (Test-Path (Join-Path $venvRoot $xyDll)))) {
    Write-Host ("WARN: missing " + (Join-Path $venvRoot $xyDll) + " (pythonservice.exe may fail to start).") -ForegroundColor Yellow
  }
}

# pywin32 service host runs as LocalSystem; ensure required DLLs are available from a non-user path.
# Copy pywintypes/pythoncom DLLs next to pythonservice.exe to avoid relying on user profile paths.
$pywin32Sys32 = Join-Path $repoRoot ".venv\\Lib\\site-packages\\pywin32_system32"
if (Test-Path $pywin32Sys32) {
  $dlls = @()
  $dlls += Get-ChildItem -Path $pywin32Sys32 -Filter "pywintypes*.dll" -ErrorAction SilentlyContinue
  $dlls += Get-ChildItem -Path $pywin32Sys32 -Filter "pythoncom*.dll" -ErrorAction SilentlyContinue
  foreach ($d in $dlls) {
    try {
      Copy-Item -Force $d.FullName (Join-Path $venvRoot $d.Name)
      Copy-Item -Force $d.FullName (Join-Path $venvScripts $d.Name)
    } catch {
      # best-effort
    }
  }
}

Write-Host "Installing service (pywin32)..." -ForegroundColor Cyan
# Install via module path so pywin32 registers a correct PythonClass (not an absolute file path).
& $pythonExe -m $serviceModule --startup auto install
if ($LASTEXITCODE -ne 0) { exit 1 }

# Fix pywin32 registry parameters so LocalSystem can import the service module reliably.
# (Some environments end up with an absolute-path-like PythonClass; override to a real module path.)
$svcRegRoot = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\$serviceName"
$pythonClassValue = "tools.unified_server.windows_service_watchdog.QuantSysUnifiedServerWatchdogService"
$pythonPathValue = ($repoRoot.Path + ";" + (Join-Path $repoRoot ".venv\\Lib\\site-packages"))

try {
  # NOTE: reg.exe expects single backslashes.
  $pythonClassKey = "HKLM\SYSTEM\CurrentControlSet\Services\$serviceName\PythonClass"
  $pythonPathKey = "HKLM\SYSTEM\CurrentControlSet\Services\$serviceName\PythonPath"

  reg.exe add $pythonClassKey /ve /t REG_SZ /d $pythonClassValue /f | Out-Null
  reg.exe add $pythonPathKey /ve /t REG_SZ /d $pythonPathValue /f | Out-Null
} catch {
  Write-Host ("WARN: failed to set service registry PythonClass/PythonPath: " + $_.Exception.Message) -ForegroundColor Yellow
}

Write-Host "Setting description..." -ForegroundColor Cyan
$out = & sc.exe description $serviceName $description 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host ($out | Out-String) -ForegroundColor Red
  exit 1
}

Write-Host "Creating service: $serviceName" -ForegroundColor Cyan
Write-Host "OK: installed service entry" -ForegroundColor Green

# Auto-restart on failure (enterprise baseline)
# reset= 86400 (1 day), 3 restarts with 5s delay each
$out = & sc.exe failure $serviceName "reset=" "86400" "actions=" "restart/5000/restart/5000/restart/5000" 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host ($out | Out-String) -ForegroundColor Red
  exit 1
}
$out = & sc.exe failureflag $serviceName 1 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host ($out | Out-String) -ForegroundColor Red
  exit 1
}

# Best-effort: delayed auto start (supported on Win10/11+)
try { & sc.exe config $serviceName "start= delayed-auto" | Out-Null } catch { }

Write-Host "Starting service..." -ForegroundColor Cyan
$out = & $pythonExe -m $serviceModule start 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host ($out | Out-String) -ForegroundColor Red
  exit 1
}
Write-Host ($out | Out-String).Trim()

# Verify service reaches RUNNING
$running = $false
for ($i = 0; $i -lt 15; $i++) {
  $q = sc.exe query $serviceName 2>$null
  if ($q -match "STATE\\s*:\\s*4\\s+RUNNING") { $running = $true; break }
  Start-Sleep -Seconds 1
}
if (-not $running) {
  Write-Host "ERROR: service did not reach RUNNING. Check:" -ForegroundColor Red
  Write-Host "  sc.exe query $serviceName" -ForegroundColor Gray
  Write-Host "  C:\\ProgramData\\QuantSys\\unified_server\\service_watchdog.log" -ForegroundColor Gray
  exit 1
}

Write-Host "OK: service installed and started." -ForegroundColor Green
Write-Host "Manage:" -ForegroundColor Yellow
Write-Host "  Query:   sc.exe query $serviceName" -ForegroundColor Gray
Write-Host "  Stop:    sc.exe stop $serviceName" -ForegroundColor Gray
Write-Host "  Start:   sc.exe start $serviceName" -ForegroundColor Gray
Write-Host "  Delete:  sc.exe delete $serviceName" -ForegroundColor Gray
Write-Host ""
Write-Host "Health:" -ForegroundColor Yellow
Write-Host "  http://127.0.0.1:18788/health/ready" -ForegroundColor Gray

Write-Host ""
Write-Host "Service logs (ProgramData):" -ForegroundColor Yellow
Write-Host "  C:\\ProgramData\\QuantSys\\unified_server\\service_watchdog.log" -ForegroundColor Gray
Write-Host "  C:\\ProgramData\\QuantSys\\unified_server\\watchdog.log" -ForegroundColor Gray
