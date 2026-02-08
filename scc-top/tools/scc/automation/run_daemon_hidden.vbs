' Run SCC automation daemon hidden (no console window).
On Error Resume Next

Dim shell, cmd
Set shell = CreateObject("WScript.Shell")

cmd = "cmd.exe /c ""d:\quantsys\.venv\Scripts\pythonw.exe d:\quantsys\tools\scc\automation\daemon_inbox.py"""
shell.Run cmd, 0, False

