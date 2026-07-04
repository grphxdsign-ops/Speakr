@echo off
rem Speakr launcher — creates the venv on first run, then starts without a console window.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First run: setting up Python environment...
    py -3.12 -m venv .venv || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
start "" ".venv\Scripts\pythonw.exe" -m speakr
echo Speakr started. Look for the mic icon in the system tray.
