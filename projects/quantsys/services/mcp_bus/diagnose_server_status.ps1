# 诊断服务器状态问题
# 检查为什么服务器状态显示"无法访问"

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MCP Server Status Diagnosis" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$serverUrl = "http://127.0.0.1:18788/"
$healthUrl = "$serverUrl/health"

# 1. 检查端口状态
Write-Host "[1] Checking port 8000 status..." -ForegroundColor Yellow
$portStatus = netstat -ano | findstr ":8000"
if ($portStatus) {
    Write-Host "  Port 8000 connections:" -ForegroundColor Cyan
    $portStatus | ForEach-Object { Write-Host "    $_" -ForegroundColor White }
} else {
    Write-Host "  [WARN] Port 8000 is not in use" -ForegroundColor Yellow
}

# 检查是否有LISTENING状态
$listening = $portStatus | Select-String "LISTENING"
if ($listening) {
    Write-Host "  [OK] Server is listening on port 8000" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Server is NOT listening on port 8000" -ForegroundColor Red
}

Write-Host ""

# 2. 检查Python进程
Write-Host "[2] Checking Python processes..." -ForegroundColor Yellow
$pythonProcesses = tasklist | findstr python
if ($pythonProcesses) {
    Write-Host "  Python processes found:" -ForegroundColor Cyan
    $pythonProcesses | ForEach-Object { Write-Host "    $_" -ForegroundColor White }
    
    # 检查pythonw.exe
    $pythonwProcesses = tasklist | findstr pythonw
    if ($pythonwProcesses) {
        Write-Host "  [INFO] pythonw.exe processes (background):" -ForegroundColor Cyan
        $pythonwProcesses | ForEach-Object { Write-Host "    $_" -ForegroundColor White }
    }
} else {
    Write-Host "  [WARN] No Python processes found" -ForegroundColor Yellow
}

Write-Host ""

# 3. 检查服务器健康状态
Write-Host "[3] Checking server health endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $healthData = $response.Content | ConvertFrom-Json
        Write-Host "  [OK] Server is accessible" -ForegroundColor Green
        Write-Host "  Status: $($healthData.status)" -ForegroundColor Cyan
        Write-Host "  OK: $($healthData.ok)" -ForegroundColor Cyan
    }
} catch {
    Write-Host "  [FAIL] Server is not accessible: $_" -ForegroundColor Red
    Write-Host "  [INFO] This means server is not running or not responding" -ForegroundColor Yellow
}

Write-Host ""

# 4. 检查单实例互斥体
Write-Host "[4] Checking for single instance mutex..." -ForegroundColor Yellow
Write-Host "  [INFO] Server uses mutex: Global\\MCP_Bus_Server_Tray_Instance" -ForegroundColor Cyan
Write-Host "  [INFO] If another instance is running, new instance will be blocked" -ForegroundColor Cyan

# 5. 检查可能的错误原因
Write-Host ""
Write-Host "[5] Possible issues:" -ForegroundColor Yellow

$issues = @()

# 检查端口是否被其他程序占用
$allPort8000 = netstat -ano | findstr ":8000"
$otherProcesses = $allPort8000 | Where-Object { $_ -notmatch "python" -and $_ -notmatch "pythonw" }
if ($otherProcesses) {
    $issues += "Port 8000 might be used by another program"
    Write-Host "  [WARN] Port 8000 might be used by another program" -ForegroundColor Yellow
}

# 检查服务器脚本是否存在
$scriptPath = "d:\quantsys\tools\mcp_bus\server_tray_enhanced.py"
if (-not (Test-Path $scriptPath)) {
    $issues += "Server script not found"
    Write-Host "  [FAIL] Server script not found: $scriptPath" -ForegroundColor Red
} else {
    Write-Host "  [OK] Server script exists: $scriptPath" -ForegroundColor Green
}

# 检查工作目录
$workDir = "d:\quantsys\tools\mcp_bus"
if ($workDir -and (Test-Path $workDir)) {
    Write-Host "  [OK] Working directory exists: $workDir" -ForegroundColor Green
} else {
    $issues += "Working directory not found"
    Write-Host "  [FAIL] Working directory not found: $workDir" -ForegroundColor Red
}

Write-Host ""

# 6. 建议的解决方案
Write-Host "[6] Recommended solutions:" -ForegroundColor Yellow
Write-Host ""

if (-not $listening) {
    Write-Host "  Solution 1: Stop all Python processes and restart" -ForegroundColor Cyan
    Write-Host "    taskkill /F /IM pythonw.exe" -ForegroundColor White
    Write-Host "    taskkill /F /IM python.exe" -ForegroundColor White
    Write-Host "    Then double-click desktop shortcut again" -ForegroundColor White
    Write-Host ""
    
    Write-Host "  Solution 2: Check system tray icon" -ForegroundColor Cyan
    Write-Host "    - Look for system tray icon (bottom-right corner)" -ForegroundColor White
    Write-Host "    - Right-click icon to see status" -ForegroundColor White
    Write-Host "    - Check if there are error messages" -ForegroundColor White
    Write-Host ""
    
    Write-Host "  Solution 3: Check server logs" -ForegroundColor Cyan
    Write-Host "    - Check if there are log files in: d:\quantsys\tools\mcp_bus\logs" -ForegroundColor White
    Write-Host "    - Or check Windows Event Viewer" -ForegroundColor White
    Write-Host ""
    
    Write-Host "  Solution 4: Start server manually to see errors" -ForegroundColor Cyan
    Write-Host "    cd d:\quantsys\tools\mcp_bus" -ForegroundColor White
    Write-Host "    python server_tray_enhanced.py" -ForegroundColor White
    Write-Host "    (This will show errors in console)" -ForegroundColor White
    Write-Host ""
}

# 7. 快速修复命令
Write-Host "[7] Quick fix commands:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Stop all server processes:" -ForegroundColor Cyan
Write-Host "    taskkill /F /IM pythonw.exe /T" -ForegroundColor White
Write-Host ""
Write-Host "  Restart server via shortcut:" -ForegroundColor Cyan
Write-Host "    Double-click 'MCP Server.lnk' on desktop" -ForegroundColor White
Write-Host ""
Write-Host "  Or start manually:" -ForegroundColor Cyan
Write-Host "    cd d:\quantsys\tools\mcp_bus" -ForegroundColor White
Write-Host "    pythonw server_tray_enhanced.py" -ForegroundColor White
Write-Host ""

# 总结
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Diagnosis Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($listening) {
    Write-Host "  [OK] Server appears to be running" -ForegroundColor Green
    Write-Host "  [INFO] If status shows '无法访问', wait a few seconds for status check" -ForegroundColor Yellow
} else {
    Write-Host "  [FAIL] Server is NOT running" -ForegroundColor Red
    Write-Host "  [INFO] Follow the solutions above to fix the issue" -ForegroundColor Yellow
}

Write-Host ""
