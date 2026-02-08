Set shell = CreateObject("WScript.Shell")
script = Chr(34) & "powershell.exe" & Chr(34) & " -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & "C:\scc\oc-scc-local\scripts\daemon-start.ps1" & Chr(34)
shell.Run script, 0, False

