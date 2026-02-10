# Create Desktop Shortcuts for MCP Server
# Fixed version - creates both normal and background service shortcuts

$ErrorActionPreference = "Stop"

Write-Host "=== Creating MCP Server Desktop Shortcuts ===" -ForegroundColor Cyan
Write-Host ""

# Get desktop path
$desktopPath = [Environment]::GetFolderPath("Desktop")
$repoRoot = "d:\quantsys"
$mcpBusDir = "$repoRoot\tools\mcp_bus"

# Script paths (using English filenames to avoid encoding issues)
$normalScript = Join-Path $mcpBusDir "start_mcp_server.ps1"
$backgroundScript = Join-Path $mcpBusDir "start_mcp_background_service.ps1"

# Scripts configuration
$scripts = @(
    @{
        Name = "启动MCP服务器.lnk"
        Script = $normalScript
        Description = "启动MCP服务器（普通模式，窗口可见，自动重启）"
        WindowStyle = "Normal"
        Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -NoExit -File `"$normalScript`""
    },
    @{
        Name = "启动MCP服务器_后台服务.lnk"
        Script = $backgroundScript
        Description = "启动MCP服务器（后台服务模式，无窗口，常驻后台，自动重启）"
        WindowStyle = "Hidden"
        Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$backgroundScript`""
    }
)

$created = 0
$updated = 0
$skipped = 0
$failed = 0

foreach ($item in $scripts) {
    $shortcutPath = Join-Path $desktopPath $item.Name
    $scriptPath = $item.Script
    
    Write-Host "Processing: $($item.Name)..." -ForegroundColor Yellow
    
    # Check if script exists
    if (-not (Test-Path $scriptPath)) {
        Write-Host "  WARNING: Script not found: $scriptPath" -ForegroundColor Yellow
        $skipped++
        continue
    }
    
    try {
        # Remove existing shortcut to ensure clean creation
        if (Test-Path $shortcutPath) {
            Remove-Item $shortcutPath -Force -ErrorAction SilentlyContinue
            Write-Host "  Removing existing shortcut..." -ForegroundColor Gray
        }
        
        # Create shortcut
        $WScriptShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WScriptShell.CreateShortcut($shortcutPath)
        $Shortcut.TargetPath = "powershell.exe"
        $Shortcut.Arguments = $item.Arguments
        $Shortcut.WorkingDirectory = $mcpBusDir
        $Shortcut.Description = $item.Description
        $Shortcut.IconLocation = "powershell.exe,0"
        $Shortcut.Save()
        
        if (Test-Path $shortcutPath) {
            Write-Host "  SUCCESS: Created/Updated" -ForegroundColor Green
            if (Test-Path $shortcutPath -NewerThan (Get-Date).AddMinutes(-1)) {
                $created++
            } else {
                $updated++
            }
        } else {
            Write-Host "  FAILED: Shortcut file not created" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "  FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }
    Write-Host ""
}

Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "  Created: $created" -ForegroundColor Green
Write-Host "  Updated: $updated" -ForegroundColor Yellow
Write-Host "  Skipped: $skipped" -ForegroundColor Yellow
Write-Host "  Failed: $failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
Write-Host ""
Write-Host "Shortcuts location: $desktopPath" -ForegroundColor Cyan
Write-Host ""

if ($created -gt 0 -or $updated -gt 0) {
    Write-Host "Shortcut Details:" -ForegroundColor Yellow
    foreach ($item in $scripts) {
        $shortcutPath = Join-Path $desktopPath $item.Name
        if (Test-Path $shortcutPath) {
            Write-Host "  - $($item.Name): $($item.Description)" -ForegroundColor White
        }
    }
    Write-Host ""
    Write-Host "Double-click the shortcuts to start the server:" -ForegroundColor Cyan
    Write-Host "  - Normal mode: Shows window, auto-restart enabled" -ForegroundColor White
    Write-Host "  - Background mode: Hidden window, runs in background" -ForegroundColor White
    Write-Host ""
}
