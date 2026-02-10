# Create Desktop Shortcut for MCP Server Background Service
# Fixed version - creates shortcut that runs in background

$ErrorActionPreference = "Stop"

Write-Host "=== Creating Desktop Shortcut for MCP Background Service ===" -ForegroundColor Cyan
Write-Host ""

# Get desktop path
$desktopPath = [Environment]::GetFolderPath("Desktop")
$repoRoot = "d:\quantsys"
$mcpBusDir = "$repoRoot\tools\mcp_bus"

# Background service script path (using English filename to avoid encoding issues)
$backgroundScript = Join-Path $mcpBusDir "start_mcp_background_service.ps1"

# Check if script exists
if (-not (Test-Path $backgroundScript)) {
    Write-Host "ERROR: Background service script not found: $backgroundScript" -ForegroundColor Red
    Write-Host "Please ensure the script exists." -ForegroundColor Yellow
    exit 1
}

Write-Host "Script path: $backgroundScript" -ForegroundColor Gray
Write-Host ""

# Shortcut path
$shortcutName = "启动MCP服务器_后台服务.lnk"
$shortcutPath = Join-Path $desktopPath $shortcutName

# Remove existing shortcut if exists
if (Test-Path $shortcutPath) {
    Write-Host "Removing existing shortcut..." -ForegroundColor Yellow
    try {
        Remove-Item $shortcutPath -Force -ErrorAction Stop
        Write-Host "OK: Existing shortcut removed" -ForegroundColor Green
    } catch {
        Write-Host "WARNING: Failed to remove existing shortcut: $_" -ForegroundColor Yellow
    }
}

Write-Host "Creating shortcut..." -ForegroundColor Yellow

try {
    # Create shortcut
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    
    # Set shortcut properties
    $Shortcut.TargetPath = "powershell.exe"
    
    # Arguments: -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File
    # Hidden window for background service
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$backgroundScript`""
    
    $Shortcut.WorkingDirectory = $mcpBusDir
    $Shortcut.Description = "启动MCP服务器后台服务（无窗口，常驻后台，自动重启）"
    $Shortcut.IconLocation = "powershell.exe,0"
    
    # Save shortcut
    $Shortcut.Save()
    
    Write-Host ""
    Write-Host "SUCCESS: Desktop shortcut created!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Shortcut Details:" -ForegroundColor Yellow
    Write-Host "  Name: $shortcutName" -ForegroundColor Gray
    Write-Host "  Location: $shortcutPath" -ForegroundColor Gray
    Write-Host "  Target: $backgroundScript" -ForegroundColor Gray
    Write-Host "  Window Style: Hidden (background)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Features:" -ForegroundColor Yellow
    Write-Host "  - Runs in background (no window)" -ForegroundColor White
    Write-Host "  - Auto-restart on crash" -ForegroundColor White
    Write-Host "  - Scheduled restart (every 24 hours)" -ForegroundColor White
    Write-Host "  - Health check monitoring" -ForegroundColor White
    Write-Host "  - Logs: d:\quantsys\logs\mcp_server.log" -ForegroundColor White
    Write-Host ""
    Write-Host "Double-click the shortcut to start the background service." -ForegroundColor Cyan
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "ERROR: Failed to create shortcut: $_" -ForegroundColor Red
    $errorMsg = $_.Exception.Message
    Write-Host "Error details: $errorMsg" -ForegroundColor Red
    if ($_.Exception.InnerException) {
        $innerMsg = $_.Exception.InnerException.Message
        Write-Host "Inner error: $innerMsg" -ForegroundColor Red
    }
    exit 1
}
