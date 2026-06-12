@echo off
setlocal

REM Remove clawdmeter-daemon's login autostart (and the legacy SmallTV / Clawdmeter
REM autostarts, since this merged daemon replaces them), and stop a running instance.
REM The daemon files themselves are left in place — delete the folder to remove them.

echo Stopping any running usage daemon...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' OR name='python.exe'\" | Where-Object { $_.CommandLine -match 'clawdmeter_daemon|smalltv_usage_daemon|claude_usage_daemon' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
echo Removing startup shortcuts...
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
echo   del "%USERPROFILE%\.clawdmeter-daemon.json"          ^(forget the saved transport^)
echo   reg delete HKCU\Environment /v CLAWDMETER_PUSH_URL /f
echo   reg delete HKCU\Environment /v SMALLTV_PUSH_URL /f
echo   reg delete HKCU\Environment /v CLAUDE_CODE_OAUTH_TOKEN /f   ^(only if you stop using the daemon^)
endlocal
