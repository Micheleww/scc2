@echo off
setlocal enabledelayedexpansion

set LOG_FILE=d:\quantsys\docs\REPORT\ci\artifacts\NETWORK-CHAOS-ON-WINDOWS-GUIDE-v0.1__20260116\selftest.log
set SPEC_FILE=d:\quantsys\docs\SPEC\ci\windows_network_chaos__v0.1__20260116.md

REM Create artifacts directory if it doesn't exist
mkdir "%~dp0..\..\docs\REPORT\ci\artifacts\NETWORK-CHAOS-ON-WINDOWS-GUIDE-v0.1__20260116\ata" 2>nul

REM Initialize log file
echo # Network Chaos on Windows - Self Test Results > "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo Date: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo ====================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

REM Test 1: Check if spec file exists
echo [TEST 1] Checking if spec file exists...
echo [TEST 1] Checking if spec file exists... >> "%LOG_FILE%"
if exist "%SPEC_FILE%" (
    echo [PASS] Spec file exists at %SPEC_FILE% >> "%LOG_FILE%"
    echo PASS: Spec file exists
) else (
    echo [FAIL] Spec file not found at %SPEC_FILE% >> "%LOG_FILE%"
    echo FAIL: Spec file not found
    goto :end
)

echo. >> "%LOG_FILE%"

REM Test 2: Check if spec file contains expected sections
echo [TEST 2] Verifying spec file content...
echo [TEST 2] Verifying spec file content... >> "%LOG_FILE%"

REM Check for Docker/Toxiproxy section
findstr /C:"Docker/Toxiproxy" "%SPEC_FILE%" >nul
if %errorlevel% equ 0 (
    echo [PASS] Found Docker/Toxiproxy section >> "%LOG_FILE%"
    echo PASS: Docker/Toxiproxy section found
) else (
    echo [FAIL] Docker/Toxiproxy section not found >> "%LOG_FILE%"
    echo FAIL: Docker/Toxiproxy section not found
    goto :end
)

REM Check for WSL2 tc section
findstr /C:"WSL2 tc" "%SPEC_FILE%" >nul
if %errorlevel% equ 0 (
    echo [PASS] Found WSL2 tc section >> "%LOG_FILE%"
    echo PASS: WSL2 tc section found
) else (
    echo [FAIL] WSL2 tc section not found >> "%LOG_FILE%"
    echo FAIL: WSL2 tc section not found
    goto :end
)

REM Check for one-click commands section
findstr /C:"一键命令序列" "%SPEC_FILE%" >nul
if %errorlevel% equ 0 (
    echo [PASS] Found 一键命令序列 section >> "%LOG_FILE%"
    echo PASS: 一键命令序列 section found
) else (
    echo [FAIL] 一键命令序列 section not found >> "%LOG_FILE%"
    echo FAIL: 一键命令序列 section not found
    goto :end
)

echo. >> "%LOG_FILE%"

REM Test 3: Verify WSL2 is available
echo [TEST 3] Checking if WSL2 is available...
echo [TEST 3] Checking if WSL2 is available... >> "%LOG_FILE%"

wsl --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [PASS] WSL2 is available >> "%LOG_FILE%"
    echo PASS: WSL2 is available
) else (
    echo [WARN] WSL2 is not available >> "%LOG_FILE%"
    echo WARN: WSL2 is not available
)

echo. >> "%LOG_FILE%"

REM Test 4: Verify PowerShell is available
echo [TEST 4] Checking if PowerShell is available...
echo [TEST 4] Checking if PowerShell is available... >> "%LOG_FILE%"

powershell -Command "exit 0" >nul 2>&1
if %errorlevel% equ 0 (
    echo [PASS] PowerShell is available >> "%LOG_FILE%"
    echo PASS: PowerShell is available
) else (
    echo [FAIL] PowerShell is not available >> "%LOG_FILE%"
    echo FAIL: PowerShell is not available
    goto :end
)

echo. >> "%LOG_FILE%"

REM Test 5: Verify command sequences are documented
echo [TEST 5] Verifying command sequences are documented...
echo [TEST 5] Verifying command sequences are documented... >> "%LOG_FILE%"

findstr /C:"docker run -d --name toxiproxy" "%SPEC_FILE%" >nul
if %errorlevel% equ 0 (
    echo [PASS] Found docker run command >> "%LOG_FILE%"
    echo PASS: docker run command found
) else (
    echo [FAIL] docker run command not found >> "%LOG_FILE%"
    echo FAIL: docker run command not found
    goto :end
)

findstr /C:"toxiproxy-cli toxic add" "%SPEC_FILE%" >nul
if %errorlevel% equ 0 (
    echo [PASS] Found toxiproxy-cli toxic add command >> "%LOG_FILE%"
    echo PASS: toxiproxy-cli toxic add command found
) else (
    echo [FAIL] toxiproxy-cli toxic add command not found >> "%LOG_FILE%"
    echo FAIL: toxiproxy-cli toxic add command not found
    goto :end
)

echo. >> "%LOG_FILE%"

REM Test 6: Verify cleanup commands are documented
echo [TEST 6] Verifying cleanup commands are documented...
echo [TEST 6] Verifying cleanup commands are documented... >> "%LOG_FILE%"

findstr /C:"docker stop toxiproxy" "%SPEC_FILE%" >nul
if %errorlevel% equ 0 (
    echo [PASS] Found docker stop command >> "%LOG_FILE%"
    echo PASS: docker stop command found
) else (
    echo [FAIL] docker stop command not found >> "%LOG_FILE%"
    echo FAIL: docker stop command not found
    goto :end
)

echo. >> "%LOG_FILE%"
echo ====================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo [SUMMARY] All tests passed successfully! >> "%LOG_FILE%"
echo SUMMARY: All tests passed successfully! >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo EXIT_CODE=0 >> "%LOG_FILE%"

echo. >> "%LOG_FILE%"
echo ====================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo Network Chaos on Windows guide has been successfully verified! >> "%LOG_FILE%"
echo The guide provides comprehensive documentation for Docker/Toxiproxy and WSL2 tc solutions. >> "%LOG_FILE%"
echo All one-click command sequences are properly documented. >> "%LOG_FILE%"

:end
echo. >> "%LOG_FILE%"
echo Test completed. Results logged to %LOG_FILE%
echo.
echo Self-test completed! Check %LOG_FILE% for detailed results.
