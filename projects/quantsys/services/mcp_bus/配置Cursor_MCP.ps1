# Cursor MCP 自动配置脚本
# 用于自动配置 Cursor 连接到本地 MCP 服务器

$ErrorActionPreference = "Stop"

Write-Host "=== Cursor MCP 配置脚本 ===" -ForegroundColor Cyan
Write-Host ""

# 获取 Python 路径
Write-Host "查找 Python 路径..." -ForegroundColor Yellow
try {
    $pythonPath = (Get-Command python).Source
    Write-Host "  Python 路径: $pythonPath" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 未找到 Python，请确保 Python 已安装并在 PATH 中" -ForegroundColor Red
    exit 1
}

# 配置文件路径
$configPath = "$env:APPDATA\Cursor\User\settings.json"
$configDir = Split-Path $configPath -Parent

# 确保目录存在
if (-not (Test-Path $configDir)) {
    Write-Host "创建配置目录: $configDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

# 读取现有配置
$config = @{}
if (Test-Path $configPath) {
    Write-Host "读取现有配置..." -ForegroundColor Yellow
    try {
        $existingContent = Get-Content $configPath -Raw -Encoding UTF8
        if ($existingContent.Trim()) {
            $config = $existingContent | ConvertFrom-Json -AsHashtable
            Write-Host "  ✅ 已读取现有配置" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠️  配置文件格式错误，将创建新配置" -ForegroundColor Yellow
        $config = @{}
    }
} else {
    Write-Host "配置文件不存在，将创建新配置" -ForegroundColor Yellow
}

# 添加 MCP 配置
Write-Host ""
Write-Host "添加 MCP 服务器配置..." -ForegroundColor Yellow

$mcpConfig = @{
    "command" = $pythonPath
    "args" = @(
        "d:\quantsys\tools\mcp_bus\server_stdio.py"
    )
    "env" = @{
        "REPO_ROOT" = "d:\quantsys"
        "MCP_BUS_HOST" = "127.0.0.1"
        "MCP_BUS_PORT" = "8000"
        "AUTH_MODE" = "none"
    }
}

if (-not $config.ContainsKey("mcpServers")) {
    $config["mcpServers"] = @{}
}

$config["mcpServers"]["qcc-bus-local"] = $mcpConfig

# 保存配置
Write-Host "保存配置到: $configPath" -ForegroundColor Yellow
try {
    # 使用 ConvertTo-Json 并格式化
    $jsonContent = $config | ConvertTo-Json -Depth 10
    $jsonContent | Set-Content $configPath -Encoding UTF8
    Write-Host "  ✅ 配置已保存" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 保存配置失败: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== 配置完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  1. 确保本地 MCP 服务器正在运行" -ForegroundColor White
Write-Host "     cd d:\quantsys" -ForegroundColor Gray
Write-Host "     .\快速启动本地MCP.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. 重启 Cursor" -ForegroundColor White
Write-Host ""
Write-Host "  3. 在 Cursor 中验证连接" -ForegroundColor White
Write-Host "     - 打开命令面板 (Ctrl+Shift+P)" -ForegroundColor Gray
Write-Host "     - 搜索 'MCP' 查看可用工具" -ForegroundColor Gray
Write-Host ""
Write-Host "配置文件位置: $configPath" -ForegroundColor Cyan
