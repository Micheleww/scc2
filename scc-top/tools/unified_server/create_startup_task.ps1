 # 创建Windows开机自启动任务
# 使用任务计划程序创建开机自启动任务

$ErrorActionPreference = "Stop"

Write-Host "=== 创建开机自启动任务 ===" -ForegroundColor Cyan
Write-Host ""

# 获取脚本目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$unifiedServerDir = $scriptDir
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ 需要管理员权限！请以管理员身份运行此脚本。" -ForegroundColor Red
    Write-Host "右键点击PowerShell，选择'以管理员身份运行'" -ForegroundColor Yellow
    exit 1
}

# 任务名称
$taskName = "QuantSysUnifiedServer"

# 检查任务是否已存在
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "⚠️ 任务已存在，将删除旧任务..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 创建任务动作
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -File `"$unifiedServerDir\run_as_background_service.ps1`""

# 创建任务触发器（开机时）
$trigger = New-ScheduledTaskTrigger -AtStartup

# 创建任务设置
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# 创建任务主体（系统账户）
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# 注册任务
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "QuantSys统一服务器 - 开机自启动" | Out-Null
    
    Write-Host "✅ 开机自启动任务创建成功" -ForegroundColor Green
    Write-Host ""
    Write-Host "任务名称: $taskName" -ForegroundColor Gray
    Write-Host "任务路径: $unifiedServerDir" -ForegroundColor Gray
    Write-Host ""
    Write-Host "管理命令:" -ForegroundColor Yellow
    Write-Host "  查看任务: Get-ScheduledTask -TaskName $taskName" -ForegroundColor Gray
    Write-Host "  运行任务: Start-ScheduledTask -TaskName $taskName" -ForegroundColor Gray
    Write-Host "  停止任务: Stop-ScheduledTask -TaskName $taskName" -ForegroundColor Gray
    Write-Host "  删除任务: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false" -ForegroundColor Gray
    Write-Host ""
    Write-Host "服务器将在下次开机时自动启动" -ForegroundColor Green
} catch {
    Write-Host "❌ 任务创建失败: $_" -ForegroundColor Red
    exit 1
}
