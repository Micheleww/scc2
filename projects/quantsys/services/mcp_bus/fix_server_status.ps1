# 修复服务器状态问题
# 停止所有相关进程并重新启动服务器

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Fix MCP Server Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 停止所有pythonw.exe进程（服务器后台进程）
Write-Host "[1] Stopping all pythonw.exe processes..." -ForegroundColor Yellow
try {
    $pythonwProcesses = Get-Process -Name pythonw -ErrorAction SilentlyContinue
    if ($pythonwProcesses) {
        Write-Host "  Found $($pythonwProcesses.Count) pythonw.exe process(es)" -ForegroundColor Cyan
        foreach ($proc in $pythonwProcesses) {
            Write-Host "    Stopping PID: $($proc.Id)" -ForegroundColor White
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 2
        Write-Host "  [OK] All pythonw.exe processes stopped" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] No pythonw.exe processes found" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [WARN] Error stopping processes: $_" -ForegroundColor Yellow
}

Write-Host ""

# 2. 检查端口8000是否被占用
Write-Host "[2] Checking port 8000..." -ForegroundColor Yellow
$port8000 = netstat -ano | findstr ":8000" | findstr "LISTENING"
if ($port8000) {
    Write-Host "  [WARN] Port 8000 is still in use" -ForegroundColor Yellow
    Write-Host "  [INFO] Finding process using port 8000..." -ForegroundColor Cyan
    $portInfo = netstat -ano | findstr ":8000" | findstr "LISTENING"
    if ($portInfo) {
        $pid = ($portInfo -split '\s+')[-1]
        Write-Host "    Process PID: $pid" -ForegroundColor White
        try {
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "    Process Name: $($proc.ProcessName)" -ForegroundColor White
                Write-Host "    [INFO] You may need to stop this process manually" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "    [INFO] Process not found (may have exited)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "  [OK] Port 8000 is free" -ForegroundColor Green
}

Write-Host ""

# 3. 等待几秒确保进程完全停止
Write-Host "[3] Waiting for processes to fully stop..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
Write-Host "  [OK] Wait complete" -ForegroundColor Green

Write-Host ""

# 4. 检查桌面快捷方式
Write-Host "[4] Checking desktop shortcut..." -ForegroundColor Yellow
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "MCP Server.lnk"

if (Test-Path $shortcutPath) {
    Write-Host "  [OK] Desktop shortcut exists: $shortcutPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "  [INFO] You can now:" -ForegroundColor Cyan
    Write-Host "    1. Double-click the desktop shortcut to start server" -ForegroundColor White
    Write-Host "    2. Wait 10-30 seconds for server to start" -ForegroundColor White
    Write-Host "    3. Check system tray icon (bottom-right corner)" -ForegroundColor White
} else {
    Write-Host "  [WARN] Desktop shortcut not found" -ForegroundColor Yellow
    Write-Host "  [INFO] Creating shortcut..." -ForegroundColor Cyan
    try {
        & "$PSScriptRoot\create_desktop_shortcut_tray.ps1"
        Write-Host "  [OK] Shortcut created" -ForegroundColor Green
    } catch {
        Write-Host "  [ERROR] Failed to create shortcut: $_" -ForegroundColor Red
    }
}

Write-Host ""

# 5. 提供启动选项
Write-Host "[5] Start server options:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Option 1: Use desktop shortcut (Recommended)" -ForegroundColor Cyan
Write-Host "    Double-click 'MCP Server.lnk' on desktop" -ForegroundColor White
Write-Host ""
Write-Host "  Option 2: Start manually (to see errors)" -ForegroundColor Cyan
Write-Host "    cd d:\quantsys\tools\mcp_bus" -ForegroundColor White
Write-Host "    python server_tray_enhanced.py" -ForegroundColor White
Write-Host "    (This will show errors in console)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Option 3: Start in background" -ForegroundColor Cyan
Write-Host "    cd d:\quantsys\tools\mcp_bus" -ForegroundColor White
Write-Host "    pythonw server_tray_enhanced.py" -ForegroundColor White
Write-Host ""

# 6. 自动启动选项
Write-Host "[6] Auto-start server?" -ForegroundColor Yellow
$userChoice = Read-Host "  Start server now? (Y/N)"

if ($userChoice -eq "Y" -or $userChoice -eq "y") {
    Write-Host ""
    Write-Host "  [INFO] Starting server..." -ForegroundColor Cyan
    
    if (Test-Path $shortcutPath) {
        try {
            Start-Process -FilePath $shortcutPath -WindowStyle Hidden
            Write-Host "  [OK] Server startup initiated" -ForegroundColor Green
            Write-Host "  [INFO] Waiting 10 seconds for server to start..." -ForegroundColor Cyan
            Start-Sleep -Seconds 10
            
            # 检查服务器是否启动
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:18788/health" -Method Get -TimeoutSec 3 -ErrorAction Stop
                if ($response.StatusCode -eq 200) {
                    Write-Host "  [SUCCESS] Server is now running!" -ForegroundColor Green
                    Write-Host "  [INFO] Server URL: http://127.0.0.1:18788/" -ForegroundColor Cyan
                }
            } catch {
                Write-Host "  [INFO] Server may still be starting..." -ForegroundColor Yellow
                Write-Host "  [INFO] Check system tray icon for status" -ForegroundColor Yellow
                Write-Host "  [INFO] Or wait a bit longer and check again" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  [ERROR] Failed to start server: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "  [ERROR] Shortcut not found, cannot auto-start" -ForegroundColor Red
    }
} else {
    Write-Host "  [INFO] Server not started automatically" -ForegroundColor Gray
    Write-Host "  [INFO] You can start it manually using the options above" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Fix Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
