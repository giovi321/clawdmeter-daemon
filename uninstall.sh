#!/bin/sh
# Remove clawdmeter-daemon's login autostart and stop a running instance on macOS/Linux.
# The daemon files themselves are left in place - delete the folder to remove them.
cd "$(dirname "$0")"
if [ -n "$PYTHON" ]; then PY="$PYTHON"
elif [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python3"; fi

echo "Removing login autostart..."
"$PY" clawdmeter_daemon.py --uninstall

echo "Stopping any running instance..."
pkill -f 'clawdmeter_daemon\.py' 2>/dev/null || true

echo
echo "Autostart removed. Optional cleanup you can run yourself:"
echo "  rm -rf .venv                      # the local virtualenv install.sh made"
echo "  rm -f ~/.clawdmeter-daemon.json   # forget the saved transport"
echo "  rm -f ~/.clawdmeter-daemon.log    # the daemon log"
