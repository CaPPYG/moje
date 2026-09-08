@echo off
title GarcArzP HUB - IG Analytics Tracker (Port 5080)
cd /d "%~dp0"
echo ===================================================
echo   IG Analytics Tracker - Port 5080
echo   Heslo: patrik3924
echo ===================================================

if not exist venv (
    echo Vytvaram virtualenv...
    python -m venv venv
)

call venv\Scripts\activate.bat
echo Instalujem zavislosti...
pip install -r requirements.txt

echo Spustam IG Tracker...
python app.py
pause
