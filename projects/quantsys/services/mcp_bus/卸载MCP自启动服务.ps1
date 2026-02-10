# 卸载MCP服务器自启动服务
# 需要管理员权限运行

$ErrorActionPreference = "Stop"

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ 需要管理员权限！" -ForegroundColor Red
    Write-Host "   请右键点击脚本，选择'以管理员身份运行'" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== 卸载MCP服务器自启动服务 ===" -ForegroundColor Cyan
Write-Host ""

$taskName = "MCP-Server-AutoStart"

# 检查任务是否存在
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "⚠️  任务不存在: $taskName" -ForegroundColor Yellow
    exit 0
}

# 停止任务（如果正在运行）
Write-Host "停止任务..." -ForegroundColor Yellow
try {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
} catch {
    Write-Host "任务未运行或已停止" -ForegroundColor Gray
}

# 删除任务
Write-Host "删除计划任务..." -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✅ 任务已删除" -ForegroundColor Green
} catch {
    Write-Host "❌ 删除任务失败: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ MCP服务器自启动服务已卸载" -ForegroundColor Green
Write-Host "   服务器将不再在开机时自动启动" -ForegroundColor Gray
