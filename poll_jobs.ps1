$i=0
while($i -lt 9){
  $all = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18788/executor/jobs -TimeoutSec 10).Content | ConvertFrom-Json
  $done = $all | Where-Object { $_.status -ne 'running' }
  $run = $all | Where-Object { $_.status -eq 'running' }
  Write-Host ("running=" + $run.Count + " done=" + $done.Count)
  $done | Select-Object -First 8 id,executor,status,exit_code | Format-Table
  Start-Sleep -Seconds 10
  $i++
}
