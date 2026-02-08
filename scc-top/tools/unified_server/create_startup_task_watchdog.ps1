# 创建Windows开机自启动任务（Watchdog版）
# 用Watchdog守护统一服务器：健康检查 + 自动重启

$ErrorActionPreference = "Stop"

Write-Host "=== 创建开机自启动任务（Unified Server Watchdog）===" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$unifiedServerDir = $scriptDir

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ 需要管理员权限！请以管理员身份运行此脚本。" -ForegroundColor Red
    exit 1
}

$taskName = "QuantSysUnifiedServerWatchdog"

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "⚠️ 任务已存在，将删除旧任务..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$cmdPath = Join-Path $unifiedServerDir "run_watchdog.cmd"
if (-not (Test-Path $cmdPath)) {
    Write-Host "❌ 未找到: $cmdPath" -ForegroundColor Red
    exit 1
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$cmdPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -RestartCount 30 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "QuantSys统一服务器Watchdog - 健康检查 + 自动重启（守护18788）" | Out-Null

Write-Host "✅ Watchdog开机自启动任务创建成功" -ForegroundColor Green
Write-Host "任务名称: $taskName" -ForegroundColor Gray
Write-Host "运行脚本: $cmdPath" -ForegroundColor Gray
Write-Host ""
Write-Host "管理命令:" -ForegroundColor Yellow
Write-Host "  运行任务: Start-ScheduledTask -TaskName $taskName" -ForegroundColor Gray
Write-Host "  停止任务: Stop-ScheduledTask -TaskName $taskName" -ForegroundColor Gray
Write-Host "  删除任务: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false" -ForegroundColor Gray

