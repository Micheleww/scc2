$jobs = @(
  @{prompt='Plan SCC native adapter patches (server /scc routes + task service + codex executor)'; executor='codex'},
  @{prompt='Split MCP routes: keep /mcp for SCC, move OC to /oc/mcp; list diffs'; executor='codex'},
  @{prompt='Design Solid/Tauri SCC panel (health, submit task, list tasks, start/stop)'; executor='codex'},
  @{prompt='Implement TS codex executor adapter with Bun.spawn; persist tasks; add /scc/tasks/:id/run'; executor='codex'},
  @{prompt='Write README + smoke checklist for SCC-OC fusion'; executor='codex'},
  @{prompt='Use opencode-cli to draft same fusion plan'; executor='opencodecli'}
)
$result = @()
foreach ($j in $jobs) {
  $body = ($j | ConvertTo-Json -Compress)
  $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $body -ContentType 'application/json' http://127.0.0.1:18788/executor/jobs -TimeoutSec 30
  $result += ($resp.Content | ConvertFrom-Json)
}
$result | Select-Object id,executor,status,model
