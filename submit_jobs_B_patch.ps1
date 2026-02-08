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

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "mcp_dedup_patch" `
  -Files @(
    "packages/opencode/src/server/server.ts",
    "packages/opencode/src/server/routes/mcp.ts"
  ) `
  -Goal @"
MCP route dedup: SCC stays /mcp, OpenCode MCP moves to /oc/mcp.

MUST OUTPUT:
- A single `*** Begin Patch ... *** End Patch` patch block that changes OpenCode server mount from `/mcp` -> `/oc/mcp`.
- If you touch any other file, include it in the patch.

Rules:
- Do not output a summary without a patch.
- Do not scan repo; only use the provided files.
"@

$jobs += Submit-AtomicJob `
  -Executor "codex" `
  -Model "gpt-5.1-codex-max" `
  -TimeoutMs 600000 `
  -TaskType "toolbox_patch" `
  -Files @(
    "packages/opencode/src/tool/registry.ts",
    "packages/opencode/src/tool/stat.ts",
    "packages/opencode/src/tool/stat.txt"
  ) `
  -Goal @"
OpenCode toolbox expansion (read-only first).

MUST OUTPUT:
- A single `*** Begin Patch ... *** End Patch` patch block that:
  1) Adds `packages/opencode/src/tool/git_diff.ts` and `git_diff.txt`
  2) Adds `packages/opencode/src/tool/tail_logs.ts` and `tail_logs.txt`
  3) Registers the tools in `packages/opencode/src/tool/registry.ts`

Rules:
- Do not output a summary without a patch.
- Match existing tool patterns (permission gating, path allowlists).
- Do not scan repo; only use provided files as reference.
"@

$jobs += Submit-AtomicJob `
  -Executor "opencodecli" `
  -Model "opencode/glm-4.7-free" `
  -TimeoutMs 900000 `
  -TaskType "ux_spec_v2" `
  -Files @(
    "packages/opencode/src/server/routes/scc.ts",
    "packages/opencode/src/scc/tasks.ts",
    "packages/desktop/package.json"
  ) `
  -Goal @"
Draft a concise UI/UX spec for an OpenCode-native SCC panel:
- Task list, task detail, run/retry, logs view, error states.
- Keep it minimal and native-feeling.
- Output only the spec (markdown), no code.
"@

$jobs | Select-Object id,executor,status,model,taskType,contextPackId

