@echo off
chcp 65001 >nul
title IG Tracker — Desktop Batch Spoofer & Drive Uploader
color 0b

echo ===============================================================================
echo     IG TRACKER & PUBLISHER — DESKTOP BATCH SPOOFER ^& DRIVE UPLOADER
echo ===============================================================================
echo.

:: 1. Kontrola Pythonu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [CHYBA] Python nie je nainstalovany alebo nie je v premennej PATH!
    echo Prosim nainstalujte Python 3.10+ z https://www.python.org/downloads/
    echo (Pri instalacii zaskrtnite "Add python.exe to PATH")
    echo.
    pause
    exit /b 1
)

:: 2. Instalacia kniznic ak chybaju
echo [*] Overujem potrebne kniznice (Google Drive, yt-dlp)...
python -c "import googleapiclient" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Instalujem potrebne balicky (jednorazovo)...
    pip install -r requirements.txt
)
python -c "import yt_dlp" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Instalujem yt-dlp...
    pip install yt-dlp
)

:: 3. Spustenie skriptu
echo [*] Spustam Batch Spoofer...
echo.
python spoofer_desktop.py

pause
