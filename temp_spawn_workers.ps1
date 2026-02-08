for ($i=1; $i -le 12; $i++) {
  Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList "-ExecutionPolicy","Bypass","-Command","$env:WORKER_NAME='occli-auto-$i'; $env:WORKER_IDLE_EXIT_SECONDS='0'; & 'C:\scc\scc-top\tools\oc-scc-local\scripts\worker-opencodecli.ps1'"
}
