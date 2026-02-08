$job = @{prompt='OC: in C:\scc\opencode-dev, draft fusion plan + diff snippets to integrate SCC into OpenCode server+desktop. Only output patches and file list.'; executor='opencodecli'} | ConvertTo-Json -Compress
Invoke-WebRequest -UseBasicParsing -Method POST -Body $job -ContentType 'application/json' http://127.0.0.1:18788/executor/jobs -TimeoutSec 30 | Select-Object StatusCode,Content
