@echo off
title GarcArzP HUB - System Monitor (Port 5070)
cd /d "%~dp0"
echo ===================================================
echo   GarcArzP HUB - System ^& Network Monitor
echo ===================================================

if not exist venv (
    echo Vytvaram virtualenv...
    python -m venv venv
)

call venv\Scripts\activate.bat
echo Instalujem zavislosti...
pip install -r requirements.txt

echo Spustam Monitor na porte 5070...
python app.py
pause
