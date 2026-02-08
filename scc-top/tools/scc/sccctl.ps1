Param(
  [Parameter(Position=0)]
  [ValidateSet('start','stop','restart','status','doctor','sweep','gc','logs','docker-up','docker-down','docker-restart','docker-status','docker-logs','desktop','help')]
  [string]$Command = 'status',

  [Parameter(Position=1)]
  [string]$Arg1 = ''
)

$ErrorActionPreference = 'Stop'

function Repo-Root {
  $here = $PSScriptRoot
  if (-not $here) {
    try { $here = Split-Path -Parent $MyInvocation.MyCommand.Path } catch { $here = '' }
  }
  if (-not $here) { $here = (Get-Location).Path }
  return (Resolve-Path (Join-Path $here '..\\..')).Path
}

function Write-Section([string]$title) {
  Write-Host ''
  Write-Host ("== {0} ==" -f $title)
}

function Ensure-Docker {
  Param(
    [int]$WaitSec = 60
  )

  function _Docker-Ok {
    try {
      $v = (& docker version --format '{{.Server.Version}}' 2>$null | Out-String).Trim()
      return [bool]$v
    } catch {
      return $false
    }
  }

  if (_Docker-Ok) { return $true }

  # Best-effort: try to start Docker Desktop (user-level) if installed.
  try {
    $candidates = @(
      "$env:ProgramFiles\\Docker\\Docker\\Docker Desktop.exe",
      "$env:ProgramFiles(x86)\\Docker\\Docker\\Docker Desktop.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    $already = Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue
    if (-not $already -and $candidates -and $candidates.Count -gt 0) {
      Write-Host ("starting Docker Desktop: {0}" -f $candidates[0])
      try { Start-Process -FilePath $candidates[0] | Out-Null } catch {}
    }
  } catch {}

  if ($WaitSec -le 0) {
    Write-Host 'Docker Desktop not available (cannot talk to Docker engine).'
    Write-Host 'Please start Docker Desktop and wait until the engine is running, then retry.'
    return $false
  }

  $deadline = (Get-Date).AddSeconds($WaitSec)
  while ((Get-Date) -lt $deadline) {
    if (_Docker-Ok) { return $true }
    Start-Sleep -Milliseconds 800
  }

  Write-Host 'Docker Desktop not ready (engine not reachable).'
  Write-Host 'Hints:'
  Write-Host '- Start Docker Desktop and wait for "Engine running".'
  Write-Host '- If you see "Access is denied", add your Windows user to the "docker-users" group then sign out/in.'
  return $false
}

function Get-Targets {
  $patterns = @(
    'tools\unified_server\watchdog.py',
    'tools\unified_server\main.py',
    'tools\scc\automation\daemon_inbox.py',
    'tools\\unified_server\\watchdog.py',
    'tools\\unified_server\\main.py',
    'tools\\scc\\automation\\daemon_inbox.py',
    'tools/unified_server/watchdog.py',
    'tools/unified_server/main.py',
    'tools/scc/automation/daemon_inbox.py'
  )
  $procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine }
  $hits = @()
  foreach ($p in $procs) {
    foreach ($pat in $patterns) {
      if ($p.CommandLine -like "*$pat*") { $hits += $p; break }
    }
  }
  return $hits
}

function Get-PortOwners([int[]]$Ports) {
  $owners = @()
  $lines = (netstat -ano | Select-String -Pattern 'LISTENING' | ForEach-Object { $_.Line }) 2>$null
  foreach ($port in $Ports) {
    foreach ($line in $lines) {
      if ($line -notmatch (":$port\\s")) { continue }
      $parts = ($line -split '\\s+') | Where-Object { $_ }
      if ($parts.Count -ge 5) {
        $pid = [int]$parts[-1]
        if ($pid -gt 0) { $owners += $pid }
      }
    }
  }
  return ($owners | Sort-Object -Unique)
}

function Kill-Targets {
  $targets = Get-Targets
  $pidsFromPorts = Get-PortOwners -Ports @(18788,18789,18790)
  foreach ($pid in $pidsFromPorts) {
    if (-not $targets) { $targets = @() }
    if (($targets | Where-Object { $_.ProcessId -eq $pid }).Count -eq 0) {
      try {
        $w = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $pid)
        if ($w -and $w.CommandLine -and ($w.CommandLine -match 'python')) { $targets += $w }
      } catch {}
    }
  }
  if (-not $targets -or $targets.Count -eq 0) {
    Write-Host 'no scc processes'
    return
  }
  $targets | Select-Object ProcessId,CommandLine | Format-Table -Wrap -AutoSize | Out-String | Write-Host
  foreach ($p in $targets) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
      Write-Host ("killed {0}" -f $p.ProcessId)
    } catch {
      Write-Host ("fail_kill {0}: {1}" -f $p.ProcessId, $_.Exception.Message)
    }
  }
}

function Wait-Ready([int]$TimeoutSec = 45) {
  $port = 18788
  try {
    if ($env:SCC_HOST_PORT) { $port = [int]$env:SCC_HOST_PORT }
  } catch {}
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      Invoke-RestMethod -TimeoutSec 2 -Uri ("http://127.0.0.1:{0}/health/ready" -f $port) | Out-Null
      return $true
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  return $false
}

function Show-Ports {
  Write-Section 'Ports'
  foreach ($port in @(18788,18789,18790)) {
    $lines = (netstat -ano | Select-String -Pattern (":$port") | ForEach-Object { $_.Line }) 2>$null
    if (-not $lines) {
      Write-Host ("{0}: (no entries)" -f $port)
      continue
    }
    Write-Host ("{0}:" -f $port)
    $lines | Select-Object -First 10 | ForEach-Object { Write-Host ("  " + $_) }
  }
}

function Show-Health {
  Write-Section 'Health'
  $port = 18788
  try {
    if ($env:SCC_HOST_PORT) { $port = [int]$env:SCC_HOST_PORT }
  } catch {}
  try {
    $r = Invoke-RestMethod -TimeoutSec 3 -Uri ("http://127.0.0.1:{0}/health/ready" -f $port)
    $r | ConvertTo-Json -Depth 6 | Write-Host
  } catch {
    Write-Host ("/health/ready ERR: {0}" -f $_.Exception.Message)
  }
  try {
    $r = Invoke-RestMethod -TimeoutSec 3 -Uri ("http://127.0.0.1:{0}/scc/parents/status?limit=15" -f $port)
    $r.counts | ConvertTo-Json -Depth 4 | Write-Host
  } catch {
    Write-Host ("/scc/parents/status ERR: {0}" -f $_.Exception.Message)
  }
}

function Start-Scc {
  $root = Repo-Root
  $py = Join-Path $root '.venv\\Scripts\\python.exe'
  if (-not (Test-Path $py)) { $py = 'python' }
  $wd = Join-Path $root 'tools\\unified_server\\watchdog.py'

  Write-Section 'Start'
  $env:UNIFIED_SERVER_MODE = '1'
  $env:UNIFIED_SERVER_HOST = '127.0.0.1'
  $env:UNIFIED_SERVER_PORT = '18788'
  $env:SCC_BASE_URL = 'http://127.0.0.1:18788'
  $env:WATCHDOG_AUTO_RUN_AUTOMATION = 'true'
  $env:SCC_PARENT_INBOX = 'artifacts/scc_state/parent_inbox.jsonl'
  $env:SCC_AUTOMATION_MAX_OUTSTANDING = '3'
  Start-Process -WindowStyle Hidden -WorkingDirectory $root -FilePath $py -ArgumentList @($wd) | Out-Null
  Write-Host ("started: {0} {1}" -f $py, $wd)

  if (Wait-Ready 60) {
    Write-Host 'READY'
  } else {
    Write-Host 'NOT_READY (timeout)'
  }
}

function Stop-Scc {
  Write-Section 'Stop'
  Kill-Targets
}

function Status-Scc {
  Write-Section 'Processes'
  $targets = Get-Targets
  if (-not $targets -or $targets.Count -eq 0) {
    Write-Host 'no scc processes'
  } else {
    $targets | Select-Object ProcessId,CommandLine | Format-Table -Wrap -AutoSize | Out-String | Write-Host
  }
  Show-Ports
  Show-Health
}

function Doctor-Scc {
  $root = Repo-Root
  $outDir = Join-Path $root 'artifacts\\scc_state\\reports'
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
  $out = Join-Path $outDir ("doctor_{0}.md" -f $ts)

  $lines = @()
  $lines += "# SCC Doctor ($ts)"
  $lines += ""
  $lines += "## Processes"
  $targets = Get-Targets
  if ($targets -and $targets.Count -gt 0) {
    $lines += ($targets | Select-Object ProcessId,CommandLine | Format-Table -Wrap -AutoSize | Out-String)
  } else {
    $lines += "no scc processes"
  }
  $lines += ""
  $lines += "## Ports"
  foreach ($port in @(18788,18789,18790)) {
    $lines += "### $port"
    $lines += ((netstat -ano | Select-String -Pattern (":$port") | ForEach-Object { $_.Line }) | Select-Object -First 30 | Out-String)
    $lines += ""
  }
  $lines += "## Health"
  try { $lines += (Invoke-RestMethod -TimeoutSec 3 -Uri 'http://127.0.0.1:18788/health/ready' | ConvertTo-Json -Depth 8) } catch { $lines += ("/health/ready ERR: " + $_.Exception.Message) }
  $lines += ""
  try { $lines += (Invoke-RestMethod -TimeoutSec 3 -Uri 'http://127.0.0.1:18788/scc/system/metrics' | ConvertTo-Json -Depth 8) } catch { $lines += ("/scc/system/metrics ERR: " + $_.Exception.Message) }
  $lines += ""
  try { $lines += (Invoke-RestMethod -TimeoutSec 5 -Uri 'http://127.0.0.1:18788/scc/parents/status?limit=50' | ConvertTo-Json -Depth 12) } catch { $lines += ("/scc/parents/status ERR: " + $_.Exception.Message) }
  $lines += ""
  $lines += "## Root Clutter Audit"
  try {
    $audit = & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\ops\\root_clutter_audit.py'))
    $lines += ($audit | Out-String)
  } catch {
    $lines += ("root_clutter_audit ERR: " + $_.Exception.Message)
  }
  $lines += ""
  $lines += "## Git Noise Audit"
  try {
    $gna = & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\ops\\git_noise_audit.py'))
    $lines += ($gna | Out-String)
  } catch {
    $lines += ("git_noise_audit ERR: " + $_.Exception.Message)
  }
  $lines += ""
  $lines += "## Untracked Inventory"
  try {
    $uti = & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\ops\\untracked_inventory.py'))
    $lines += ($uti | Out-String)
  } catch {
    $lines += ("untracked_inventory ERR: " + $_.Exception.Message)
  }
  $lines += ""

  $lines += "## Port Reference Audit (localhost)"
  try {
    $pra = & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\ops\\port_reference_audit.py'))
    $lines += ($pra | Out-String)
  } catch {
    $lines += ("port_reference_audit ERR: " + $_.Exception.Message)
  }

  Set-Content -Encoding UTF8 -Path $out -Value $lines
  Write-Host ("wrote: {0}" -f $out)
}

function Gc-Scc([bool]$Apply = $false) {
  $root = Repo-Root
  Write-Section 'GC Artifacts'
  $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\gc_artifacts.py')
  if ($Apply) { $cmd += " --apply" }
  & $env:ComSpec /c $cmd | Out-Host
}

function Sweep-Scc([bool]$Apply = $false) {
  $root = Repo-Root
  $outDir = Join-Path $root 'artifacts\\scc_state\\reports'
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
  $out = Join-Path $outDir ("sweep_{0}.md" -f $ts)

  Write-Section 'Sweep'
  Write-Host ("apply={0} report={1}" -f $Apply, $out)

  $lines = @()
  $lines += "# SCC Sweep ($ts)"
  $lines += ""
  $lines += ("- apply: {0}" -f $Apply)
  $lines += ""

  $lines += "## Housekeeping (root clutter archive)"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\housekeeping.py') + " --apply"
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("housekeeping ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Git Local Exclude Apply (SCC focus)"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\git_local_exclude_apply.py') + " --scc-focus"
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("git_local_exclude_apply ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Root Clutter Audit"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\root_clutter_audit.py')
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("root_clutter_audit ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Git Noise Audit"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\git_noise_audit.py')
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("git_noise_audit ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Untracked Inventory"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\untracked_inventory.py')
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("untracked_inventory ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Port Reference Audit (localhost)"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\port_reference_audit.py')
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("port_reference_audit ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Quarantine Untracked"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\quarantine_untracked.py')
    if ($Apply) { $cmd += " --apply" }
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("quarantine_untracked ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Prune Executor Active Runs"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\prune_executor_active_runs.py')
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("prune_executor_active_runs ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## Evidence Budget Audit"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\evidence_budget_audit.py')
    if ($Apply) { $cmd += " --apply" }
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("evidence_budget_audit ERR: " + $_.Exception.Message) }
  $lines += ""

  $lines += "## GC Artifacts"
  try {
    $cmd = "python " + (Join-Path $root 'tools\\scc\\ops\\gc_artifacts.py')
    if ($Apply) { $cmd += " --apply" }
    $lines += (& $env:ComSpec /c $cmd | Out-String)
  } catch { $lines += ("gc_artifacts ERR: " + $_.Exception.Message) }

  Set-Content -Encoding UTF8 -Path $out -Value $lines
  Write-Host ("wrote: {0}" -f $out)
}

function Docker-Compose([string[]]$Args) {
  $root = Repo-Root
  $compose = Join-Path $root 'docker-compose.scc.yml'
  if (-not (Test-Path $compose)) {
    throw "missing compose file: $compose"
  }
  $full = @('compose','-f', $compose) + $Args
  & docker @full
}

switch ($Command) {
  'start'   { Start-Scc }
  'stop'    { Stop-Scc }
  'restart' { Stop-Scc; Start-Sleep -Milliseconds 500; Start-Scc }
  'status'  { Status-Scc }
  'doctor'  { Doctor-Scc }
  'sweep'   { Sweep-Scc -Apply:($Arg1 -eq 'apply') }
  'gc'      { Gc-Scc -Apply:($Arg1 -eq 'apply') }
  'docker-up' {
    Write-Section 'Docker Up'
    if (-not (Ensure-Docker -WaitSec 90)) { return }
    $root = Repo-Root
    try {
      & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\check_wheelhouse.py')) | Out-Host
    } catch {}
    $stageCmd = Join-Path $root 'tools\\unified_server\\docker\\stage_context.cmd'
    if (Test-Path $stageCmd) {
      Write-Host ("staging build context: {0}" -f $stageCmd)
      & $env:ComSpec /c ('"' + $stageCmd + '"') | Out-Host
    }
    Docker-Compose @('up','-d','--build')
    Docker-Compose @('ps')
    if (Wait-Ready 120) { Write-Host 'READY' } else { Write-Host 'NOT_READY (timeout)' }
  }
  'docker-down' {
    Write-Section 'Docker Down'
    if (-not (Ensure-Docker -WaitSec 30)) { return }
    Docker-Compose @('down')
  }
  'docker-restart' {
    Write-Section 'Docker Restart'
    if (-not (Ensure-Docker -WaitSec 90)) { return }
    Docker-Compose @('down')
    $root = Repo-Root
    try {
      & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\check_wheelhouse.py')) | Out-Host
    } catch {}
    $stageCmd = Join-Path $root 'tools\\unified_server\\docker\\stage_context.cmd'
    if (Test-Path $stageCmd) {
      Write-Host ("staging build context: {0}" -f $stageCmd)
      & $env:ComSpec /c ('"' + $stageCmd + '"') | Out-Host
    }
    Docker-Compose @('up','-d','--build')
    Docker-Compose @('ps')
    if (Wait-Ready 120) { Write-Host 'READY' } else { Write-Host 'NOT_READY (timeout)' }
  }
  'desktop' {
    Write-Section 'Desktop'
    if (-not (Ensure-Docker -WaitSec 120)) { return }
    $root = Repo-Root
    try {
      & $env:ComSpec /c ("python " + (Join-Path $root 'tools\\scc\\check_wheelhouse.py')) | Out-Host
    } catch {}
    $stageCmd = Join-Path $root 'tools\\unified_server\\docker\\stage_context.cmd'
    if (Test-Path $stageCmd) {
      Write-Host ("staging build context: {0}" -f $stageCmd)
      & $env:ComSpec /c ('"' + $stageCmd + '"') | Out-Host
    }
    Docker-Compose @('up','-d','--build')
    Docker-Compose @('ps')
    if (Wait-Ready 180) {
      Write-Host 'READY'
      $port = 18788
      try { if ($env:SCC_HOST_PORT) { $port = [int]$env:SCC_HOST_PORT } } catch {}
      $url = ("http://127.0.0.1:{0}/desktop" -f $port)
      try { Start-Process $url | Out-Null } catch { Write-Host ("open_browser_failed: " + $_.Exception.Message) }
      Write-Host ("opened: {0}" -f $url)
    } else {
      Write-Host 'NOT_READY (timeout)'
    }
  }
  'docker-status' {
    Write-Section 'Docker Status'
    Docker-Compose @('ps')
  }
  'docker-logs' {
    Write-Section 'Docker Logs'
    if ($Arg1) {
      Docker-Compose @('logs','-f','--tail','200', $Arg1)
    } else {
      Docker-Compose @('logs','-f','--tail','200')
    }
  }
  'logs'    {
    $root = Repo-Root
    $log = Join-Path $root 'tools\\unified_server\\logs\\watchdog.log'
    if (Test-Path $log) { Get-Content $log -Tail 200 } else { Write-Host "no log: $log" }
  }
  Default   {
    Write-Host 'Usage: sccctl.ps1 start|stop|restart|status|doctor|sweep|gc|logs|docker-up|docker-down|docker-restart|docker-status|docker-logs [apply|service]'
  }
}
