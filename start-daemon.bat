@echo off
REM Start clawdmeter-daemon now, silently (no console window), with the tray icon.
REM Autostart at login is set up separately by install.bat (an HKCU Run entry).
REM Pick the transport by right-clicking the tray icon; your choice is remembered.
REM You can also pass flags, e.g.  start-daemon.bat --serial
REM
REM pyw.exe is the windowless Python launcher: it resolves your default Python with
REM no hardcoded version path and no console flash. Override with CLAWDMETER_PYTHONW
REM if you want a specific interpreter.

cd /d "%~dp0"
set "PYW=pythonw"
if exist "C:\Python314\pythonw.exe" set "PYW=C:\Python314\pythonw.exe"
where pyw >nul 2>&1 && set "PYW=pyw"
if defined CLAWDMETER_PYTHONW set "PYW=%CLAWDMETER_PYTHONW%"

start "" "%PYW%" "%~dp0clawdmeter_daemon.py" --tray %*
