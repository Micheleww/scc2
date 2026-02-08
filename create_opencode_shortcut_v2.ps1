# 创建OpenCode桌面快捷方式（指向源代码目录）
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut("$env:USERPROFILE\Desktop\OpenCode.lnk")
$Shortcut.TargetPath = "C:\Users\Nwe-1\AppData\Roaming\npm\opencode.cmd"
$Shortcut.WorkingDirectory = "C:\scc\opencode-dev\opencode-dev"
$Shortcut.Description = "OpenCode AI Coding Assistant"
$Shortcut.Save()

Write-Host "OpenCode桌面快捷方式已更新！"
Write-Host "位置：$env:USERPROFILE\Desktop\OpenCode.lnk"
Write-Host "工作目录：C:\scc\opencode-dev\opencode-dev"