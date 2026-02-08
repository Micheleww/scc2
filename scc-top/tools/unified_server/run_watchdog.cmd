@echo off
setlocal

REM Run the unified-server watchdog using the repo-local Python environment (best-effort).
REM This is for stability (auto-restart), not for making it "unkillable".

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%\..\..") do set REPO_ROOT=%%~fI

set UNIFIED_SERVER_HOST=127.0.0.1
set UNIFIED_SERVER_PORT=18788
REM Default: only guarantee unified server (18788). All external access goes via 18788.
set WATCHDOG_ENSURE_DASHBOARD=false
REM Auto-run SCC automation daemon after server is ready.
set WATCHDOG_AUTO_RUN_AUTOMATION=true
set SCC_PARENT_INBOX=artifacts/scc_state/parent_inbox.jsonl
set SCC_AUTOMATION_MAX_OUTSTANDING=3
REM Resource governor thresholds (tune for this machine).
set SCC_GOV_MEM_HIGH=0.83
set SCC_GOV_MEM_LOW=0.75
set SCC_GOV_CPU_HIGH=0.75
set SCC_GOV_CPU_LOW=0.55

cd /d "%REPO_ROOT%"

set PYTHON_EXE=
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe
if not defined PYTHON_EXE set PYTHON_EXE=python

"%PYTHON_EXE%" tools\unified_server\watchdog.py
