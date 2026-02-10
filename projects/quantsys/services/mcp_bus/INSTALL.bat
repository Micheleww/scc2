@echo off
REM ========================================
REM MCP Server Complete Installation
REM Right-click and select "Run as administrator"
REM ========================================

REM Change to script directory
cd /d "%~dp0"

REM Check administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo ========================================
    echo   Administrator privileges required
    echo ========================================
    echo.
    echo Please right-click this file and select "Run as administrator"
    echo.
    echo Or:
    echo 1. Press Win+X
    echo 2. Select "Windows PowerShell (Admin)" or "Terminal (Admin)"
    echo 3. Run: cd d:\quantsys\tools\mcp_bus
    echo 4. Run: powershell -ExecutionPolicy Bypass -File install_all.ps1
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   MCP Server Complete Installation
echo ========================================
echo.
echo Administrator privileges detected
echo.

echo [1/3] Creating desktop shortcut...
echo.
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0create_desktop_shortcut_tray.ps1"
if %errorLevel% equ 0 (
    echo [OK] Desktop shortcut created
) else (
    echo [ERROR] Failed to create desktop shortcut
)
echo.

echo [2/3] Setting up autostart...
echo.
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0setup_autostart_tray.ps1"
if %errorLevel% equ 0 (
    echo [OK] Autostart configured
) else (
    echo [ERROR] Failed to setup autostart
    echo Tip: Make sure you run as administrator
)
echo.

echo [3/3] Checking dependencies...
echo.
python.exe -c "import pystray, PIL" >nul 2>&1
if %errorLevel% neq 0 (
    echo Installing pystray and pillow...
    python.exe -m pip install pystray pillow >nul 2>&1
    if %errorLevel% equ 0 (
        echo [OK] Dependencies installed
    ) else (
        echo [WARNING] Failed to install dependencies
        echo You can install manually: pip install pystray pillow
    )
) else (
    echo [OK] Dependencies already installed
)
echo.

echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo Usage:
echo 1. Double-click desktop shortcut to start server
echo 2. Server runs in background, check system tray icon
echo 3. Right-click tray icon to access menu
echo 4. Server will auto-start on boot
echo.
echo Tray icon colors:
echo   [Green]  Server running normally
echo   [Yellow] Some services abnormal
echo   [Red]    Server unreachable
echo   [Gray]   Starting or status unknown
echo.
pause
