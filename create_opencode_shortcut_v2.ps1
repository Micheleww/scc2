# Create OpenCode desktop shortcut (source workspace)
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path -Path $desktopPath -ChildPath 'OpenCode.lnk'

$opencodeCmd = if ($env:APPDATA) { Join-Path -Path $env:APPDATA -ChildPath 'npm\\opencode.cmd' } else { 'opencode' }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $opencodeCmd
$shortcut.WorkingDirectory = 'C:\\scc\\opencode-dev\\opencode-dev'
$shortcut.Description = 'OpenCode AI Coding Assistant'
$shortcut.Save()

Write-Host "Updated: $shortcutPath"
Write-Host 'WorkingDirectory: C:\\scc\\opencode-dev\\opencode-dev'
