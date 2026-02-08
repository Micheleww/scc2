Param(
  [switch]$AllUsers
)

$ErrorActionPreference = "Stop"

function Repo-Root {
  $here = $PSScriptRoot
  if (-not $here) {
    try { $here = Split-Path -Parent $MyInvocation.MyCommand.Path } catch { $here = "" }
  }
  if (-not $here) { $here = (Get-Location).Path }
  return (Resolve-Path (Join-Path $here "..\\..\\..")).Path
}

function Desktop-Path([switch]$AllUsers) {
  if ($AllUsers) {
    # C:\Users\Public\Desktop
    return [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonDesktopDirectory)
  }
  return [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
}

function New-Shortcut([string]$ShortcutPath, [string]$TargetPath, [string]$Arguments, [string]$WorkingDirectory, [string]$Description) {
  $wsh = New-Object -ComObject WScript.Shell
  $sc = $wsh.CreateShortcut($ShortcutPath)
  $sc.TargetPath = $TargetPath
  if ($Arguments) { $sc.Arguments = $Arguments }
  if ($WorkingDirectory) { $sc.WorkingDirectory = $WorkingDirectory }
  if ($Description) { $sc.Description = $Description }
  $sc.WindowStyle = 1
  $sc.Save()
}

$root = Repo-Root
$desktop = Desktop-Path -AllUsers:$AllUsers
New-Item -ItemType Directory -Force -Path $desktop | Out-Null

$devCmd = Join-Path $root "tools\\scc\\dev.cmd"
$ctlCmd = Join-Path $root "tools\\scc\\sccctl.cmd"

if (-not (Test-Path $devCmd)) { throw "missing: $devCmd" }
if (-not (Test-Path $ctlCmd)) { throw "missing: $ctlCmd" }

# SCC Dev: opens local dev.html immediately, then starts docker+server in background.
$devLnk = Join-Path $desktop "SCC Dev.lnk"
New-Shortcut -ShortcutPath $devLnk -TargetPath $devCmd -Arguments "" -WorkingDirectory $root -Description "SCC Dev (open dev page in <3s; then start Docker+server)"

# SCC Desktop: docker-up + open /desktop when ready.
$desktopLnk = Join-Path $desktop "SCC Desktop.lnk"
New-Shortcut -ShortcutPath $desktopLnk -TargetPath $ctlCmd -Arguments "desktop" -WorkingDirectory $root -Description "SCC Desktop (Docker-only unified server on 18788)"

Write-Host ("created: {0}" -f $devLnk)
Write-Host ("created: {0}" -f $desktopLnk)

