@echo off
setlocal

REM Install clawdmeter-daemon as a Windows startup program (silent, tray icon).
REM Installs dependencies, writes a VBS wrapper for windowless launch, and drops a
REM shortcut in the Startup folder so it runs at every login.
REM
REM Transport is taken from environment variables so the autostart needs no edits:
REM   set a long-lived token:   setx CLAUDE_CODE_OAUTH_TOKEN "sk-ant-oat01-..."
REM   push to a SmallTV:        setx CLAWDMETER_PUSH_URL "smalltv.local"
REM   (no push var set -> serves HTTP on :8787; add --serial in the VBS for USB)

set DAEMON_DIR=%~dp0
set VBS_FILE=%DAEMON_DIR%run_daemon.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_DIR%\ClawdmeterDaemon.lnk

echo Installing Python dependencies...
py -m pip install -r "%DAEMON_DIR%requirements.txt" --quiet || pip install -r "%DAEMON_DIR%requirements.txt" --quiet

echo Creating silent launcher...
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "pythonw """ ^& Replace^(WScript.ScriptFullName, "run_daemon.vbs", "clawdmeter_daemon.py"^) ^& """ --tray", 0, False
) > "%VBS_FILE%"

echo Creating startup shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%VBS_FILE%'; $sc.WorkingDirectory = '%DAEMON_DIR%'; $sc.Description = 'clawdmeter-daemon (tray)'; $sc.Save()"

echo.
echo Installation complete. The daemon starts automatically at next login (tray icon).
echo   Start it now:     start-daemon.bat
echo   Run in console:   py clawdmeter_daemon.py --no-tray --serve
echo   Stop it:          right-click the tray icon ^> Quit
echo   Uninstall:        delete "%SHORTCUT%"
