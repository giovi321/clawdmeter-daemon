@echo off
setlocal
cd /d "%~dp0"

REM Install clawdmeter-daemon on Windows: dependencies + login autostart (tray).
REM Autostart is a per-user HKCU\...\Run entry written by the daemon's --install
REM (no admin, no shortcut/VBS, no hardcoded Python path). Transport is taken from
REM env vars so autostart needs no edits:
REM   long-lived token:  setx CLAUDE_CODE_OAUTH_TOKEN "sk-ant-oat01-..."
REM   push to a SmallTV:  setx CLAWDMETER_PUSH_URL "smalltv.local"
REM   (no push var set -> serves HTTP on :8787)

REM Pick one interpreter for both steps so deps and autostart can't diverge onto
REM different Pythons. Prefer the py launcher; fall back to python on PATH.
set "PYCMD=py"
where py >nul 2>&1 || set "PYCMD=python"

echo Installing Python dependencies (using %PYCMD%)...
%PYCMD% -m pip install -r "%~dp0requirements.txt" --quiet

echo Registering login autostart (tray)...
%PYCMD% "%~dp0clawdmeter_daemon.py" --install
if errorlevel 1 (
    echo.
    echo   WARNING: autostart was NOT registered. Run it yourself:
    echo     %PYCMD% clawdmeter_daemon.py --install
    goto :end
)

echo.
echo Installation complete. The tray daemon starts automatically at next login.
echo   Start it now:     start-daemon.bat
echo   Run in console:   %PYCMD% clawdmeter_daemon.py --no-tray --serve
echo   Stop it:          right-click the tray icon ^> Quit
echo   Uninstall:        uninstall.bat

:end
endlocal
