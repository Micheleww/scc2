# 创建开机自启动任务（使用托盘版本）
# 注意：此脚本已更新为使用托盘版本，如需使用原版本，请使用 setup_autostart_tray.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== 设置MCP服务器开机自启动（托盘版本）===" -ForegroundColor Cyan
Write-Host ""

# 配置
$taskName = "MCP Bus Server"
$taskDescription = "Start MCP Bus Server on system startup with system tray icon"
$mcpDir = "d:\quantsys\tools\mcp_bus"
$scriptPath = Join-Path $mcpDir "server_tray_enhanced.py"

# 检查脚本是否存在
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Script not found: $scriptPath" -ForegroundColor Red
    Write-Host "Falling back to basic tray version..." -ForegroundColor Yellow
    $scriptPath = Join-Path $mcpDir "server_tray.py"
}

# 使用pythonw.exe（无窗口Python）
$pythonExe = "python"
$pythonwExe = $pythonExe -replace "python\.exe$", "pythonw.exe"
if (Test-Path $pythonwExe) {
    $pythonExe = $pythonwExe
}

# 创建启动操作
$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $mcpDir

# 创建触发器（开机启动）
$trigger = New-ScheduledTaskTrigger -AtStartup

# 创建设置
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

# 注册任务
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Description $taskDescription `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -RunLevel Highest `
        -Force | Out-Null
    
    Write-Host "✅ 已创建开机自启动任务: $taskName" -ForegroundColor Green
    Write-Host "任务描述: $taskDescription" -ForegroundColor Cyan
    Write-Host "启动脚本: $scriptPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "托盘图标颜色说明:" -ForegroundColor Yellow
    Write-Host "  🟢 绿色: 服务器正常运行" -ForegroundColor Green
    Write-Host "  🟡 黄色: 部分服务异常" -ForegroundColor Yellow
    Write-Host "  🔴 红色: 服务器无法访问" -ForegroundColor Red
    Write-Host "  ⚪ 灰色: 启动中或状态未知" -ForegroundColor Gray
} catch {
    Write-Host "❌ 创建任务失败: $_" -ForegroundColor Red
    Write-Host "提示: 请以管理员身份运行此脚本" -ForegroundColor Yellow
    exit 1
}
