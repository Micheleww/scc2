$all=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18788/executor/jobs -TimeoutSec 10).Content | ConvertFrom-Json
$all | Sort-Object createdAt | ForEach-Object {
  [PSCustomObject]@{id=$_.id; executor=$_.executor; status=$_.status; attempts=$_.attempts; model=$_.model; prompt=$_.prompt.Substring(0,[Math]::Min(60,$_.prompt.Length))}
} | Format-Table -AutoSize
