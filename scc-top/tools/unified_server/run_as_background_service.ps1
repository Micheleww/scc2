# 统一服务器后台服务运行脚本
# 使用PowerShell后台作业运行，支持开机自启动

$ErrorActionPreference = "Stop"

Write-Host "=== 统一服务器后台服务 ===" -ForegroundColor Cyan
Write-Host ""

# 获取脚本目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$unifiedServerDir = $scriptDir
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

# 切换到统一服务器目录
Set-Location $unifiedServerDir

# 设置环境变量
$env:REPO_ROOT = $repoRoot
$env:UNIFIED_SERVER_HOST = "127.0.0.1"
$env:UNIFIED_SERVER_PORT = "18788"
$env:LOG_LEVEL = "info"
$env:DEBUG = "false"
if (-not $env:DASHBOARD_ENABLED) {
    $env:DASHBOARD_ENABLED = "true"
}

Write-Host "环境变量:" -ForegroundColor Yellow
Write-Host "  REPO_ROOT: $env:REPO_ROOT" -ForegroundColor Gray
Write-Host "  UNIFIED_SERVER_HOST: $env:UNIFIED_SERVER_HOST" -ForegroundColor Gray
Write-Host "  UNIFIED_SERVER_PORT: $env:UNIFIED_SERVER_PORT" -ForegroundColor Gray
Write-Host "  DASHBOARD_ENABLED: $env:DASHBOARD_ENABLED" -ForegroundColor Gray
Write-Host ""

# 检查Python环境
Write-Host "检查Python环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python未安装或不在PATH中" -ForegroundColor Red
    exit 1
}

# 检查依赖
Write-Host "检查依赖..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn, pydantic_settings" 2>&1 | Out-Null
    Write-Host "✅ 依赖已安装" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 正在安装依赖..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

Write-Host ""

# 创建日志目录
$logDir = Join-Path $unifiedServerDir "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$logFile = Join-Path $logDir "server_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

Write-Host "启动后台服务..." -ForegroundColor Yellow
Write-Host "服务器地址: http://$($env:UNIFIED_SERVER_HOST):$($env:UNIFIED_SERVER_PORT)/" -ForegroundColor Cyan
Write-Host "日志文件: $logFile" -ForegroundColor Gray
Write-Host ""

# 使用Start-Process在后台运行
$process = Start-Process -FilePath "python" `
    -ArgumentList "main.py" `
    -WorkingDirectory $unifiedServerDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError $logFile `
    -PassThru

Write-Host "✅ 服务器已在后台启动" -ForegroundColor Green
Write-Host "进程ID: $($process.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "管理命令:" -ForegroundColor Yellow
Write-Host "  查看日志: Get-Content $logFile -Tail 50 -Wait" -ForegroundColor Gray
Write-Host "  停止服务: Stop-Process -Id $($process.Id)" -ForegroundColor Gray
Write-Host "  查看进程: Get-Process -Id $($process.Id)" -ForegroundColor Gray
Write-Host ""

# 保存进程ID到文件
$pidFile = Join-Path $unifiedServerDir "server.pid"
$process.Id | Out-File -FilePath $pidFile -Encoding ASCII

Write-Host "进程ID已保存到: $pidFile" -ForegroundColor Gray
