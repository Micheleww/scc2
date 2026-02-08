$jobs = @(
  @{prompt=@"
[Goal] Implement native SCC task API in OpenCode server (opencode-dev). Output ONLY patches (diff blocks) + file list.

[Scope]
- Repo root: C:\scc\opencode-dev
- Target server: packages/opencode
- Existing scaffold exists: packages/opencode/src/scc/{config.ts,codex.ts,tasks.ts} and packages/opencode/src/server/routes/scc.ts is wired.

[Deliverables]
1) Implement minimal persistent TaskStore writing JSON files to: artifacts/scc_tasks/<task_id>/task.json (under repo root or Instance directory).
2) Add concurrency-limited runner (limit=2) that executes via existing gateway executor HTTP endpoint: http://127.0.0.1:18788/executor/codex (POST {prompt,model}) OR Bun.spawn codex exec.
3) Extend /scc routes:
   - POST /scc/tasks -> creates task (queued)
   - POST /scc/tasks/:id/run -> trigger run
   - GET /scc/tasks, GET /scc/tasks/:id
   - GET /scc/tasks/:id/stdout and /stderr to read stored logs
4) Keep OC style: avoid try/catch where possible, no any, prefer const, early returns.

[Constraints]
- Do not run commands.
- Do not apply edits; output patches only.
- Keep patches minimal and compilable.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] Port SCC model routing logic into OpenCode.

[Input]
- SCC reference: C:\scc\scc-top\tools\scc\task_queue.py function _resolve_auto_mode and related risk hints.

[Deliverables]
- Add packages/opencode/src/scc/model-router.ts implementing a pure function route(input)->{mode:'plan'|'chat', risk:'low'|'medium'|'high', notes:string[]}.
- Wire it into SCC task creation so each task gets mode/risk stored.
- Output patches only, include tests if lightweight.

[Constraints]
- No commands, no edits applied.
- Avoid try/catch, no any.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] Implement OC-side executor adapter to call codexcli and/or gateway, with progress reporting.

[Deliverables]
- In packages/opencode/src/scc/codex.ts implement runCodexTask({prompt,model,cwd?}) with:
  - Option A: fetch POST http://127.0.0.1:18788/executor/jobs (executor=codex) and poll /executor/jobs/:id
  - Option B: Bun.spawn codex exec
- Add minimal progress fields (lastUpdate, status) to returned structure.
- Output patches only.

[Constraints]
- No commands.
- Keep to OC style.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] MCP route dedup in OpenCode: SCC keeps /mcp, OC moves to /oc/mcp.

[Deliverables]
- Patch packages/opencode/src/server/server.ts to mount McpRoutes at /oc/mcp.
- Update any internal callers (search for '/mcp') that refer to OC MCP and adjust.
- Ensure no break for SCC /mcp which is proxied by SCC server.
- Output patches only.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] Desktop UI: add SCC panel to OpenCode Desktop (Tauri/Solid) for native feel.

[Scope]
- Repo: C:\scc\opencode-dev\packages\desktop

[Deliverables]
- Add menu entry Tools -> SCC.
- Add a view/component that:
  - GET /scc/health
  - POST /scc/tasks
  - GET /scc/tasks
  - show status list and open task details.
- Use plugin-http fetch (already used) and existing i18n/t.
- Output patches only.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] Git/Doc management integration plan + minimal API skeleton.

[Deliverables]
- Propose TS module packages/opencode/src/scc/repo.ts exposing:
  - status(), diff(), commit(message), listChangedFiles()
- Add /scc/repo endpoints (read-only first) that call these.
- Mention how to integrate SCC viewer/dashboard into OC UI later.
- Output patches only.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] Tooling improvements in OpenCode tool registry.

[Deliverables]
- Based on packages/opencode/src/tool/*, propose and implement 2-3 missing tools:
  - git_diff (read-only)
  - run_tests (restricted allowlist)
  - tail_logs (read-only)
- Ensure permissions gating consistent.
- Output patches only.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
[Goal] Docs + smoke test plan for SCC-OC fusion.

[Deliverables]
- Add doc file under packages/opencode or repo root describing:
  - ports (18788 gateway/OC), SCC 18789
  - /scc endpoints
  - /mcp vs /oc/mcp
  - how to run smoke checks
- Provide a small PowerShell smoke script content.
- Output patches only.
"@; executor='codex'; model='gpt-5.1-codex-max'},

  @{prompt=@"
Write an architecture note for SCC->OpenCode native fusion.

Constraints:
- Do NOT use tools.
- Do NOT scan the repo.
- Output a concise module map + API list + rollout phases.
"@; executor='opencodecli'; model='opencode/glm-4.7-free'},

  @{prompt=@"
Draft UI/UX spec for an OpenCode-native SCC panel.

Constraints:
- Do NOT use tools.
- Provide labels, states, errors, and minimal flows.
"@; executor='opencodecli'; model='opencode/glm-4.7-free'}
)

$result=@()
foreach($j in $jobs){
  $body = ($j | ConvertTo-Json -Compress)
  $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $body -ContentType 'application/json' http://127.0.0.1:18788/executor/jobs -TimeoutSec 30
  $result += ($resp.Content | ConvertFrom-Json)
}
$result | Select-Object id,executor,status,model
