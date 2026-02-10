# 创建桌面快捷方式 - 启动MCP服务器
# 此脚本会在桌面创建快捷方式，点击即可启动服务器

$ErrorActionPreference = "Stop"

Write-Host "=== 创建MCP服务器桌面快捷方式 ===" -ForegroundColor Cyan
Write-Host ""

# 获取桌面路径
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "启动MCP服务器.lnk"

# 服务器启动脚本路径
$repoRoot = "d:\quantsys"
$startScript = Join-Path $repoRoot "快速启动本地MCP.ps1"

# 检查启动脚本是否存在
if (-not (Test-Path $startScript)) {
    Write-Host "错误: 启动脚本不存在: $startScript" -ForegroundColor Red
    exit 1
}

# 创建PowerShell命令
$psCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$startScript`""

Write-Host "桌面路径: $desktopPath" -ForegroundColor Gray
Write-Host "快捷方式: $shortcutPath" -ForegroundColor Gray
Write-Host "启动脚本: $startScript" -ForegroundColor Gray
Write-Host ""

# 创建快捷方式
try {
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$startScript`""
    $Shortcut.WorkingDirectory = $repoRoot
    $Shortcut.Description = "启动MCP服务器（包含MCP服务、Web查看器和FreqUI）"
    $Shortcut.IconLocation = "powershell.exe,0"
    $Shortcut.Save()
    
    Write-Host "✅ 快捷方式创建成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "快捷方式位置: $shortcutPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "现在可以双击桌面上的'启动MCP服务器'快捷方式来启动服务器" -ForegroundColor Yellow
} catch {
    Write-Host "❌ 创建快捷方式失败: $_" -ForegroundColor Red
    exit 1
}
