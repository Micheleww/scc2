@echo off
chcp 65001 >nul
title SCC Docker Launcher

echo ╔══════════════════════════════════════════════════╗
echo ║     SCC Full Stack Docker Launcher               ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo 可用的启动模式:
echo   [1] 基础服务 (scc-olt-cli + scc-bd)
echo   [2] 完整服务 (包含 daemon)
echo   [3] 仅 OLT CLI
echo   [4] 停止所有服务
echo   [5] 查看日志
echo   [6] 重启服务
echo.
set /p choice="请选择模式 (1-6): "

if "%choice%"=="1" goto basic
if "%choice%"=="2" goto full
if "%choice%"=="3" goto olt-only
if "%choice%"=="4" goto stop
if "%choice%"=="5" goto logs
if "%choice%"=="6" goto restart
echo 无效选择
goto end

:basic
echo.
echo 启动基础服务...
docker-compose -f docker-compose.full.yml up -d
echo.
echo 服务已启动:
echo   - OLT CLI: http://localhost:3458
echo   - SCC Backend: http://localhost:18788
goto end

:full
echo.
echo 启动完整服务 (包含 daemon)...
docker-compose -f docker-compose.full.yml --profile with-daemon up -d
echo.
echo 服务已启动:
echo   - OLT CLI: http://localhost:3458
echo   - SCC Backend: http://localhost:18788
echo   - SCC Daemon: 内部服务
goto end

:olt-only
echo.
echo 仅启动 OLT CLI...
docker-compose -f docker-compose.full.yml up -d scc-olt-cli
echo.
echo OLT CLI 已启动: http://localhost:3458
goto end

:stop
echo.
echo 停止所有服务...
docker-compose -f docker-compose.full.yml down
echo 服务已停止
goto end

:logs
echo.
echo 查看日志...
docker-compose -f docker-compose.full.yml logs -f
goto end

:restart
echo.
echo 重启服务...
docker-compose -f docker-compose.full.yml restart
echo 服务已重启
goto end

:end
echo.
pause
