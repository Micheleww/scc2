$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:18788"

function Submit-AtomicJob {
  param(
    [Parameter(Mandatory=$true)][string]$Goal,
    [Parameter(Mandatory=$false)][string[]]$Files = @(),
    [Parameter(Mandatory=$false)][string]$Executor = "codex",
    [Parameter(Mandatory=$false)][string]$Model = $null,
    [Parameter(Mandatory=$false)][int]$TimeoutMs = 0,
    [Parameter(Mandatory=$false)][string]$TaskType = "atomic",
    [Parameter(Mandatory=$false)][string]$Runner = "external"
  )

  $body = @{
    goal = $Goal
    files = $Files
    executor = $Executor
    taskType = $TaskType
    runner = $Runner
  }
  if ($Model) { $body.model = $Model }
  if ($TimeoutMs -gt 0) { $body.timeoutMs = $TimeoutMs }

  $json = ($body | ConvertTo-Json -Depth 6 -Compress)
  $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $json -ContentType "application/json" "$base/executor/jobs/atomic" -TimeoutSec 30
  return ($resp.Content | ConvertFrom-Json)
}

$jobs = @()

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "scc_task_api_patch" `
  -Files @(
    "packages/opencode/src/server/routes/scc.ts",
    "packages/opencode/src/scc/tasks.ts",
    "packages/opencode/src/scc/config.ts",
    "packages/opencode/src/scc/codex.ts"
  ) `
  -Goal @"
Implement SCC-native task API in OpenCode server (patches only).

MUST OUTPUT:
- One or more `*** Begin Patch ... *** End Patch` blocks.

Requirements:
- Persistent TaskStore on disk: artifacts/scc_tasks/<task_id>/task.json (+ stdout/stderr logs).
- /scc routes:
  - POST /scc/tasks (create queued task)
  - POST /scc/tasks/:id/run (trigger run)
  - GET /scc/tasks, GET /scc/tasks/:id
  - GET /scc/tasks/:id/stdout and /stderr
- Runner: limit=2, and it must execute via gateway executor:
  - POST http://127.0.0.1:18788/executor/jobs (executor=codex, runner=internal ok)
  - poll /executor/jobs/:id until done

Rules:
- Do NOT scan repo; use provided context pack only.
- Do NOT output summary without patch.
"@

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "desktop_nav_patch" `
  -Files @(
    "packages/desktop/src/menu.ts",
    "packages/desktop/src/index.tsx",
    "packages/opencode/src/server/routes/scc.ts"
  ) `
  -Goal @"
Desktop navigation tidy + add SCC entry (patches only).

MUST OUTPUT:
- `*** Begin Patch ... *** End Patch` blocks only.

Requirements:
- Add a new menu item under Tools: 'SCC' (or localized).
- It should open a view (route/page) that loads SCC health and shows tasks list from OpenCode server /scc endpoints.

Rules:
- Use existing patterns in menu.ts/index.tsx.
- Do NOT scan repo; only use provided files.
"@

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "docs_nav_patch" `
  -Files @(
    "..\\docs\\README.md",
    "..\\docs\\NAVIGATION.md",
    "..\\docs\\EXECUTOR.md"
  ) `
  -Goal @"
Improve documentation navigation (patches only).

MUST OUTPUT:
- `*** Begin Patch ... *** End Patch` blocks only.

Requirements:
- Make docs/README.md a clear table of contents with links.
- Keep it short and readable.

Rules:
- Do NOT add large sections; only improve navigation.
"@

$jobs | Select-Object id,executor,status,model,taskType,runner,contextPackId

