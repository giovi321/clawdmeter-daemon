@echo off
REM Launch clawdmeter-daemon silently (no console window) with the system-tray icon.
REM Pick the transport (Serial / HTTP push / HTTP serve) by right-clicking the tray icon;
REM your choice is remembered. You can also pass flags, e.g.  start-daemon.bat --serial
REM
REM First run only:  py -m pip install -r requirements.txt
REM
REM pythonw.exe = windowless Python. We prefer the explicit Python 3.14 path because the
REM "...\WindowsApps\pythonw.exe" on PATH is the Microsoft Store alias stub, not a real
REM interpreter. Override with CLAWDMETER_PYTHONW if your install lives elsewhere.

set "PYW=C:\Python314\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
if defined CLAWDMETER_PYTHONW set "PYW=%CLAWDMETER_PYTHONW%"

cd /d "%~dp0"
start "" "%PYW%" "%~dp0clawdmeter_daemon.py" --tray %*
