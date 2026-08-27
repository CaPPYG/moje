@echo off
rem ===== CaPPy Tools =====
rem Spusta appku standardnym Windows Python 3.14 (ma pip a vsetky kniznice).
set "PY=C:\Users\patri\AppData\Local\Programs\Python\Python314\pythonw.exe"
if not exist "%PY%" set "PY=pythonw"
start "" "%PY%" "%~dp0cappy_tools.py"
