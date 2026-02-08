@echo off
setlocal
REM Thin wrapper for PowerShell sccctl.

set SCRIPT_DIR=%~dp0
set PS1=%SCRIPT_DIR%sccctl.ps1

if not exist "%PS1%" (
  echo missing: %PS1%
  exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*

