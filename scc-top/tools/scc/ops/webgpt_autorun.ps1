$ErrorActionPreference = "Stop"

function PostJson($url, $obj) {
  $body = ($obj | ConvertTo-Json -Depth 12)
  return Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body $body
}

function GetJson($url) {
  return Invoke-RestMethod -Method Get -Uri $url
}

$base = "http://127.0.0.1:18788"

Write-Host "[webgpt_autorun] waiting for server..."
for ($i=0; $i -lt 60; $i++) {
  try {
    $r = GetJson "$base/health/ready"
    if ($r.status -eq "ready") { break }
  } catch {}
  Start-Sleep -Milliseconds 500
}

$st = GetJson "$base/scc/browser/status"
if (-not $st.running) {
  Write-Host "[webgpt_autorun] starting SCC browser (keeps login in persist:scc-chatgpt)..."
  PostJson "$base/scc/browser/start" @{ url = "https://chatgpt.com/" } | Out-Null
  Start-Sleep -Seconds 2
} else {
  Write-Host "[webgpt_autorun] browser already running; will NOT restart (to keep login stable)."
}

# Always open chatgpt.com in the existing browser (no new domains).
PostJson "$base/scc/browser/command" @{ cmd = "open_url"; args = @{ url = "https://chatgpt.com/" } } | Out-Null
Start-Sleep -Seconds 2

Write-Host "[webgpt_autorun] enqueue backfill (sidebar scroll + per-conv scroll)..."
PostJson "$base/scc/browser/command" @{
  cmd  = "webgpt_backfill_start"
  args = @{
    limit = 1200
    scroll_steps = 120
    sidebar_scroll_steps = 360
    scroll_delay_ms = 240
    per_conv_wait_ms = 18000
  }
} | Out-Null

Write-Host "[webgpt_autorun] waiting for backfill to run..."
Start-Sleep -Seconds 10

Write-Host "[webgpt_autorun] exporting all archived conversations..."
PostJson "$base/scc/webgpt/export_all" @{ limit = 2000 } | Out-Null

$ws = GetJson "$base/scc/webgpt/status"
Write-Host "[webgpt_autorun] done. conversations=$($ws.counts.conversations) messages=$($ws.counts.messages)"
Write-Host "[webgpt_autorun] docs: d:\\quantsys\\docs\\INPUTS\\WEBGPT"

