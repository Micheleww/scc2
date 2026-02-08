Param(
  [ValidateSet('dry','apply')]
  [string]$Mode = 'apply'
)

$ErrorActionPreference = 'Stop'

function Repo-Root {
  $here = $PSScriptRoot
  if (-not $here) {
    try { $here = Split-Path -Parent $MyInvocation.MyCommand.Path } catch { $here = '' }
  }
  if (-not $here) { $here = (Get-Location).Path }
  return (Resolve-Path (Join-Path $here '..\\..\\..')).Path
}

$root = Repo-Root
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $root 'artifacts\\scc_state\\reports'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("daily_sweep_{0}.log" -f $ts)

Push-Location $root
try {
  if ($Mode -eq 'dry') {
    & $env:ComSpec /c ("tools\\scc\\sccctl.cmd sweep") 2>&1 | Tee-Object -FilePath $log | Out-Host
  } else {
    & $env:ComSpec /c ("tools\\scc\\sccctl.cmd sweep apply") 2>&1 | Tee-Object -FilePath $log | Out-Host
  }
  Write-Host ("wrote: {0}" -f $log)
} finally {
  Pop-Location
}

