# clawdmeter-daemon

One small daemon that shows your **Claude Code usage** on a desk device. It polls
the Claude API rate-limit headers (using the OAuth token Claude Code already stores
on your machine) and delivers your **5-hour** and **7-day** usage to the device by
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

> Not affiliated with Anthropic. The throwaway API call it makes (cheapest model,
> `max_tokens: 1`) is only to read the rate-limit response headers.

## Install

Needs Python 3.10+.

```sh
pip install -r requirements.txt
```

`httpx` is required; `pyserial` is only needed for `--serial`, and `pystray` +
`Pillow` only for the tray icon.

## Quick start

```sh
python clawdmeter_daemon.py --serial                 # USB Clawdmeter (auto-detect COM)
python clawdmeter_daemon.py --serial COM5            # ...or a specific port
python clawdmeter_daemon.py --push-to 192.168.1.50   # push to a SmallTV (or smalltv.local)
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

## Windows tray + autostart

By default the daemon shows a **system-tray icon** (the mascot): grey while
waiting, red if you're not logged in, full colour once it's serving data. Hover for
live `5h % / 7d %`; right-click for **Refresh now** / **Quit**.

- **`start-daemon.bat [flags]`** — start it now, silently (no console). Pass your
  transport, e.g. `start-daemon.bat --serial` or `start-daemon.bat --push-to smalltv.local`.
- **`install.bat`** — install dependencies and register **login autostart**. The
  autostart reads its transport from env vars, so set them once:
  `setx CLAWDMETER_PUSH_URL "smalltv.local"` (push) — otherwise it serves on `:8787`.
  Uninstall by deleting `…\Startup\ClawdmeterDaemon.lnk`.

> Microsoft-Store `pythonw` stub? Set `CLAWDMETER_PYTHONW` to your real interpreter,
> e.g. `set CLAWDMETER_PYTHONW=C:\Python314\pythonw.exe`.

## The payload contract

Every transport delivers the same object:

```json
{ "s": 29, "sr": 142, "w": 4, "wr": 9876, "st": "allowed", "ok": true }
```

| field | meaning |
|-------|---------|
| `s` / `w` | 5‑hour / 7‑day window utilization (%) |
| `sr` / `wr` | minutes until each window resets |
| `st` | rate-limit status (`allowed`, `allowed_warning`, `rejected`, …) |
| `ok` | `false` when there's no data (e.g. not logged in) |

- **serial:** one JSON line per update; reads `{"ready"}` / `{"refresh"}` back from
  the device to re-poll. `--no-hid` sends `{"hid":false}` on connect.
- **push:** `POST` to `http://<device>/api/usage`.
- **serve:** `GET http://host:port/` returns the latest object (`/healthz` too).

## Options

```
--serial [PORT]     USB serial; optional COM port, else auto-detect (VID 0x303A)
--no-hid            tell the serial device to disable its HID keys
--push-to DEVICE    HTTP-push to a device (IP or hostname); env CLAWDMETER_PUSH_URL
--push-interval N   seconds between pushes (default 20)
--serve             run the HTTP server (default when no transport is chosen)
--host / --port     bind address for --serve (default 0.0.0.0:8787)
--interval N        seconds between Claude API refreshes (default 60)
--no-tray           run headless in the console
```

## Troubleshooting

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
- **Serial device not found.** Check the cable/driver; pass the port explicitly
  (`--serial COM5`). Find it in Device Manager.

## Credits

- Original **Clawdmeter** (ESP32‑S3 desk dashboard):
  [HermannBjorgvin/Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter).
- USB/Windows fork: [clawdmeter-win](https://github.com/giovi321/clawdmeter-win).
- SmallTV firmware: [smalltv-mod](https://github.com/giovi321/smalltv-mod).

## License

[WTFPL](LICENSE) — Do What The F*ck You Want To Public License.
