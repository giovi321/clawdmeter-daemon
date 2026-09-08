# clawdmeter-daemon

One small daemon that shows your **Claude Code usage** on a desk device. It reads the
Claude usage endpoint (using the OAuth token Claude Code already stores on your
machine) and delivers your **5-hour** and **7-day** usage to the device by
whichever transport fits your setup:

| Transport | How | For |
|-----------|-----|-----|
| **serial** | writes JSON lines over USB CDC | the original **Clawdmeter** (ESP32‑S3, USB‑attached) |
| **push** | HTTP `POST` to the device | a **SmallTV** behind Wi‑Fi **client isolation** (device can't reach the PC) |
| **serve** | HTTP server the device polls | a **SmallTV** in pull mode, n8n, anything |

Pick one or several — they share the same poller, token handling and tray icon.

This merges the two device-specific daemons into one:
- **Clawdmeter (ESP32‑S3, serial):** https://github.com/giovi321/clawdmeter-win
- **SmallTV (ESP8266, HTTP):** https://github.com/giovi321/smalltv-mod

> Not affiliated with Anthropic. It reads `GET /api/oauth/usage`, a plain status
> query, so a poll spends no inference request and does not consume the quota it
> reports. Short intervals are safe.

## Install

Needs Python 3.10+. Works on Windows, macOS and Linux.

```sh
pip install -r requirements.txt
```

Recommended: use the wrapper that installs deps and registers login autostart in one
step: `install.bat` (Windows) / `./install.sh` (macOS/Linux). Both create a
self-contained `.venv` beside the script and register autostart to use it, so the
daemon always starts with its dependencies. This matters because the interpreter a
launcher resolves at start time is not always the one you installed deps into — on
Windows the Microsoft Store Python installs packages to a sandboxed location another
launch can't import, which silently drops the tray to headless; on modern
Homebrew/Debian the system Python refuses a plain `pip install` (PEP 668). The
macOS/Linux venv uses `--system-site-packages` so a Linux tray still sees the system
GTK/AppIndicator bindings.

A manual `pip install -r requirements.txt` into your own environment works too, as
long as you launch the daemon with that same interpreter.

`httpx` is required; `pyserial` is only needed for `--serial`, `pystray` +
`Pillow` only for the tray icon, and `zeroconf` only for mDNS auto-discovery on
`--push` (without it, push still works via explicit `--push-to` hosts). On
**macOS** the tray also needs `pyobjc-framework-Cocoa` (auto-installed by the
requirements marker). On **Linux** the tray needs the AppIndicator + GTK system
packages and `python3-tk` for the push-targets dialog — `install.sh` prints the
exact command for your distro; without them the daemon runs headless.

## Quick start

```sh
python clawdmeter_daemon.py --serial                 # USB Clawdmeter (auto-detect COM)
python clawdmeter_daemon.py --serial COM5            # ...or a specific port
python clawdmeter_daemon.py --push                   # push to every SmallTV it finds (mDNS)
python clawdmeter_daemon.py --push-to 192.168.1.50   # push to a specific SmallTV (or smalltv.local)
python clawdmeter_daemon.py --serve --port 8787      # serve for the device to pull
python clawdmeter_daemon.py --serial --serve         # several at once
python clawdmeter_daemon.py --no-tray --serve        # headless console
```

With no transport flag it defaults to `--serve` on `:8787`.

## Authentication (the durable way)

The daemon needs a Claude token. In order it tries:

1. **`CLAUDE_CODE_OAUTH_TOKEN`** env var — a **long-lived token** from
   `claude setup-token`. This is the robust choice for an always-on daemon: it
   doesn't expire, so there's nothing to refresh.
2. macOS Keychain / `~/.claude/.credentials.json`, refreshing via the OAuth
   refresh grant or by briefly spawning `claude` (same autonomous mechanisms the
   original daemon used).

The on-disk session credentials expire (often every few hours) and, for some
subscription logins, carry **no refresh token** — then nothing can renew them
headlessly. So for a set-and-forget daemon:

```sh
claude setup-token        # subscription required; prints a token (sk-ant-oat…)
# Windows:  setx CLAUDE_CODE_OAUTH_TOKEN "sk-ant-oat...your-token..."
# macOS/Linux:  export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat..."  in your shell profile
```

Then restart the daemon from a **new** shell so it inherits the variable.

## Tray icon + autostart (Windows, macOS, Linux)

By default the daemon shows a **tray / menu-bar icon** (the mascot): grey while
waiting, red if you're not logged in, full colour once it's serving data. Hover for
live `5h % / 7d %`. **Right-click (macOS: click) to pick the transport** — *Serial
(USB)* / *HTTP push to device* / *HTTP serve* — which switches **live** and is
**remembered** (in `~/.clawdmeter-daemon.json`), plus **Configure push targets…**,
**Refresh now** and **Quit**. So you don't need flags after the first run; the tray
is the switch. **Configure push targets…** opens a box to type one or more device
IPs/hostnames (comma-separated, e.g. `192.168.1.44, 192.168.1.45`); it applies
immediately and is remembered. Leave it blank to rely on mDNS auto-discovery only.
(*HTTP push* also seeds its targets from `CLAWDMETER_PUSH_URL` / `SMALLTV_PUSH_URL`
/ `--push-to`.)

### Autostart at login

`--install` registers the tray daemon to start at login, per-user and without admin,
using each OS's native mechanism — no hardcoded Python path (it registers the
interpreter you run it with):

| OS | Mechanism | Where |
|----|-----------|-------|
| Windows | `HKCU\…\Run` value (windowless `pythonw`) | Task Manager → Startup |
| macOS | LaunchAgent | `~/Library/LaunchAgents/com.giovi321.clawdmeter.plist` |
| Linux | XDG autostart `.desktop` (GUI session) | `~/.config/autostart/clawdmeter-daemon.desktop` |

```sh
python clawdmeter_daemon.py --install            # register autostart at login
python clawdmeter_daemon.py --uninstall          # remove it
python clawdmeter_daemon.py --autostart-status   # show what's registered
```

The autostart command is just `--tray`; the transport comes from the remembered
config and the env vars above, so autostart needs no edits — set them once (e.g.
`CLAWDMETER_PUSH_URL=smalltv.local` for push, otherwise it serves on `:8787`).

Convenience scripts wrap dependency install + `--install`:

- **Windows** — `install.bat` (creates `.venv`, installs deps, registers autostart),
  `start-daemon.bat [flags]` (start now, silent, using the `.venv` interpreter),
  `uninstall.bat` (remove autostart, stop the process, and clear the **legacy**
  `SmallTVUsageDaemon` / `ClaudeUsageDaemon` shortcuts this merged daemon replaced).
- **macOS / Linux** — `./install.sh`, `./start-daemon.sh [flags]`, `./uninstall.sh`
  (set `PYTHON=/path/to/python3` to force an interpreter).

> Windows Microsoft-Store `pythonw` stub, or a non-default interpreter? Set
> `CLAWDMETER_PYTHONW` before `start-daemon.bat`, e.g.
> `set CLAWDMETER_PYTHONW=C:\Python314\pythonw.exe`.

> The tray icon starts in the Windows 11 `⌃` overflow area — drag it onto the
> taskbar to pin it. On **GNOME/Wayland** there is no tray at all without the
> *AppIndicator and KStatusNotifier Support* extension; without a usable tray backend
> the daemon logs a note and runs headless (it keeps working, just no icon).

Anything the daemon logs also goes to **`~/.clawdmeter-daemon.log`** — the place to
look if a windowless/headless launch seems to do nothing.

## The payload contract

Every transport delivers the same object:

```json
{ "s": 29, "sr": 142, "w": 4, "wr": 9876, "st": "normal", "ok": true }
```

| field | meaning |
|-------|---------|
| `s` / `w` | 5‑hour / 7‑day window utilization (%) |
| `sr` / `wr` | minutes until each window resets |
| `st` | session limit severity (`normal`, `warning`, `rejected`, …) |
| `ok` | `false` when there's no data (e.g. not logged in) |

- **serial:** one JSON line per update; reads `{"ready"}` / `{"refresh"}` back from
  the device to re-poll. `--no-hid` sends `{"hid":false}` on connect.
- **push:** `POST` to `http://<device>/api/usage`.
- **serve:** `GET http://host:port/` returns the latest object (`/healthz` too).

> `st` changed vocabulary in v1.1.0, when the daemon moved to the usage endpoint. It
> used to carry the rate-limit header status (`allowed`, `allowed_warning`,
> `rejected`). Firmware that branches on the exact string wants **smalltv-mod
> 2.13.1+**; older builds read `normal` as a warning and light the accent dot.

## Options

```
--serial [PORT]     USB serial; optional COM port, else auto-detect (VID 0x303A)
--no-hid            tell the serial device to disable its HID keys
--push              HTTP-push with mDNS auto-discovery of every SmallTV on the LAN
                    (mDNS is link-local: won't cross subnets/VLANs, see Troubleshooting)
--push-to DEVICE    HTTP-push to a device (IP or hostname). Repeatable
                    (--push-to A --push-to B) and/or comma-separated
                    (--push-to "A,B"); env CLAWDMETER_PUSH_URL accepts the same list
--no-discover       disable mDNS discovery for push (only push to --push-to hosts)
--push-interval N   seconds between pushes (default 20)
--serve             run the HTTP server (default when no transport is chosen)
--host / --port     bind address for --serve (default 0.0.0.0:8787)
--interval N        seconds between Claude API refreshes (default 60)
--no-tray           run headless in the console
--install           register autostart at login (per-user) and exit
--uninstall         remove the autostart entry and exit
--autostart-status  print whether autostart is registered and exit
```

## Troubleshooting

- **No tray icon appears.** First check `~/.clawdmeter-daemon.log`. If it says
  `pystray/Pillow not installed - running headless`, the daemon is running under a
  Python that lacks the tray deps (a launcher resolved a different interpreter than
  you installed into — common with the Microsoft Store Python). Fix: run `install.bat`
  / `./install.sh`, which pin a `.venv`, or set `CLAWDMETER_PYTHONW` to a Python that
  has `pystray` + `Pillow`. If the log instead shows the daemon polling, it's running
  and the icon is just hidden or unsupported. **Windows 11:** the icon starts in the
  `⌃` overflow flyout; drag it onto the taskbar. **Linux (GNOME/Wayland):** there is no
  tray without the *AppIndicator and KStatusNotifier Support* extension, and the icon
  needs the AppIndicator/GTK packages (see Install); without a backend the daemon logs
  a note and runs headless. **macOS:** it's a menu-bar icon (no Dock icon by design).
- **Tray says "Token expired - run: claude setup-token".** Your on-disk credentials
  expired and can't be renewed headlessly. Use a long-lived token (see
  [Authentication](#authentication-the-durable-way)).
- **Device never shows data (push/serve).** The device must be able to reach the PC
  (serve) or the PC the device (push). On Wi‑Fi with **client/AP isolation** the
  device can't open a connection back — use **push** mode. Also open the PC's
  firewall for `--serve` (`New-NetFirewallRule -DisplayName clawdmeter -Direction
  Inbound -Protocol TCP -LocalPort 8787 -Action Allow`).
- **Device IP keeps changing.** Push to its mDNS name (e.g. `smalltv.local`) or set
  a DHCP reservation.
- **Several SmallTVs on one network.** With firmware **2.8.0+** just run `--push`:
  each device advertises itself over mDNS (`_clawdmeter._tcp`) and the daemon
  discovers them all and pushes the same usage to every one, no per-device address.
  Devices that join or drop off are picked up on the next push. Needs `zeroconf`
  (in `requirements.txt`).
- **Auto-discovery finds nothing (but the devices are reachable).** mDNS is
  **link-local** — it does not cross routers/VLANs. If the daemon PC and the SmallTVs
  are on **different subnets** (e.g. PC on `192.168.2.x`, devices on `192.168.10.x`),
  discovery sees nothing and `.local` names won't resolve, even though direct IP
  still routes. Fixes: run the daemon on a machine **on the same subnet** as the
  devices (then `--push` just works), or enable an **mDNS reflector/repeater** on
  your router between the VLANs, or skip discovery and **list the device IPs
  explicitly** — via the tray's *Configure push targets…*, or
  `--push-to 192.168.10.44 --push-to 192.168.10.45` (or `--push-to "192.168.10.44,192.168.10.45"`).
  For a fixed IP list, add **DHCP reservations** so the addresses don't drift.
- **Only some devices update.** You listed one host but have several — add the rest
  (tray *Configure push targets…* or repeated/comma-separated `--push-to`), or use
  `--push` if they're all on the daemon's subnet. On older firmware, push to each
  device's unique hostname (`smalltv-3fa2.local`) by hand.
- **Serial device not found.** Check the cable/driver; pass the port explicitly
  (`--serial COM5`). Find it in Device Manager.

## Credits

- Original **Clawdmeter** (ESP32‑S3 desk dashboard):
  [HermannBjorgvin/Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter).
- USB/Windows fork: [clawdmeter-win](https://github.com/giovi321/clawdmeter-win).
- SmallTV firmware: [smalltv-mod](https://github.com/giovi321/smalltv-mod).

## License

[WTFPL](LICENSE) — Do What The F*ck You Want To Public License.
