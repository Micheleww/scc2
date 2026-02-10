# Create desktop shortcut for MCP Server (Tray version)
# Creates ONE shortcut that starts server in background with tray icon

$ErrorActionPreference = "Continue"

Write-Host "=== Create MCP Server Desktop Shortcut (Tray Version) ===" -ForegroundColor Cyan
Write-Host ""

# Configuration
$mcpDir = "d:\quantsys\tools\mcp_bus"
$scriptPath = Join-Path $mcpDir "server_tray_enhanced.py"
$desktopPath = [Environment]::GetFolderPath("Desktop")

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

# Create WScript.Shell object
try {
    $shell = New-Object -ComObject WScript.Shell
} catch {
    Write-Host "ERROR: Cannot create WScript.Shell object: $_" -ForegroundColor Red
    exit 1
}

# Remove old shortcuts if they exist
$oldShortcuts = @(
    "MCP Server (Tray Icon).lnk",
    "MCP Server (Tray Launch).lnk",
    "MCP服务器（托盘图标）.lnk",
    "MCP服务器（托盘启动）.lnk"
)

foreach ($oldName in $oldShortcuts) {
    $oldPath = Join-Path $desktopPath $oldName
    if (Test-Path $oldPath) {
        try {
            Remove-Item $oldPath -Force
            Write-Host "Removed old shortcut: $oldName" -ForegroundColor Gray
        } catch {
            # Ignore errors
        }
    }
}

# Create single shortcut: MCP Server
$shortcutName = "MCP Server.lnk"
$shortcutPath = Join-Path $desktopPath $shortcutName

try {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    
    # Find pythonw.exe (windowless Python for background execution)
    $pythonExe = "pythonw"
    $pythonTest = Get-Command pythonw -ErrorAction SilentlyContinue
    if (-not $pythonTest) {
        # Try to find pythonw.exe in common locations
        $pythonPaths = @(
            "$env:ProgramFiles\Python*\pythonw.exe",
            "$env:LocalAppData\Programs\Python\Python*\pythonw.exe",
            "$env:USERPROFILE\AppData\Local\Programs\Python\Python*\pythonw.exe"
        )
        $found = $false
        foreach ($pathPattern in $pythonPaths) {
            $matches = Get-ChildItem -Path $pathPattern -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($matches) {
                $pythonExe = $matches.FullName
                $found = $true
                break
            }
        }
        if (-not $found) {
            $pythonExe = "python"
            Write-Host "Warning: pythonw.exe not found, using python.exe" -ForegroundColor Yellow
            Write-Host "Server will run but may show a console window" -ForegroundColor Yellow
        } else {
            Write-Host "Found pythonw.exe: $pythonExe" -ForegroundColor Green
        }
    } else {
        $pythonExe = $pythonTest.Source
        Write-Host "Using pythonw.exe: $pythonExe" -ForegroundColor Green
    }
    
    # Configure shortcut for background execution with tray icon
    $shortcut.TargetPath = $pythonExe
    $shortcut.Arguments = "`"$scriptPath`""
    $shortcut.WorkingDirectory = $mcpDir
    $shortcut.Description = "Start MCP Server in background with system tray status icon"
    $shortcut.WindowStyle = 7  # Minimized (hidden)
    $shortcut.IconLocation = "$pythonExe, 0"
    $shortcut.Save()
    
    Write-Host ""
    Write-Host "SUCCESS: Desktop shortcut created!" -ForegroundColor Green
    Write-Host "  Name: $shortcutName" -ForegroundColor Cyan
    Write-Host "  Path: $shortcutPath" -ForegroundColor Cyan
    Write-Host "  Target: $pythonExe" -ForegroundColor Cyan
    Write-Host "  Script: $scriptPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  1. Double-click '$shortcutName' on desktop" -ForegroundColor White
    Write-Host "  2. Server starts in background (no window)" -ForegroundColor White
    Write-Host "  3. Check system tray icon (bottom-right corner)" -ForegroundColor White
    Write-Host "  4. Right-click tray icon for menu" -ForegroundColor White
    Write-Host ""
    Write-Host "Tray icon status colors:" -ForegroundColor Yellow
    Write-Host "  [Green]  Server running, all services OK" -ForegroundColor Green
    Write-Host "  [Yellow] Server running, some services abnormal" -ForegroundColor Yellow
    Write-Host "  [Red]    Server unreachable or error" -ForegroundColor Red
    Write-Host "  [Gray]   Server starting or status unknown" -ForegroundColor Gray
    Write-Host ""
    
} catch {
    Write-Host "ERROR: Failed to create shortcut: $_" -ForegroundColor Red
    exit 1
}
