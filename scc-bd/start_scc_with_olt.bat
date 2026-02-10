@echo off
chcp 65001 >nul
title SCC Server with OLT CLI

echo ╔══════════════════════════════════════════════════╗
echo ║     SCC Server with OLT CLI Launcher             ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo 正在启动 SCC 服务器 (包含 OLT CLI 功能)...
echo.
echo 服务将运行在: http://localhost:3458
echo.
echo 可用端点:
echo   GET  /api/health
echo   GET  /api/olt-cli/health
echo   GET  /api/olt-cli/models
echo   POST /api/olt-cli/chat/completions
echo   POST /api/olt-cli/execute
echo   POST /api/olt-cli/tools/:tool
echo.
echo 按 Ctrl+C 停止服务器
echo.

cd /d "%~dp0"
node L6_execution_layer/scc_server_with_olt.mjs

pause
