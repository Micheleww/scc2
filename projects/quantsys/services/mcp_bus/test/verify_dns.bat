@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  DNS Verification - mcp.timquant.tech
echo ========================================
echo.

set DOMAIN=mcp.timquant.tech
set EXPECTED_IP=13.229.100.10
set LOG_FILE=dns_verification_%date:~0,4%%date:~0,2%%year%.txt

echo [1/4] Checking DNS resolution for %DOMAIN%...
echo.

REM Check using nslookup
nslookup %DOMAIN% > %LOG_FILE% 2>&1
echo DNS resolution completed.
echo.

REM Check using dig if available
where dig >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [2/4] Using dig for detailed DNS check...
    echo.
    dig %DOMAIN% A >> %LOG_FILE% 2>&1
) else (
    echo [2/4] dig not available, using nslookup only.
    echo.
)

echo.
echo [3/4] Analyzing DNS results...
echo.

findstr /C:"%EXPECTED_IP%" %LOG_FILE% >nul
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] DNS correctly resolves to %EXPECTED_IP%
    echo.
    echo ========================================
    echo  DNS Verification Complete
    echo ========================================
    echo.
    echo Results saved to: %LOG_FILE%
    echo.
    echo Next Steps:
    echo   1. Verify DNS propagation (5-30 minutes)
    echo   2. Configure AWS Security Group (ports 80 and 443)
    echo   3. Deploy Caddy on EC2: ssh ubuntu@13.229.100.10
    echo   4. Run: bash tools/mcp_bus/deploy/caddy_setup.sh
    echo   5. Verify HTTPS: curl https://mcp.timquant.tech/health
    echo.
) else (
    echo [FAILED] DNS does not resolve to expected IP
    echo.
    echo ========================================
    echo  DNS Verification Failed
    echo ========================================
    echo.
    echo Expected IP: %EXPECTED_IP%
    echo.
    echo Troubleshooting:
    echo   1. Check DNS A record in control panel
    echo   2. Wait for DNS propagation (up to 48 hours)
    echo   3. Verify EC2 instance is running
    echo   4. Check AWS Security Group rules
    echo.
)

echo.
echo Log file: %LOG_FILE%
echo.
pause
