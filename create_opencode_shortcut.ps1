# 创建OpenCode桌面快捷方式
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut("$env:USERPROFILE\Desktop\OpenCode.lnk")
$Shortcut.TargetPath = "C:\Users\Nwe-1\AppData\Roaming\npm\opencode.cmd"
$Shortcut.WorkingDirectory = "C:\scc"
$Shortcut.Description = "OpenCode AI Coding Assistant"
$Shortcut.Save()

Write-Host "OpenCode桌面快捷方式已创建！"
Write-Host "位置：$env:USERPROFILE\Desktop\OpenCode.lnk"