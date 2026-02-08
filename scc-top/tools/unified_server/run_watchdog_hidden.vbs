' Run unified server watchdog hidden (no console window).
' This is a user-friendly launcher for SCC base.
On Error Resume Next

Dim shell, cmd
Set shell = CreateObject("WScript.Shell")

' Use cmd.exe to run the existing run_watchdog.cmd from repo
cmd = "cmd.exe /c """ & "d:\quantsys\tools\unified_server\run_watchdog.cmd" & """"

' 0 = hidden, False = do not wait
shell.Run cmd, 0, False
