$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:18788"

function Submit-AtomicJob {
  param(
    [Parameter(Mandatory=$true)][string]$Goal,
    [Parameter(Mandatory=$false)][string[]]$Files = @(),
    [Parameter(Mandatory=$false)][string]$Executor = "codex",
    [Parameter(Mandatory=$false)][string]$Model = $null,
    [Parameter(Mandatory=$false)][int]$TimeoutMs = 0,
    [Parameter(Mandatory=$false)][string]$TaskType = "atomic"
  )

  $body = @{
    goal = $Goal
    files = $Files
    executor = $Executor
    taskType = $TaskType
  }
  if ($Model) { $body.model = $Model }
  if ($TimeoutMs -gt 0) { $body.timeoutMs = $TimeoutMs }

  $json = ($body | ConvertTo-Json -Depth 6 -Compress)
  $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $json -ContentType "application/json" "$base/executor/jobs/atomic" -TimeoutSec 30
  return ($resp.Content | ConvertFrom-Json)
}

$jobs = @()

# CodexCLI tasks (atomic, constrained by context packs)
$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "fusion_api" `
  -Files @(
    "packages/opencode/src/server/routes/scc.ts",
    "packages/opencode/src/server/server.ts",
    "packages/opencode/src/scc/tasks.ts",
    "packages/opencode/src/scc/config.ts",
    "packages/opencode/src/scc/codex.ts"
  ) `
  -Goal @"
Implement SCC-native task API in OpenCode server.

Requirements:
- Patch ONLY (diff blocks) + file list.
- Extend /scc routes:
  - POST /scc/tasks (creates queued task)
  - POST /scc/tasks/:id/run (trigger run)
  - GET /scc/tasks and GET /scc/tasks/:id
  - GET /scc/tasks/:id/stdout and /stderr (read stored logs)
- Task store must be persistent (JSON on disk), under: artifacts/scc_tasks/<task_id>/task.json
- Concurrency-limited runner (limit=2) that executes via gateway: POST http://127.0.0.1:18788/executor/jobs (executor=codex) and polls /executor/jobs/:id until done.
- Keep OC style: avoid try/catch where possible, no any, prefer const, early returns.
"@

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "model_router" `
  -Files @(
    "..\\scc-top\\tools\\scc\\task_queue.py",
    "packages/opencode/src/scc/config.ts",
    "packages/opencode/src/scc/tasks.ts"
  ) `
  -Goal @"
Port SCC model routing logic into OpenCode.

Source reference: scc-top/tools/scc/task_queue.py::_resolve_auto_mode and related hints.

Deliverable:
- Add packages/opencode/src/scc/model-router.ts with a pure function route(input)->{mode:'plan'|'chat', risk:'low'|'medium'|'high', notes:string[]}.
- Wire into SCC task creation so each task gets mode/risk stored.
- Add lightweight unit tests if possible.
- Output patches only.
"@

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "mcp_dedup" `
  -Files @(
    "packages/opencode/src/server/server.ts",
    "packages/opencode/src/server/routes/mcp.ts"
  ) `
  -Goal @"
MCP route dedup: SCC stays /mcp, OpenCode MCP moves to /oc/mcp.

Deliverable:
- Patch packages/opencode/src/server/server.ts to mount OC McpRoutes at /oc/mcp instead of /mcp.
- Update OC internal callers that refer to OC MCP paths (search for '/mcp' usages that are OC-specific).
- Output patches only; keep behavior for SCC /mcp (proxied by SCC server) unchanged.
"@

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "toolbox" `
  -Files @(
    "packages/opencode/src/tool/registry.ts",
    "packages/opencode/src/tool/stat.ts",
    "packages/opencode/src/tool/grep.ts",
    "packages/opencode/src/tool/glob.ts"
  ) `
  -Goal @"
OpenCode toolbox expansion (read-only first):

Deliverable (patches only):
- Implement 2 tools: git_diff (read-only) and tail_logs (read-only; only within repo artifacts/log dirs).
- Register them in packages/opencode/src/tool/registry.ts with consistent permissions.
"@

# OpenCodeCLI tasks (design docs only; no tools)
$jobs += Submit-AtomicJob `
  -Executor "opencodecli" `
  -Model "opencode/glm-4.7-free" `
  -TimeoutMs 900000 `
  -TaskType "ux_spec" `
  -Goal @"
Draft a concise UI/UX spec for an OpenCode-native SCC panel:
- Task list, task detail, run/retry, logs view, error states.
- Keep it minimal and native-feeling.
- No tools.
"@

$jobs | Select-Object id,executor,status,model,taskType,contextPackId

