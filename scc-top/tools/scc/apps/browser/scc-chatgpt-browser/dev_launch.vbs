Option Explicit

Dim shell, fso, appDir, electronExe, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
electronExe = appDir & "\node_modules\electron\dist\electron.exe"

If Not fso.FileExists(electronExe) Then
  shell.Popup "Missing Electron. Run `npm install` in: " & appDir, 5, "SCC ChatGPT Browser", 48
  WScript.Quit 2
End If

' Run hidden (no console window). Also clear ELECTRON_RUN_AS_NODE to ensure Electron APIs are available.
cmd = "cmd /c set ELECTRON_RUN_AS_NODE= & """ & electronExe & """ """ & appDir & """"
shell.Run cmd, 0, False

