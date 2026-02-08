@echo off
setlocal

REM SCC Cleanroom: make the dev environment reproducible and avoid Windows autostart/ACL noise.
REM - Starts Docker Desktop engine (desktop-linux)
REM - Stages a minimal docker build context to _docker_ctx_scc (avoids repo-wide ACL issues)
REM - Builds & starts SCC via docker compose (offline wheelhouse)

pushd "%~dp0..\.."
set "ROOT=%CD%"
popd

echo [cleanroom] repo_root=%ROOT%

REM 1) Sanity: wheelhouse must exist (offline install)
echo [cleanroom] step=wheelhouse_check
if not exist "%ROOT%\_wheelhouse" (
  echo [cleanroom] ERROR: missing %ROOT%\_wheelhouse
  echo [cleanroom] Please run pip download first. Need manylinux wheels for Linux containers.
  exit /b 2
)

REM 2) Start Docker Desktop and wait for engine (single-line to avoid cmd caret pitfalls)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$exe='C:\Program Files\Docker\Docker\Docker Desktop.exe'; if(-not (Test-Path $exe)){ $exe=\"$env:LOCALAPPDATA\Programs\Docker\Docker\Docker Desktop.exe\" }; if(-not (Test-Path $exe)){ Write-Host '[cleanroom] Docker Desktop.exe not found'; exit 2 }; Start-Process -FilePath $exe -WindowStyle Hidden | Out-Null; $deadline=(Get-Date).AddSeconds(120); while((Get-Date) -lt $deadline){ try { $v = docker version 2>$null; if($LASTEXITCODE -eq 0 -and ($v -match 'Server:')){ Write-Host '[cleanroom] docker engine ready'; exit 0 } } catch {}; Start-Sleep -Seconds 3 }; Write-Host '[cleanroom] docker engine NOT ready (timeout)'; exit 3"

if errorlevel 1 (
  echo [cleanroom] ERROR: docker engine not ready
  exit /b 3
)

REM 3) Stage minimal context (avoid repo ACL hotspots like .pytest_cache)
call "%ROOT%\tools\unified_server\docker\stage_context.cmd"
if errorlevel 1 (
  echo [cleanroom] ERROR: stage_context failed
  exit /b 4
)

REM 4) Build + start
pushd "%ROOT%"
docker compose -f docker-compose.scc.yml down --remove-orphans >nul 2>nul
docker compose -f docker-compose.scc.yml build scc-server
if errorlevel 1 (
  echo [cleanroom] ERROR: docker build failed
  exit /b 5
)
docker compose -f docker-compose.scc.yml up -d
if errorlevel 1 (
  echo [cleanroom] ERROR: docker up failed
  exit /b 6
)

REM 5) Health
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(60); while((Get-Date) -lt $deadline){ try { iwr -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:18788/health/ready | Out-Null; Write-Host '[cleanroom] READY http://127.0.0.1:18788/scc'; exit 0 } catch {}; Start-Sleep -Seconds 2 }; Write-Host '[cleanroom] NOT_READY (timeout)'; exit 7"
popd

endlocal
