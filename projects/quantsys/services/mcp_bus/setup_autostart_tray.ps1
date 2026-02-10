# 设置开机自启动（使用托盘版本）
# 创建开机自启动任务，使用托盘版本，后台运行，不显示窗口

$ErrorActionPreference = "Continue"

Write-Host "=== 设置MCP服务器开机自启动（托盘版本）===" -ForegroundColor Cyan
Write-Host ""

# 配置
$taskName = "MCP Bus Server (Tray)"
$taskDescription = "Start MCP Bus Server on system startup with system tray icon"
$mcpDir = "d:\quantsys\tools\mcp_bus"
$scriptPath = Join-Path $mcpDir "server_tray_enhanced.py"

# 检查脚本是否存在
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

# 检查Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found" -ForegroundColor Red
    exit 1
}

# 检查并安装依赖
Write-Host "检查依赖..." -ForegroundColor Yellow
try {
    python -c "import pystray, PIL" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "安装 pystray 和 pillow..." -ForegroundColor Yellow
        pip install pystray pillow 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠️ 警告: 无法安装依赖，托盘图标可能不可用" -ForegroundColor Yellow
        } else {
            Write-Host "✅ 依赖安装成功" -ForegroundColor Green
        }
    } else {
        Write-Host "✅ 依赖已安装" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️ 警告: 依赖检查失败" -ForegroundColor Yellow
}

Write-Host ""

# 使用pythonw.exe（无窗口Python）
$pythonExe = "python"
$pythonwExe = $pythonExe -replace "python\.exe$", "pythonw.exe"
if (Test-Path $pythonwExe) {
    $pythonExe = $pythonwExe
    Write-Host "使用 pythonw.exe（无窗口模式）" -ForegroundColor Gray
} else {
    Write-Host "使用 python.exe（将隐藏窗口）" -ForegroundColor Gray
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
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # 无时间限制

# 注册任务（需要管理员权限）
Write-Host "创建计划任务..." -ForegroundColor Yellow
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Description $taskDescription `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -RunLevel Highest `
        -Force | Out-Null
    
    Write-Host "✅ 开机自启动任务创建成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "任务名称: $taskName" -ForegroundColor Cyan
    Write-Host "任务描述: $taskDescription" -ForegroundColor Cyan
    Write-Host "启动脚本: $scriptPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "托盘图标颜色说明:" -ForegroundColor Yellow
    Write-Host "  🟢 绿色: 服务器正常运行，所有服务正常" -ForegroundColor Green
    Write-Host "  🟡 黄色: 服务器运行但部分服务异常" -ForegroundColor Yellow
    Write-Host "  🔴 红色: 服务器无法访问或严重错误" -ForegroundColor Red
    Write-Host "  ⚪ 灰色: 服务器启动中或状态未知" -ForegroundColor Gray
    Write-Host ""
    Write-Host "管理任务:" -ForegroundColor Yellow
    Write-Host "  查看任务: Get-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
    Write-Host "  删除任务: Unregister-ScheduledTask -TaskName `"$taskName`" -Confirm:`$false" -ForegroundColor Gray
    Write-Host "  运行任务: Start-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
    
} catch {
    Write-Host "❌ 创建任务失败: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "提示: 请以管理员身份运行此脚本" -ForegroundColor Yellow
    Write-Host "右键点击PowerShell，选择'以管理员身份运行'" -ForegroundColor Yellow
    exit 1
}
