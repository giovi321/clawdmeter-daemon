@echo off
setlocal
cd /d "%~dp0"

REM Remove clawdmeter-daemon's login autostart and stop a running instance.
REM The daemon files themselves are left in place - delete the folder to remove them.

echo Stopping any running usage daemon...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' OR name='python.exe' OR name='pyw.exe'\" | Where-Object { $_.CommandLine -match 'clawdmeter_daemon|smalltv_usage_daemon|claude_usage_daemon' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Removing login autostart...
REM Delete the HKCU Run value directly so uninstall never depends on a working Python.
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v clawdmeter /f >nul 2>&1 && echo   removed HKCU Run\clawdmeter

REM Legacy cleanup: older versions used a Startup-folder shortcut + a VBS wrapper,
REM and this merged daemon replaced two device-specific autostarts.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
for %%F in (ClawdmeterDaemon SmallTVUsageDaemon ClaudeUsageDaemon) do (
    if exist "%STARTUP%\%%F.lnk" (
        del "%STARTUP%\%%F.lnk"
        echo   removed %%F.lnk
    )
)
if exist "%~dp0run_daemon.vbs" (
    del "%~dp0run_daemon.vbs"
    echo   removed run_daemon.vbs
)

echo.
echo Autostart removed - the daemon will not launch at login anymore.
echo Optional cleanup you can run yourself:
echo   rmdir /s /q "%~dp0.venv"                              ^(the local virtualenv install.bat made^)
echo   del "%USERPROFILE%\.clawdmeter-daemon.json"          ^(forget the saved transport^)
echo   del "%USERPROFILE%\.clawdmeter-daemon.log"           ^(the daemon log^)
echo   reg delete HKCU\Environment /v CLAWDMETER_PUSH_URL /f
echo   reg delete HKCU\Environment /v SMALLTV_PUSH_URL /f
echo   reg delete HKCU\Environment /v CLAUDE_CODE_OAUTH_TOKEN /f   ^(only if you stop using the daemon^)
endlocal
