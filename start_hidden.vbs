' Run Job Watch in the background (no console window).
' Log: data\job_watch.log   /   Stop: stop.bat
' Auto-start on login: put a shortcut to this file in the shell:startup folder.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = dir
shell.Run """" & dir & "\.venv\Scripts\pythonw.exe"" """ & dir & "\run.py""", 0, False
