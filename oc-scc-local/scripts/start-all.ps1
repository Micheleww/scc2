$ErrorActionPreference = "Stop"

Write-Host "== Start OpenCode =="
& "$PSScriptRoot\\start-opencode.ps1"

Write-Host "== Start SCC (Docker) =="
try {
  & "$PSScriptRoot\\start-scc.ps1"
} catch {
  Write-Warning "SCC failed to start (Docker may be unavailable): $($_.Exception.Message)"
}

Write-Host "== Start Gateway (18788) =="
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
  if (-not $env:EXEC_CONCURRENCY_CODEX) { $env:EXEC_CONCURRENCY_CODEX = "4" }
  if (-not $env:EXEC_CONCURRENCY_OPENCODE) { $env:EXEC_CONCURRENCY_OPENCODE = "6" }
  if (-not $env:EXEC_TIMEOUT_CODEX_MS) { $env:EXEC_TIMEOUT_CODEX_MS = "1200000" }
  if (-not $env:EXEC_TIMEOUT_OPENCODE_MS) { $env:EXEC_TIMEOUT_OPENCODE_MS = "1200000" }
  if (-not $env:MODEL_POOL_FREE) { $env:MODEL_POOL_FREE = "opencode/glm-4.7-free,opencode/kimi-k2.5-free,opencode/gpt-5-nano,opencode/minimax-m2.1-free,opencode/trinity-large-preview-free,opencode/big-pickle" }
  if (-not $env:MODEL_POOL_VISION) { $env:MODEL_POOL_VISION = "opencode/kimi-k2.5-free,opencode/gpt-5-nano" }
  npm install | Out-Null
  # Use cmd.exe to start in background (more resilient in restricted environments)
  cmd /c "cd /d ""$repo"" && start """" /b node src\\gateway.mjs" | Out-Null
  Write-Host "Gateway started. Open: http://127.0.0.1:18788/"
} finally {
  Pop-Location
}
