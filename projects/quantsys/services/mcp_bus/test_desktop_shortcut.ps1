# Test Desktop Shortcut for MCP Server
# 测试桌面快捷方式是否能够有效打开服务器

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Desktop Shortcut Test for MCP Server" -ForegroundColor Cyan
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
$testResults = @{
    "ShortcutExists" = $false
    "ShortcutValid" = $false
    "TargetPathValid" = $false
    "WorkingDirectoryValid" = $false
    "ServerStartable" = $false
    "ServerStarted" = $false
    "ServerAccessible" = $false
}

# Test 1: Check if shortcut exists
Write-Host "[Test 1] Checking if shortcut exists..." -ForegroundColor Yellow
if (Test-Path $shortcutPath) {
    $testResults["ShortcutExists"] = $true
    Write-Host "  [OK] Shortcut found: $shortcutPath" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Shortcut not found: $shortcutPath" -ForegroundColor Red
    Write-Host "  [INFO] Run create_desktop_shortcut_tray.ps1 to create shortcut" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Test Results Summary:" -ForegroundColor Cyan
    Write-Host "  Shortcut Exists: $($testResults['ShortcutExists'])" -ForegroundColor $(if ($testResults['ShortcutExists']) { "Green" } else { "Red" })
    exit 1
}

# Test 2: Read shortcut properties
Write-Host ""
Write-Host "[Test 2] Reading shortcut properties..." -ForegroundColor Yellow
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    
    $targetPath = $shortcut.TargetPath
    $arguments = $shortcut.Arguments
    $workingDir = $shortcut.WorkingDirectory
    $description = $shortcut.Description
    
    Write-Host "  Target Path: $targetPath" -ForegroundColor Cyan
    Write-Host "  Arguments: $arguments" -ForegroundColor Cyan
    Write-Host "  Working Directory: $workingDir" -ForegroundColor Cyan
    Write-Host "  Description: $description" -ForegroundColor Cyan
    
    # Validate target path
    if (Test-Path $targetPath) {
        $testResults["TargetPathValid"] = $true
        Write-Host "  [OK] Target path is valid" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Target path does not exist: $targetPath" -ForegroundColor Red
    }
    
    # Validate working directory
    if (Test-Path $workingDir) {
        $testResults["WorkingDirectoryValid"] = $true
        Write-Host "  [OK] Working directory is valid" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Working directory does not exist: $workingDir" -ForegroundColor Red
    }
    
    # Validate script path in arguments
    $scriptPath = $arguments.Trim('"')
    if (Test-Path $scriptPath) {
        $testResults["ShortcutValid"] = $true
        Write-Host "  [OK] Script path in arguments is valid" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Script path in arguments does not exist: $scriptPath" -ForegroundColor Red
    }
    
} catch {
    Write-Host "  [ERROR] Failed to read shortcut properties: $_" -ForegroundColor Red
}

# Test 3: Check if server is already running
Write-Host ""
Write-Host "[Test 3] Checking if server is already running..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $healthData = $response.Content | ConvertFrom-Json
        if ($healthData.ok) {
            Write-Host "  [INFO] Server is already running" -ForegroundColor Green
            Write-Host "  [INFO] Skipping server start test (server already running)" -ForegroundColor Yellow
            $testResults["ServerAccessible"] = $true
            $testResults["ServerStarted"] = $true
        }
    }
} catch {
    Write-Host "  [INFO] Server is not running (this is OK for testing)" -ForegroundColor Gray
}

# Test 4: Test if shortcut can start server (only if server is not running)
if (-not $testResults["ServerStarted"]) {
    Write-Host ""
    Write-Host "[Test 4] Testing if shortcut can start server..." -ForegroundColor Yellow
    Write-Host "  [INFO] This test will:" -ForegroundColor Cyan
    Write-Host "    1. Launch shortcut in background" -ForegroundColor White
    Write-Host "    2. Wait for server to start (max $maxWaitTime seconds)" -ForegroundColor White
    Write-Host "    3. Check if server is accessible" -ForegroundColor White
    Write-Host ""
    
    $userChoice = Read-Host "  Do you want to test server startup? (Y/N)"
    if ($userChoice -eq "Y" -or $userChoice -eq "y") {
        try {
            # Launch shortcut
            Write-Host "  [INFO] Launching shortcut..." -ForegroundColor Cyan
            $process = Start-Process -FilePath $shortcutPath -PassThru -WindowStyle Hidden
            
            if ($process) {
                Write-Host "  [OK] Shortcut launched (PID: $($process.Id))" -ForegroundColor Green
                $testResults["ServerStartable"] = $true
                
                # Wait for server to start
                Write-Host "  [INFO] Waiting for server to start..." -ForegroundColor Cyan
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
                                $testResults["ServerStarted"] = $true
                                $testResults["ServerAccessible"] = $true
                                Write-Host "  [OK] Server started successfully after $elapsed seconds" -ForegroundColor Green
                            }
                        }
                    } catch {
                        # Server not ready yet, continue waiting
                        Write-Host "  [WAIT] Waiting for server... ($elapsed/$maxWaitTime seconds)" -ForegroundColor Gray
                    }
                }
                
                if (-not $serverStarted) {
                    Write-Host "  [WARN] Server did not start within $maxWaitTime seconds" -ForegroundColor Yellow
                    Write-Host "  [INFO] This might be normal if:" -ForegroundColor Cyan
                    Write-Host "    - Server is already running (check with another instance)" -ForegroundColor White
                    Write-Host "    - Server startup takes longer than expected" -ForegroundColor White
                    Write-Host "    - There are errors in server startup (check logs)" -ForegroundColor White
                }
            } else {
                Write-Host "  [FAIL] Failed to launch shortcut" -ForegroundColor Red
            }
        } catch {
            Write-Host "  [ERROR] Error during server startup test: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "  [SKIP] Server startup test skipped by user" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "[Test 4] Skipping server startup test (server already running)" -ForegroundColor Yellow
}

# Test 5: Verify server accessibility (if server is running)
if ($testResults["ServerStarted"] -or $testResults["ServerAccessible"]) {
    Write-Host ""
    Write-Host "[Test 5] Verifying server accessibility..." -ForegroundColor Yellow
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $healthData = $response.Content | ConvertFrom-Json
            Write-Host "  [OK] Server is accessible" -ForegroundColor Green
            Write-Host "  Server Status: $($healthData.status)" -ForegroundColor Cyan
            Write-Host "  Server URL: $serverUrl" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "  [FAIL] Server is not accessible: $_" -ForegroundColor Red
        $testResults["ServerAccessible"] = $false
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Test Results Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allTests = @(
    @{Name = "Shortcut Exists"; Key = "ShortcutExists"},
    @{Name = "Shortcut Valid"; Key = "ShortcutValid"},
    @{Name = "Target Path Valid"; Key = "TargetPathValid"},
    @{Name = "Working Directory Valid"; Key = "WorkingDirectoryValid"},
    @{Name = "Server Startable"; Key = "ServerStartable"},
    @{Name = "Server Started"; Key = "ServerStarted"},
    @{Name = "Server Accessible"; Key = "ServerAccessible"}
)

$passedTests = 0
$totalTests = 0

foreach ($test in $allTests) {
    $totalTests++
    $result = $testResults[$test.Key]
    $color = if ($result) { "Green" } else { "Red" }
    $status = if ($result) { "[PASS]" } else { "[FAIL]" }
    Write-Host "  $status $($test.Name): $result" -ForegroundColor $color
    if ($result) { $passedTests++ }
}

Write-Host ""
Write-Host "Overall Result: $passedTests/$totalTests tests passed" -ForegroundColor $(if ($passedTests -eq $totalTests) { "Green" } else { "Yellow" })

if ($passedTests -eq $totalTests) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  ALL TESTS PASSED!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Desktop shortcut is working correctly!" -ForegroundColor Green
    Write-Host "You can use it to start the MCP Server." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  SOME TESTS FAILED" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please check the errors above and:" -ForegroundColor Yellow
    Write-Host "  1. Ensure shortcut exists (run create_desktop_shortcut_tray.ps1)" -ForegroundColor White
    Write-Host "  2. Check Python installation" -ForegroundColor White
    Write-Host "  3. Check server script path" -ForegroundColor White
    Write-Host "  4. Check server logs for errors" -ForegroundColor White
}

Write-Host ""
