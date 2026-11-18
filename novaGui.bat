@echo off
REM Double-click to open the NOVA nozzle designer in a desktop window (no console window).
REM Adjust PYTHONW if your interpreter lives elsewhere. Startup output and tracebacks go to
REM %TEMP%\NOVA\novaGui.log; run  python -m novaGui  from this directory to see them live.
REM Build the front end once first: npm install, then npm run build, in novaGui\frontend.
set "PYTHONW=C:\Users\seanb\miniconda3\pythonw.exe"
cd /d "%~dp0"
start "" "%PYTHONW%" -m novaGui
