$jobs = @(
  @{prompt='OC: draft fusion plan focusing on integrating SCC task decomposition, model routing, CLI runner, git/doc management into OpenCode native server + UI. Output only patch diffs and file lists.'; executor='opencodecli'},
  @{prompt='CODEX: design /scc backend module patches (task store + executor adapter + routes). Output diffs only.'; executor='codex'},
  @{prompt='CODEX: MCP dedup: keep SCC /mcp, move OC MCP to /oc/mcp; include server+client patches.'; executor='codex'},
  @{prompt='CODEX: Desktop UI: add SCC panel in packages/desktop (menu + page, health/tasks). Output diffs.'; executor='codex'},
  @{prompt='CODEX: Executor: implement concurrency-limited task runner and artifacts persistence for SCC tasks in OC.'; executor='codex'},
  @{prompt='CODEX: Docs/smoke: write README section + smoke script for fusion.'; executor='codex'}
)
$result = @()
foreach ($j in $jobs) {
  $body = ($j | ConvertTo-Json -Compress)
  $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $body -ContentType 'application/json' http://127.0.0.1:18788/executor/jobs -TimeoutSec 30
  $result += ($resp.Content | ConvertFrom-Json)
}
$result | Select-Object id,executor,status,model
