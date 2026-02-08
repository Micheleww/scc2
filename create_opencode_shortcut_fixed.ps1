# 创建OpenCode桌面快捷方式
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path -Path $desktopPath -ChildPath 'OpenCode.lnk'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'C:\Users\Nwe-1\AppData\Roaming\npm\opencode.cmd'
$shortcut.WorkingDirectory = 'C:\scc\opencode-dev\opencode-dev'
$shortcut.Description = 'OpenCode AI Coding Assistant'
$shortcut.Save()

Write-Host "OpenCode桌面快捷方式已创建！"
Write-Host "位置：$shortcutPath"
Write-Host "工作目录：C:\scc\opencode-dev\opencode-dev"