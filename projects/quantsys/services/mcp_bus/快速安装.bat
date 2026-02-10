@echo off
REM ========================================
REM Quick Installation Script
REM Note: Requires administrator for autostart
REM ========================================

REM Change to script directory
cd /d "%~dp0"

echo.
echo ========================================
echo   MCP Server Quick Installation
echo ========================================
echo.

REM Check administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARNING] Not running as administrator
    echo.
    echo Autostart requires administrator privileges
    echo Desktop shortcut can be created normally
    echo.
    echo Suggestions:
    echo 1. Right-click "安装.bat" and select "Run as administrator"
    echo 2. Or run "仅创建快捷方式.bat" (no admin needed)
    echo.
    pause
    exit /b 1
)

echo [1/3] Creating desktop shortcut...
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0create_desktop_shortcut_tray.ps1"
if %errorLevel% equ 0 (
    echo [OK] Desktop shortcut created
) else (
    echo [ERROR] Failed to create desktop shortcut
)
echo.

echo [2/3] Setting up autostart...
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0setup_autostart_tray.ps1"
if %errorLevel% equ 0 (
    echo [OK] Autostart configured
) else (
    echo [ERROR] Failed to setup autostart (may need administrator)
)
echo.

echo [3/3] Checking dependencies...
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
echo 4. Server will auto-start on boot (if configured)
echo.
echo Tray icon colors:
echo   [Green]  Server running normally
echo   [Yellow] Some services abnormal
echo   [Red]    Server unreachable
echo   [Gray]   Starting or status unknown
echo.
pause
