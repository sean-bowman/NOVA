@echo off
REM Double-click to open the NOVA Nozzle Designer GUI (no console window).
REM Adjust PYTHONW if your interpreter lives elsewhere. For a visible console
REM with tracebacks, run  python -m novaGui  from this directory instead.
set "PYTHONW=C:\Users\seanb\miniconda3\pythonw.exe"
cd /d "%~dp0"
start "" "%PYTHONW%" -m novaGui
