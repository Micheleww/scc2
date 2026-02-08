$all=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18788/executor/jobs -TimeoutSec 10).Content | ConvertFrom-Json
$run=$all | Where-Object { $_.status -eq 'running' }
$queued=$all | Where-Object { $_.status -eq 'queued' }
$done=$all | Where-Object { $_.status -eq 'done' -or $_.status -eq 'failed' }
[PSCustomObject]@{running=$run.Count; queued=$queued.Count; done=$done.Count} | ConvertTo-Json -Compress
