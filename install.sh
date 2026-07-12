#!/bin/sh
# Install clawdmeter-daemon on macOS / Linux: dependencies + login autostart (tray).
# Autostart is written by the daemon's --install, per-OS and per-user (no sudo):
#   macOS  ~/Library/LaunchAgents/com.giovi321.clawdmeter.plist
#   Linux  ~/.config/autostart/clawdmeter-daemon.desktop  (runs in the GUI session)
# Set the transport once via env vars (no autostart edits needed):
#   export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."   # long-lived token
#   export CLAWDMETER_PUSH_URL="smalltv.local"          # push (else serves :8787)
set -e
cd "$(dirname "$0")"
BASE_PY="${PYTHON:-python3}"

# Modern macOS (Homebrew) and Debian/Ubuntu mark the system Python
# "externally managed" (PEP 668), so a plain `pip install` is refused. Use a
# self-contained venv beside the script. --system-site-packages lets a Linux tray
# still see the system PyGObject/AppIndicator bindings (pip can't provide those),
# and autostart registers this venv's own python so it always has the deps.
VENV=".venv"
VPY="$VENV/bin/python"
if [ ! -x "$VPY" ]; then
    echo "Creating a virtualenv (.venv)..."
    if ! "$BASE_PY" -m venv --system-site-packages "$VENV"; then
        echo "Could not create a venv (Debian/Ubuntu need the python3-venv package)."
        echo "Install that, or install the deps yourself and run:"
        echo "  $BASE_PY clawdmeter_daemon.py --install"
        exit 1
    fi
fi

echo "Installing Python dependencies into .venv ..."
"$VPY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$VPY" -m pip install -r requirements.txt

# Linux tray needs system packages pip can't provide; nudge the user if missing.
if [ "$(uname)" = "Linux" ]; then
    if ! "$VPY" -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('AyatanaAppIndicator3','0.1')" >/dev/null 2>&1 \
       && ! "$VPY" -c "import gi; gi.require_version('AppIndicator3','0.1')" >/dev/null 2>&1; then
        cat <<'HINT'

Heads-up: a Linux system-tray icon needs AppIndicator + GTK bindings (and Tk for
the push-targets dialog), which are OS packages, not pip:
  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 python3-tk
  Fedora:        sudo dnf install python3-gobject gtk3 libayatana-appindicator-gtk3 python3-tkinter
  Arch:          sudo pacman -S python-gobject gtk3 libayatana-appindicator tk
  GNOME on Wayland also needs the "AppIndicator and KStatusNotifier Support" extension.
Without a tray backend the daemon still runs headless.
HINT
    fi
fi

echo "Registering login autostart (tray)..."
"$VPY" clawdmeter_daemon.py --install

echo
echo "Installation complete. The tray daemon starts at your next login."
echo "  Start it now:   ./start-daemon.sh"
echo "  Run in console: $VPY clawdmeter_daemon.py --no-tray --serve"
echo "  Uninstall:      ./uninstall.sh"
