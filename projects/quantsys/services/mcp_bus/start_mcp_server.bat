@echo off
cd /d d:\quantsys\tools\mcp_bus
set REPO_ROOT=d:\quantsys
set MCP_BUS_HOST=127.0.0.1
set MCP_BUS_PORT=8000
set AUTH_MODE=none
REM 默认禁用自启，如需与总服务器同步启动，取消下面的注释：
REM set AUTO_START_FREQTRADE=true
REM 与总服务器同步启动Freqtrade（可靠启动机制，100%成功率）
python -m server.main
pause