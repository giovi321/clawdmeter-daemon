# Changelog

## v1.0.2

Keep the tray menu compact when pushing to several devices.

- The menu header no longer lists every full push URL inline (which stretched the
  popover very wide with multiple targets). It now shows a one-line summary with the
  first host trimmed to its IP/hostname plus a `(+N more)` count.
- The full target list moved to the icon's hover tooltip, with hosts trimmed and
  capped at six plus a `(+N more)`.
- Also fixes the header running lines together (e.g. `Connected5h 9%`), since it is
  now a single explicitly-spaced line.

## v1.0.1

Fix the Windows tray silently starting headless (no icon).

- `install.bat` now creates a self-contained `.venv`, installs the dependencies into
  it, and registers autostart to use it. `start-daemon.bat` launches that same
  `.venv` interpreter. Previously the launchers relied on the `py`/`pyw` launcher,
  which can resolve a different Python than the one the deps were installed into (the
  Microsoft Store Python installs to a sandboxed location another launch can't
  import), so `pystray`/`Pillow` failed to import and the daemon fell back to headless
  with no tray icon.
- `uninstall.bat` removes the autostart registry value directly, so it no longer
  depends on a working Python, and points at the `.venv` for cleanup.

## v1.0.0

First cross-platform release. The daemon now runs with full feature parity on
Windows, macOS and Linux, including a tray / menu-bar icon and login autostart on
each.

### Added
- `--install` / `--uninstall` / `--autostart-status`: per-user login autostart, no
  admin, using each OS's native mechanism (Windows `HKCU\...\Run` via `winreg`,
  macOS LaunchAgent plist, Linux XDG `.desktop`). The registered command uses the
  interpreter you install with (windowless `pythonw` on Windows), never a hardcoded
  path.
- Cross-platform tray backend detection: on Linux the daemon checks for a display and
  an AppIndicator/Xlib backend and falls back to headless with a clear message instead
  of crashing; on macOS it registers as a menu-bar accessory (no Dock icon).
- File logging to `~/.clawdmeter-daemon.log`, so a windowless or headless launch is no
  longer silent when something goes wrong.
- POSIX helper scripts `install.sh`, `start-daemon.sh`, `uninstall.sh`. `install.sh`
  creates a self-contained `.venv` with `--system-site-packages`, which sidesteps the
  PEP 668 "externally managed environment" block and still lets a Linux tray see the
  system GTK / AppIndicator bindings.

### Changed
- Windows launchers no longer hardcode `C:\Python314\pythonw.exe` or rely on the
  Microsoft Store `pythonw` alias stub. `start-daemon.bat` uses the windowless `pyw`
  launcher; `install.bat` / `uninstall.bat` pick one interpreter for both dependency
  install and autostart so they cannot diverge, and report if autostart registration
  fails instead of claiming success.
- Autostart replaces the previous Startup-folder shortcut + VBS wrapper chain with the
  registry Run key. `uninstall.bat` still clears the legacy shortcuts.
- README documents install, autostart and tray for all three platforms.

### Notes
- Tray backend on Linux needs system packages (`install.sh` prints the command for
  your distro); GNOME on Wayland also needs the AppIndicator extension. Without a
  backend the daemon runs headless.
- macOS tray needs `pyobjc-framework-Cocoa` (installed automatically via a
  requirements marker).
