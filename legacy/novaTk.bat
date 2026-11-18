@echo off
REM Double-click to open the legacy Tkinter NOVA front end (no console window).
REM Adjust PYTHONW if your interpreter lives elsewhere. For a visible console
REM with tracebacks, run  python -m legacy.novaTk  from the repository root instead.
set "PYTHONW=C:\Users\seanb\miniconda3\pythonw.exe"
cd /d "%~dp0.."
start "" "%PYTHONW%" -m legacy.novaTk
