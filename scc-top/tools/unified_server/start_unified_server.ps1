# 启动统一服务器脚本 (PowerShell)
# 用于Windows环境

$ErrorActionPreference = "Stop"

Write-Host "=== 启动统一服务器 ===" -ForegroundColor Cyan
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

# 切换到统一服务器目录
$unifiedServerDir = "d:\quantsys\tools\unified_server"
if (-not (Test-Path $unifiedServerDir)) {
    Write-Host "❌ 统一服务器目录不存在: $unifiedServerDir" -ForegroundColor Red
    exit 1
}

Set-Location $unifiedServerDir
Write-Host "工作目录: $unifiedServerDir" -ForegroundColor Gray
Write-Host ""

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

# 设置环境变量
$env:REPO_ROOT = "d:\quantsys"
$env:UNIFIED_SERVER_HOST = "127.0.0.1"
$env:UNIFIED_SERVER_PORT = "18788"
$env:LOG_LEVEL = "info"

Write-Host "环境变量:" -ForegroundColor Yellow
Write-Host "  REPO_ROOT: $env:REPO_ROOT" -ForegroundColor Gray
Write-Host "  UNIFIED_SERVER_HOST: $env:UNIFIED_SERVER_HOST" -ForegroundColor Gray
Write-Host "  UNIFIED_SERVER_PORT: $env:UNIFIED_SERVER_PORT" -ForegroundColor Gray
Write-Host "  LOG_LEVEL: $env:LOG_LEVEL" -ForegroundColor Gray
Write-Host ""

# 启动服务器
Write-Host "启动统一服务器..." -ForegroundColor Yellow
Write-Host "服务器地址: http://$($env:UNIFIED_SERVER_HOST):$($env:UNIFIED_SERVER_PORT)/" -ForegroundColor Cyan
Write-Host "端点:" -ForegroundColor Cyan
Write-Host "  - MCP Bus: http://$($env:UNIFIED_SERVER_HOST):$($env:UNIFIED_SERVER_PORT)/mcp" -ForegroundColor Gray
Write-Host "  - A2A Hub: http://$($env:UNIFIED_SERVER_HOST):$($env:UNIFIED_SERVER_PORT)/api" -ForegroundColor Gray
Write-Host "  - Exchange: http://$($env:UNIFIED_SERVER_HOST):$($env:UNIFIED_SERVER_PORT)/exchange" -ForegroundColor Gray
Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Gray
Write-Host ""

try {
    # 使用Python启动
    python start_unified_server.py
} catch {
    Write-Host "❌ 启动失败: $_" -ForegroundColor Red
    exit 1
}
