@echo off
rem ===== CaPPy Tools WEB =====
rem Spusta web appku (Flask) na http://127.0.0.1:5000
cd /d "%~dp0"
set "PY=C:\Users\patri\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=python"
start "CaPPy Tools WEB" "%PY%" server.py
