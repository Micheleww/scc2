@echo off
chcp 65001 >nul
:: SCC 统一启动脚本
:: 版本: 1.0.0
::
:: 用法: start-scc.bat [选项]
::   选项:
::     --build    强制重新构建镜像
::     --restart  重启服务
::     --logs     启动后查看日志

setlocal EnableDelayedExpansion

echo ============================================
echo SCC 统一启动脚本
echo ============================================
echo.

:: 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 未运行！
    echo.
    echo 请按以下步骤操作：
    echo 1. 启动 Docker Desktop
    echo 2. 等待 Docker 完全启动（图标不再闪烁）
    echo 3. 重新运行此脚本
    echo.
    pause
    exit /b 1
)

echo [✓] Docker 运行正常

:: 解析参数
set "FORCE_BUILD=false"
set "RESTART=false"
set "SHOW_LOGS=false"

:parse_args
if "%~1"=="" goto :done_parse
if "%~1"=="--build" set "FORCE_BUILD=true"
if "%~1"=="-b" set "FORCE_BUILD=true"
if "%~1"=="--restart" set "RESTART=true"
if "%~1"=="-r" set "RESTART=true"
if "%~1"=="--logs" set "SHOW_LOGS=true"
if "%~1"=="-l" set "SHOW_LOGS=true"
shift
goto :parse_args
:done_parse

:: 切换到 docker 目录
cd /d "%~dp0..\docker"

:: 如果需要重启，先停止
if "%RESTART%"=="true" (
    echo.
    echo [*] 正在停止现有服务...
    docker-compose down
    echo [✓] 服务已停止
)

:: 检查镜像是否存在
set "IMAGE_EXISTS=false"
docker images scc:latest --format "{{.Repository}}" | findstr "scc" >nul && set "IMAGE_EXISTS=true"

:: 决定是否需要构建
if "%FORCE_BUILD%"=="true" (
    echo.
    echo [*] 强制重新构建镜像...
    docker-compose build --no-cache
    if errorlevel 1 (
        echo [错误] 镜像构建失败！
        pause
        exit /b 1
    )
    echo [✓] 镜像构建成功
) else if "%IMAGE_EXISTS%"=="false" (
    echo.
    echo [*] 镜像不存在，开始构建...
    docker-compose build
    if errorlevel 1 (
        echo [错误] 镜像构建失败！
        echo.
        echo 可能的原因：
        echo 1. Docker 刚刚重启，镜像源配置未生效
        echo 2. 网络连接问题
        echo 3. Dockerfile 配置错误
        echo.
        echo 建议：
        echo - 等待几分钟后重试
        echo - 检查网络连接
        echo - 查看详细错误：docker-compose build
        pause
        exit /b 1
    )
    echo [✓] 镜像构建成功
) else (
    echo [✓] 镜像已存在，跳过构建
)

:: 启动服务
echo.
echo [*] 正在启动 SCC 服务...
docker-compose up -d

if errorlevel 1 (
