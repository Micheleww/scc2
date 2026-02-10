@echo off
REM Start MCP Server with System Tray Icon (Hidden Window)
REM 后台启动MCP服务器，在系统托盘显示图标，不显示任务栏窗口

cd /d "d:\quantsys\tools\mcp_bus"

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

REM 检查并安装pystray依赖
python -c "import pystray" >nul 2>&1
if errorlevel 1 (
    echo Installing pystray and pillow...
    pip install pystray pillow >nul 2>&1
)

REM 使用VBScript隐藏窗口启动Python脚本
echo Starting MCP Server with System Tray...
echo Server URL: http://127.0.0.1:18788/
echo Look for the tray icon in the system tray (bottom-right corner)
echo.

REM 创建临时VBScript来隐藏窗口
REM 优先使用增强版托盘程序（带状态监控）
set TRAY_SCRIPT=d:\quantsys\tools\mcp_bus\server_tray_enhanced.py
if not exist "%TRAY_SCRIPT%" (
    set TRAY_SCRIPT=d:\quantsys\tools\mcp_bus\server_tray.py
)

set VBS_FILE=%TEMP%\start_mcp_tray_%RANDOM%.vbs
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "python ""%TRAY_SCRIPT%""", 0, False
echo Set WshShell = Nothing
) > "%VBS_FILE%"

REM 执行VBScript（隐藏窗口）
cscript //nologo "%VBS_FILE%"

REM 删除临时文件
del "%VBS_FILE%" >nul 2>&1

echo MCP Server started in background with system tray icon.
echo Right-click the tray icon to access the menu.
echo To stop the server, right-click the tray icon and select 'Exit'.
echo.
timeout /t 3 >nul
