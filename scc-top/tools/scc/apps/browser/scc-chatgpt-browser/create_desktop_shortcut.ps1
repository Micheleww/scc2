$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $appDir "dev_launch.vbs"

if (!(Test-Path $vbs)) {
  throw "Missing launcher: $vbs"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "SCC ChatGPT Browser (DEV).lnk"

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnkPath)
$sc.TargetPath = $vbs
$sc.WorkingDirectory = $appDir
$sc.IconLocation = "$env:SystemRoot\\System32\\shell32.dll,220"
$sc.Description = "Launch SCC ChatGPT Browser (DEV) without a console window."
$sc.Save()

Write-Output "Created shortcut: $lnkPath"

