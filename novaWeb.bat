@echo off
REM Double-click to open the NOVA web front end in a desktop window (no console window).
REM Adjust PYTHONW if your interpreter lives elsewhere. Startup output and tracebacks go to
REM %TEMP%\NOVA\novaWeb.log; run  python -m novaWeb  from this directory to see them live.
REM Build the front end once first: npm install, then npm run build, in novaWeb\frontend.
set "PYTHONW=C:\Users\seanb\miniconda3\pythonw.exe"
cd /d "%~dp0"
start "" "%PYTHONW%" -m novaWeb
