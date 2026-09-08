@echo off
rem ===== PasteBin (Local Launcher) =====
cd /d "%~dp0"
set "PY=C:\Users\patri\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=python"
echo Spustam PasteBin na http://127.0.0.1:5060
"%PY%" app.py
pause
