@echo off
chcp 65001 >nul
echo ==================================
echo SCC Git Hooks Installation
echo ==================================
echo.

set SCC_ROOT=C:\scc
set HOOKS_DIR=%SCC_ROOT%\.git\hooks
set HOOK_SCRIPT=%SCC_ROOT%\docker\auto-sync-hook.ps1

REM Check Git repository
if not exist "%SCC_ROOT%\.git" (
    echo ERROR: Git repository not found at %SCC_ROOT%\.git
    exit /b 1
)

echo Found Git repository: %SCC_ROOT%

REM Create hooks directory if not exists
if not exist "%HOOKS_DIR%" (
    mkdir "%HOOKS_DIR%"
    echo Created hooks directory: %HOOKS_DIR%
)

REM Check hook script exists
if not exist "%HOOK_SCRIPT%" (
    echo ERROR: Hook script not found: %HOOK_SCRIPT%
    exit /b 1
)

echo Found hook script: %HOOK_SCRIPT%
echo.

REM Create post-commit hook
echo #!/bin/sh > "%HOOKS_DIR%\post-commit"
echo # SCC Docker Auto-Sync Hook - post-commit >> "%HOOKS_DIR%\post-commit"
echo powershell.exe -ExecutionPolicy Bypass -File "%HOOK_SCRIPT%" -HookType "post-commit" >> "%HOOKS_DIR%\post-commit"
echo exit %%? >> "%HOOKS_DIR%\post-commit"

echo Created post-commit hook: %HOOKS_DIR%\post-commit

REM Create post-push hook
echo #!/bin/sh > "%HOOKS_DIR%\post-push"
echo # SCC Docker Auto-Sync Hook - post-push >> "%HOOKS_DIR%\post-push"
echo powershell.exe -ExecutionPolicy Bypass -File "%HOOK_SCRIPT%" -HookType "post-push" >> "%HOOKS_DIR%\post-push"
echo exit %%? >> "%HOOKS_DIR%\post-push"

echo Created post-push hook: %HOOKS_DIR%\post-push
echo.
echo ==================================
echo Git Hooks installed successfully!
echo ==================================
echo.
echo Now Docker container will auto-sync
echo after each git commit or push.
echo.
echo To uninstall:
echo   del "%HOOKS_DIR%\post-commit"
echo   del "%HOOKS_DIR%\post-push"
echo.
pause
