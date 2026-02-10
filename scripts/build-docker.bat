@echo off
chcp 65001 >nul
:: SCC Docker 统一构建脚本
:: 版本: 1.0.0
:: 使用规范: 所有 SCC 镜像构建必须通过此脚本
::
:: 用法:
::   build-docker.bat [版本号]
::
:: 示例:
::   build-docker.bat              :: 构建 scc:latest
::   build-docker.bat 1.0.0        :: 构建 scc:1.0.0
::   build-docker.bat 1.0.0 latest :: 构建并标记为 latest

setlocal EnableDelayedExpansion

:: 配置
set "DOCKERFILE_DIR=%~dp0..\docker"
set "CONTEXT_DIR=%~dp0.."
set "IMAGE_NAME=scc"

:: 解析参数
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=latest"

echo ============================================
echo SCC Docker 统一构建脚本
echo ============================================
echo.
echo 镜像名称: %IMAGE_NAME%
echo 版本标签: %VERSION%
echo Dockerfile: %DOCKERFILE_DIR%\Dockerfile
echo 构建上下文: %CONTEXT_DIR%
echo.

:: 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 未运行，请先启动 Docker Desktop
    exit /b 1
)

:: 进入构建上下文目录
cd /d "%CONTEXT_DIR%"

:: 构建镜像
echo [1/3] 正在构建镜像 %IMAGE_NAME%:%VERSION% ...
docker build -t %IMAGE_NAME%:%VERSION% -f %DOCKERFILE_DIR%\Dockerfile %CONTEXT_DIR%

if errorlevel 1 (
    echo [错误] 镜像构建失败
    exit /b 1
)

echo [✓] 镜像构建成功: %IMAGE_NAME%:%VERSION%

:: 如果需要，标记为 latest
if not "%VERSION%"=="latest" (
    if "%~2"=="latest" (
        echo [2/3] 标记为 latest ...
        docker tag %IMAGE_NAME%:%VERSION% %IMAGE_NAME%:latest
        echo [✓] 已标记为 latest
    ) else (
        echo [2/3] 跳过 latest 标记 (使用 'build-docker.bat %VERSION% latest' 可同时标记)
    )
) else (
    echo [2/3] 版本已是 latest，跳过标记
)

:: 显示构建结果
echo [3/3] 构建完成，当前镜像列表:
docker images %IMAGE_NAME% --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

echo.
echo ============================================
echo 构建完成!
echo ============================================
echo.
echo 启动服务:
echo   cd %DOCKERFILE_DIR%
echo   docker-compose up -d
echo.

endlocal
