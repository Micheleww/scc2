# Create OpenCode desktop shortcut
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path -Path $desktopPath -ChildPath 'OpenCode.lnk'

$opencodeCmd = if ($env:APPDATA) { Join-Path -Path $env:APPDATA -ChildPath 'npm\\opencode.cmd' } else { 'opencode' }
$repoRoot = Split-Path -Parent $PSCommandPath

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $opencodeCmd
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = 'OpenCode AI Coding Assistant'
$shortcut.Save()

Write-Host "Created: $shortcutPath"
