@echo off
REM ========================================
REM MCP Server Installation (Run as Administrator)
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
    echo 2. Select "Windows PowerShell (Admin)"
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

REM Execute PowerShell installation script
echo Executing installation script...
echo.
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0install_all.ps1"

if %errorLevel% equ 0 (
    echo.
    echo ========================================
    echo   Installation Complete!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   Installation encountered errors
    echo ========================================
)

echo.
pause
