@echo off
chcp 65001 >nul
echo ============================================================
echo ATA与UI-TARS集成服务
echo ============================================================
echo.
echo 功能: 当user_ai收到ATA消息时，自动发送UI-TARS提醒
echo.
echo 按 Ctrl+C 停止服务
echo.
echo ============================================================
echo.

cd /d "%~dp0"
python ata_uit_integration.py --repo-root ..\.. --check-interval 30

pause
