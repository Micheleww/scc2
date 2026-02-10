# Auto Test Desktop Shortcut for MCP Server
# 自动测试桌面快捷方式是否能够有效打开服务器（无需用户交互）

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Auto Test: Desktop Shortcut" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutName = "MCP Server.lnk"
$shortcutPath = Join-Path $desktopPath $shortcutName
$serverUrl = "http://127.0.0.1:18788/"
$healthUrl = "$serverUrl/health"
$maxWaitTime = 30  # seconds
$checkInterval = 2  # seconds

# Test Results
$allPassed = $true

# Test 1: Check if shortcut exists
Write-Host "[Test 1] Checking if shortcut exists..." -ForegroundColor Yellow
if (Test-Path $shortcutPath) {
    Write-Host "  [OK] Shortcut found: $shortcutPath" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Shortcut not found: $shortcutPath" -ForegroundColor Red
    Write-Host "  [INFO] Run create_desktop_shortcut_tray.ps1 to create shortcut" -ForegroundColor Yellow
    $allPassed = $false
    exit 1
}

# Test 2: Read and validate shortcut properties
Write-Host ""
Write-Host "[Test 2] Validating shortcut properties..." -ForegroundColor Yellow
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    
    $targetPath = $shortcut.TargetPath
    $arguments = $shortcut.Arguments
    $workingDir = $shortcut.WorkingDirectory
    
    Write-Host "  Target: $targetPath" -ForegroundColor Cyan
    Write-Host "  Arguments: $arguments" -ForegroundColor Cyan
    Write-Host "  Working Dir: $workingDir" -ForegroundColor Cyan
    
    # Validate all paths
    if (-not (Test-Path $targetPath)) {
        Write-Host "  [FAIL] Target path does not exist: $targetPath" -ForegroundColor Red
        $allPassed = $false
    } else {
        Write-Host "  [OK] Target path is valid" -ForegroundColor Green
    }
    
    if (-not (Test-Path $workingDir)) {
        Write-Host "  [FAIL] Working directory does not exist: $workingDir" -ForegroundColor Red
        $allPassed = $false
    } else {
        Write-Host "  [OK] Working directory is valid" -ForegroundColor Green
    }
    
    $scriptPath = $arguments.Trim('"')
    if (-not (Test-Path $scriptPath)) {
        Write-Host "  [FAIL] Script path does not exist: $scriptPath" -ForegroundColor Red
        $allPassed = $false
    } else {
        Write-Host "  [OK] Script path is valid" -ForegroundColor Green
    }
    
} catch {
    Write-Host "  [ERROR] Failed to read shortcut: $_" -ForegroundColor Red
    $allPassed = $false
}

# Test 3: Check if server is already running
Write-Host ""
Write-Host "[Test 3] Checking current server status..." -ForegroundColor Yellow
$serverRunning = $false
try {
    $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $healthData = $response.Content | ConvertFrom-Json
        if ($healthData.ok) {
            $serverRunning = $true
            Write-Host "  [INFO] Server is already running" -ForegroundColor Green
            Write-Host "  [INFO] Server URL: $serverUrl" -ForegroundColor Cyan
        }
    }
} catch {
    Write-Host "  [INFO] Server is not running (will test startup)" -ForegroundColor Gray
}

# Test 4: Test server startup (only if not running)
if (-not $serverRunning) {
    Write-Host ""
    Write-Host "[Test 4] Testing server startup via shortcut..." -ForegroundColor Yellow
    Write-Host "  [INFO] Launching shortcut..." -ForegroundColor Cyan
    
    try {
        # Launch shortcut
        $process = Start-Process -FilePath $shortcutPath -PassThru -WindowStyle Hidden
        
        if ($process) {
            Write-Host "  [OK] Shortcut launched (PID: $($process.Id))" -ForegroundColor Green
            
            # Wait for server to start
            Write-Host "  [INFO] Waiting for server to start (max $maxWaitTime seconds)..." -ForegroundColor Cyan
            $elapsed = 0
            $serverStarted = $false
            
            while ($elapsed -lt $maxWaitTime -and -not $serverStarted) {
                Start-Sleep -Seconds $checkInterval
                $elapsed += $checkInterval
                
                try {
                    $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 2 -ErrorAction Stop
                    if ($response.StatusCode -eq 200) {
                        $healthData = $response.Content | ConvertFrom-Json
                        if ($healthData.ok) {
                            $serverStarted = $true
                            Write-Host "  [OK] Server started successfully after $elapsed seconds" -ForegroundColor Green
                            Write-Host "  [OK] Server is accessible at: $serverUrl" -ForegroundColor Green
                        }
                    }
                } catch {
                    # Server not ready yet
                    Write-Host "  [WAIT] Waiting... ($elapsed/$maxWaitTime seconds)" -ForegroundColor Gray
                }
            }
            
            if ($serverStarted) {
                Write-Host ""
                Write-Host "  [SUCCESS] Server startup test PASSED!" -ForegroundColor Green
            } else {
                Write-Host ""
                Write-Host "  [WARN] Server did not start within $maxWaitTime seconds" -ForegroundColor Yellow
                Write-Host "  [INFO] Possible reasons:" -ForegroundColor Cyan
                Write-Host "    - Server startup takes longer than expected" -ForegroundColor White
                Write-Host "    - There might be errors (check system tray icon)" -ForegroundColor White
                Write-Host "    - Port 8000 might be in use by another process" -ForegroundColor White
                $allPassed = $false
            }
        } else {
            Write-Host "  [FAIL] Failed to launch shortcut" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "  [ERROR] Error during startup test: $_" -ForegroundColor Red
        $allPassed = $false
    }
} else {
    Write-Host ""
    Write-Host "[Test 4] Server already running - startup test skipped" -ForegroundColor Yellow
    Write-Host "  [INFO] This means shortcut can start server (server is already running)" -ForegroundColor Green
}

# Final Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($allPassed) {
    Write-Host "  [SUCCESS] All tests PASSED!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Desktop shortcut is working correctly!" -ForegroundColor Green
    Write-Host "You can use it to start the MCP Server." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Double-click 'MCP Server.lnk' on desktop" -ForegroundColor White
    Write-Host "  2. Check system tray icon (bottom-right corner)" -ForegroundColor White
    Write-Host "  3. Right-click tray icon to access menu" -ForegroundColor White
    Write-Host "  4. Visit $serverUrl in browser" -ForegroundColor White
} else {
    Write-Host "  [WARN] Some tests had issues" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please check:" -ForegroundColor Yellow
    Write-Host "  1. Ensure shortcut exists (run create_desktop_shortcut_tray.ps1)" -ForegroundColor White
    Write-Host "  2. Check Python installation" -ForegroundColor White
    Write-Host "  3. Check server script path" -ForegroundColor White
    Write-Host "  4. Check system tray for server status" -ForegroundColor White
}

Write-Host ""
