# Create OpenCode desktop shortcut (source workspace)
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path -Path $desktopPath -ChildPath 'OpenCode.lnk'

$opencodeCmd = if ($env:APPDATA) { Join-Path -Path $env:APPDATA -ChildPath 'npm\\opencode.cmd' } else { 'opencode' }
$repoRoot = Split-Path -Parent $PSCommandPath
$workDir = Join-Path -Path $repoRoot -ChildPath 'opencode-dev\\opencode-dev'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $opencodeCmd
$shortcut.WorkingDirectory = $workDir
$shortcut.Description = 'OpenCode AI Coding Assistant'
$shortcut.Save()

Write-Host "Updated: $shortcutPath"
Write-Host "WorkingDirectory: $workDir"
