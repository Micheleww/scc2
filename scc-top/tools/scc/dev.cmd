@echo off
setlocal

REM User-level Dev launcher:
REM 1) Open a local dev page immediately (<= 3s) so user sees something.
REM 2) Start Docker + server in background (sccctl desktop).

set ROOT=%~dp0..
for %%I in ("%ROOT%") do set ROOT=%%~fI

set DEV_HTML=%ROOT%\tools\scc\desktop\dev.html
if not exist "%DEV_HTML%" (
  echo missing: %DEV_HTML%
  exit /b 2
)

REM Allow overriding host port mapping (default 18788).
if "%SCC_HOST_PORT%"=="" set SCC_HOST_PORT=18788

start "" "%DEV_HTML%?port=%SCC_HOST_PORT%"

REM Kick server in background; sccctl will wait for Docker engine and open /desktop too.
start "" /B cmd /c "%ROOT%\tools\scc\sccctl.cmd desktop"

exit /b 0

