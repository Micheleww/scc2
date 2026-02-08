$all = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18788/executor/jobs -TimeoutSec 10).Content | ConvertFrom-Json
$all | Select-Object -First 2 | ConvertTo-Json -Depth 6
