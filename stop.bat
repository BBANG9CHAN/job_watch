@echo off
REM Stop Job Watch started by start_hidden.vbs (or start.bat)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Where-Object { $_.CommandLine -like '*run.py*' -and $_.ExecutablePath -like '*job_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('stopped PID ' + $_.ProcessId) }"
pause
