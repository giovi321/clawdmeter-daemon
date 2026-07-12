#!/bin/sh
# Start clawdmeter-daemon now (tray icon), in the background. Autostart at login is
# set up separately by install.sh. Pass flags through, e.g. ./start-daemon.sh --serial
cd "$(dirname "$0")"
if [ -n "$PYTHON" ]; then PY="$PYTHON"
elif [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python3"; fi
nohup "$PY" clawdmeter_daemon.py --tray "$@" >/dev/null 2>&1 &
echo "clawdmeter-daemon started (tray). Log: ~/.clawdmeter-daemon.log"
