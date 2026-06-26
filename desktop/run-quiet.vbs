' Steward - launch with no console window.
' Double-click this instead of run.bat. It starts the app through the venv's
' windowless Python (pythonw.exe), so no console appears. Startup and crash
' detail still go to  %USERPROFILE%\.steward\steward.log .
Option Explicit

Dim fso, shell, here, pyw, app
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
pyw  = here & "\.venv\Scripts\pythonw.exe"
app  = here & "\app.py"

If Not fso.FileExists(pyw) Then
  MsgBox "Steward isn't set up yet. Double-click setup.bat first.", vbExclamation, "Steward"
  WScript.Quit 1
End If

shell.CurrentDirectory = here
' window style 0 = hidden console; False = don't block waiting for the app to exit
shell.Run """" & pyw & """ """ & app & """", 0, False
