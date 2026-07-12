@echo off
REM Start clawdmeter-daemon now, silently (no console window), with the tray icon.
REM Autostart at login is set up separately by install.bat.
REM
REM Prefer the .venv that install.bat created: it is the one interpreter guaranteed
REM to have the tray dependencies. Relying on a bare "pyw"/"python" here is exactly
REM what silently drops the tray to headless when the launcher resolves a different
REM Python (e.g. the Microsoft Store build) than the deps were installed into.
REM Override the interpreter with CLAWDMETER_PYTHONW if you manage deps yourself.

cd /d "%~dp0"

if defined CLAWDMETER_PYTHONW (
    start "" "%CLAWDMETER_PYTHONW%" "%~dp0clawdmeter_daemon.py" --tray %*
    goto :eof
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0clawdmeter_daemon.py" --tray %*
    goto :eof
)

echo No .venv found - run install.bat first (or set CLAWDMETER_PYTHONW to a Python
echo that has pystray + Pillow). Trying the py launcher as a last resort...
set "PYW=pythonw"
where pyw >nul 2>&1 && set "PYW=pyw"
start "" "%PYW%" "%~dp0clawdmeter_daemon.py" --tray %*
