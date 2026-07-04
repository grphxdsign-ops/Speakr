@echo off
rem Speakr in console mode — shows live logs, Ctrl+C to stop.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m speakr
pause
