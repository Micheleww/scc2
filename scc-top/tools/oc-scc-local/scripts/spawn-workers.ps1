$ErrorActionPreference = "Stop"

$CodeX = $null
if ($env:WORKERS_CODEX -ne $null -and $env:WORKERS_CODEX -ne "") { $CodeX = [int]$env:WORKERS_CODEX }
if ($CodeX -eq $null) { $CodeX = 4 }

$OC = $null
if ($env:WORKERS_OPENCODECLI -ne $null -and $env:WORKERS_OPENCODECLI -ne "") { $OC = [int]$env:WORKERS_OPENCODECLI }
if ($OC -eq $null) { $OC = 6 }

$repo = Split-Path -Parent $PSScriptRoot

Write-Host "Spawning workers: codex=$CodeX, opencodecli=$OC"

$prefix = $env:WORKER_PREFIX
if (-not $prefix) { $prefix = (Get-Date -Format "yyyyMMdd-HHmmss") }

$modelsCodex = $env:WORKER_MODELS_CODEX
if (-not $modelsCodex) { $modelsCodex = "gpt-5.1-codex-max,gpt-5.2" }

$modelsOc = $env:WORKER_MODELS_OPENCODECLI
if (-not $modelsOc) { $modelsOc = "opencode/glm-4.7-free,opencode/kimi-k2.5-free,opencode/gpt-5-nano,opencode/minimax-m2.1-free,opencode/trinity-large-preview-free,opencode/big-pickle" }

for ($i = 1; $i -le $CodeX; $i++) {
  $name = "$prefix-codex-$i"
  $script = Join-Path $repo "scripts\\worker-codex.ps1"
  Start-Process -FilePath powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy","Bypass",
    "-Command",
    "`$env:WORKER_NAME='$name'; `$env:WORKER_MODELS='$modelsCodex'; & '$script'"
  ) | Out-Null
}

for ($i = 1; $i -le $OC; $i++) {
  $name = "$prefix-occli-$i"
  $script = Join-Path $repo "scripts\\worker-opencodecli.ps1"
  Start-Process -FilePath powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy","Bypass",
    "-Command",
    "`$env:WORKER_NAME='$name'; `$env:WORKER_MODELS='$modelsOc'; & '$script'"
  ) | Out-Null
}

Write-Host "Workers started. Check: http://127.0.0.1:18788/executor/workers"
