$done=$false
for($i=0;$i -lt 12 -and -not $done;$i++){
  $all=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18788/executor/jobs -TimeoutSec 10).Content | ConvertFrom-Json
  $j=$all | Where-Object { $_.id -eq '54fb3bce-7eef-4523-ad68-2b31eef4964f' }
  Write-Host ("status=" + $j.status + " lastUpdate=" + $j.lastUpdate)
  if($j.status -ne 'running'){ $done=$true; $j | Select-Object id,status,exit_code | Format-Table; $j.stdout.Substring(0,[Math]::Min(800,$j.stdout.Length)) }
  Start-Sleep -Seconds 10
}
