@echo off
REM ========================================
REM Create Desktop Shortcut Only
REM No administrator privileges required
REM ========================================

REM Change to script directory
cd /d "%~dp0"

echo.
echo ========================================
echo   Create Desktop Shortcut
echo ========================================
echo.
echo This operation does not require administrator privileges
echo.

REM Execute PowerShell script
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0create_desktop_shortcut_tray.ps1"

if %errorLevel% equ 0 (
    echo.
    echo ========================================
    echo   Shortcut Created Successfully!
    echo ========================================
    echo.
    echo You can now double-click the desktop shortcut to start the server
    echo.
) else (
    echo.
    echo ========================================
    echo   Failed to Create Shortcut
    echo ========================================
    echo.
)

pause
