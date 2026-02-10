# 配置本地MCP转发到云MCP
# 用于实现GPT与TRAE的文件通信

$ErrorActionPreference = "Stop"

Write-Host "=== 配置本地MCP转发到云MCP ===" -ForegroundColor Cyan
Write-Host ""

# 云MCP配置
$cloudMcpUrl = "https://mcp.timquant.tech/mcp"
$cloudMcpToken = ""  # 如果需要token，在这里填写

# 检查环境变量
Write-Host "当前配置:" -ForegroundColor Yellow
Write-Host "  云MCP地址: $cloudMcpUrl" -ForegroundColor Gray
if ($cloudMcpToken) {
    Write-Host "  云MCP Token: [已配置]" -ForegroundColor Gray
} else {
    Write-Host "  云MCP Token: [未配置，使用无认证模式]" -ForegroundColor Gray
}
Write-Host ""

# 设置环境变量（当前会话）
$env:UPSTREAM_MCP_URL = $cloudMcpUrl
if ($cloudMcpToken) {
    $env:UPSTREAM_MCP_TOKEN = $cloudMcpToken
}

Write-Host "✅ 环境变量已设置（当前会话）" -ForegroundColor Green
Write-Host ""

# 创建启动脚本（包含环境变量）
$startScript = @"
# 启动本地MCP服务器（带云MCP转发）
`$env:REPO_ROOT = "d:\quantsys"
`$env:MCP_BUS_HOST = "127.0.0.1"
`$env:MCP_BUS_PORT = "8000"
`$env:AUTH_MODE = "none"
`$env:UPSTREAM_MCP_URL = "$cloudMcpUrl"
"@

if ($cloudMcpToken) {
    $startScript += "`n`$env:UPSTREAM_MCP_TOKEN = `"$cloudMcpToken`""
}

$startScript += @"

cd d:\quantsys\tools\mcp_bus
python -m uvicorn server.main:app --host `$env:MCP_BUS_HOST --port `$env:MCP_BUS_PORT --reload
"@

$scriptPath = "d:\quantsys\tools\mcp_bus\启动MCP_带云转发.ps1"
$startScript | Out-File -FilePath $scriptPath -Encoding UTF8

Write-Host "✅ 已创建启动脚本: $scriptPath" -ForegroundColor Green
Write-Host ""

# 更新快速启动脚本
Write-Host "更新快速启动脚本..." -ForegroundColor Yellow
$quickStartScript = "d:\quantsys\快速启动本地MCP.ps1"
if (Test-Path $quickStartScript) {
    $content = Get-Content $quickStartScript -Raw
    
    # 检查是否已包含UPSTREAM_MCP_URL
    if ($content -notmatch "UPSTREAM_MCP_URL") {
        # 在环境变量设置部分添加
        $content = $content -replace "(`$env:AUTH_MODE = `"none`")", "`$1`n`$env:UPSTREAM_MCP_URL = `"$cloudMcpUrl`""
        if ($cloudMcpToken) {
            $content = $content -replace "(`$env:UPSTREAM_MCP_URL = `"$cloudMcpUrl`")", "`$1`n`$env:UPSTREAM_MCP_TOKEN = `"$cloudMcpToken`""
        }
        $content | Out-File -FilePath $quickStartScript -Encoding UTF8
        Write-Host "✅ 已更新快速启动脚本" -ForegroundColor Green
    } else {
        Write-Host "⚠️  快速启动脚本已包含云MCP配置" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️  快速启动脚本不存在，跳过更新" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 配置完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "使用方式:" -ForegroundColor Yellow
Write-Host "  1. 使用新脚本启动: .\tools\mcp_bus\启动MCP_带云转发.ps1" -ForegroundColor White
Write-Host "  2. 或使用快速启动: .\快速启动本地MCP.ps1" -ForegroundColor White
Write-Host ""
Write-Host "验证转发:" -ForegroundColor Yellow
Write-Host "  测试云MCP连接: curl $cloudMcpUrl" -ForegroundColor White
Write-Host ""
