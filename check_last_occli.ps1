$all = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18788/executor/jobs -TimeoutSec 10).Content | ConvertFrom-Json
$oc = $all | Where-Object { $_.executor -eq 'opencodecli' } | Select-Object -Last 1
$oc | ConvertTo-Json -Depth 6
