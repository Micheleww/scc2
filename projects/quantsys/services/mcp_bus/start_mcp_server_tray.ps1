# Start MCP Server with System Tray Icon (Hidden Window)
# 后台启动MCP服务器，在系统托盘显示图标，不显示任务栏窗口

$ErrorActionPreference = "Continue"

# 检查MCP目录
$mcpDir = "d:\quantsys\tools\mcp_bus"
if (-not (Test-Path $mcpDir)) {
    Write-Host "ERROR: MCP directory not found: $mcpDir" -ForegroundColor Red
    exit 1
}

Set-Location $mcpDir

# 检查Python
try {
    $pythonCheck = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Python not found" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: Python check failed: $_" -ForegroundColor Red
    exit 1
}

# 检查pystray依赖
Write-Host "Checking dependencies..." -ForegroundColor Yellow
try {
    $pystrayCheck = python -c "import pystray" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing pystray and pillow..." -ForegroundColor Yellow
        pip install pystray pillow 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "WARNING: Failed to install pystray, tray icon will not be available" -ForegroundColor Yellow
            Write-Host "You can install manually: pip install pystray pillow" -ForegroundColor Yellow
        } else {
            Write-Host "Dependencies installed successfully" -ForegroundColor Green
        }
    } else {
        Write-Host "Dependencies OK" -ForegroundColor Green
    }
} catch {
    Write-Host "WARNING: pystray check failed, tray icon may not be available" -ForegroundColor Yellow
    Write-Host "Error: $_" -ForegroundColor Red
}

# 使用PowerShell隐藏窗口启动Python脚本
# 使用Start-Process的-WindowStyle Hidden参数
# 优先使用增强版托盘程序（带状态监控）
$scriptPath = Join-Path $mcpDir "server_tray_enhanced.py"
if (-not (Test-Path $scriptPath)) {
    # 回退到基础版本
    $scriptPath = Join-Path $mcpDir "server_tray.py"
}

# 检查脚本是否存在
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "Starting MCP Server with Enhanced System Tray..." -ForegroundColor Cyan
Write-Host "Server URL: http://127.0.0.1:18788/" -ForegroundColor Cyan
Write-Host "Look for the tray icon in the system tray (bottom-right corner)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tray icon colors:" -ForegroundColor Yellow
Write-Host "  🟢 Green: Server healthy, all services OK" -ForegroundColor Green
Write-Host "  🟡 Yellow: Server running but some services abnormal" -ForegroundColor Yellow
Write-Host "  🔴 Red: Server unreachable or error" -ForegroundColor Red
Write-Host "  ⚪ Gray: Server starting or status unknown" -ForegroundColor Gray
Write-Host ""

# 启动进程，隐藏窗口
# 使用pythonw.exe（无窗口Python）如果可用
$pythonExe = "python"
$pythonwExe = $pythonExe -replace "python\.exe$", "pythonw.exe"
if (Test-Path $pythonwExe) {
    $pythonExe = $pythonwExe
}

$process = Start-Process -FilePath $pythonExe -ArgumentList "`"$scriptPath`"" -WindowStyle Hidden -PassThru

if ($process) {
    Write-Host "MCP Server started (PID: $($process.Id))" -ForegroundColor Green
    Write-Host "The server is running in the background with a system tray icon." -ForegroundColor Green
    Write-Host "Right-click the tray icon to access the menu." -ForegroundColor Green
    Write-Host ""
    Write-Host "To stop the server, right-click the tray icon and select 'Exit'." -ForegroundColor Yellow
} else {
    Write-Host "ERROR: Failed to start server" -ForegroundColor Red
    exit 1
}
