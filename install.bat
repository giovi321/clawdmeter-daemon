@echo off
setlocal
cd /d "%~dp0"

REM Install clawdmeter-daemon on Windows: dependencies + login autostart (tray).
REM
REM Uses a self-contained .venv so the daemon always runs with its dependencies, no
REM matter which Python the launcher resolves at start time. The Microsoft Store
REM Python in particular installs packages to a sandboxed per-user location that a
REM differently-launched process can't import, which silently drops the tray to
REM headless. The venv pins ONE interpreter for deps + autostart + start-now.
REM
REM Transport is taken from env vars so autostart needs no edits:
REM   long-lived token:  setx CLAUDE_CODE_OAUTH_TOKEN "sk-ant-oat01-..."
REM   push to a SmallTV:  setx CLAWDMETER_PUSH_URL "smalltv.local"
REM   (no push var set -> serves HTTP on :8787)

set "PYCMD=py -3"
where py >nul 2>&1 || set "PYCMD=python"

if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Creating virtualenv .venv ...
    %PYCMD% -m venv "%~dp0.venv" || ( echo Could not create a venv with "%PYCMD%". & goto :fail )
)
set "VPY=%~dp0.venv\Scripts\python.exe"

echo Installing Python dependencies into .venv ...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r "%~dp0requirements.txt" --quiet || ( echo Dependency install failed. & goto :fail )

echo Verifying the tray dependencies ...
"%VPY%" -c "import pystray, PIL" || echo   WARNING: pystray/Pillow did not import; the tray will run headless.

echo Registering login autostart (tray) ...
"%VPY%" "%~dp0clawdmeter_daemon.py" --install || ( echo   WARNING: autostart was NOT registered. & goto :end )

echo.
echo Installation complete. The tray daemon starts automatically at next login.
echo   Start it now:     start-daemon.bat
echo   Run in console:   .venv\Scripts\python clawdmeter_daemon.py --no-tray --serve
echo   Stop it:          right-click the tray icon ^> Quit
echo   Uninstall:        uninstall.bat
goto :end

:fail
echo.
echo Installation failed - see the messages above.

:end
endlocal
