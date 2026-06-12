@echo off
setlocal

REM Launch clawdmeter-daemon silently (no console) with the tray icon.
REM First run only:  py -m pip install -r requirements.txt
REM
REM Pass the transport you want, e.g.:
REM   start-daemon.bat --serial                 (USB Clawdmeter, auto-detect COM)
REM   start-daemon.bat --push-to 192.168.1.50   (push to a SmallTV)
REM   start-daemon.bat --serve                  (HTTP server the device polls)
REM Or set CLAWDMETER_PUSH_URL and run with no args.
REM
REM pythonw.exe = windowless Python. If "where pythonw" shows a WindowsApps stub,
REM set CLAWDMETER_PYTHONW to your real interpreter, e.g. C:\Python314\pythonw.exe

if defined CLAWDMETER_PYTHONW (
    set "PYW=%CLAWDMETER_PYTHONW%"
) else (
    set "PYW=pythonw.exe"
)

cd /d "%~dp0"
start "" "%PYW%" "clawdmeter_daemon.py" --tray %*
