@echo off
title Tapo P110 Control Center - Windows 11
color 0B

echo ======================================================================
echo          TAPO P110 CONTROL CENTER - WINDOWS 11 WEBAPP
echo ======================================================================
echo.

cd /d "%~dp0"

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [INFO] Creazione ambiente virtuale .venv...
    python -m venv .venv
    echo [INFO] Installazione requisiti...
    .\.venv\Scripts\pip install -r requirements.txt
)

echo [INFO] Avvio Tapo P110 Control Center in corso...
echo [INFO] Apri il browser su http://127.0.0.1:8000 se non si apre la finestra.
echo.

.\.venv\Scripts\python.exe main.py

pause
