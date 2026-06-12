#!/usr/bin/env python3
"""clawdmeter-daemon — one daemon, three ways to reach the device.

Polls the Claude API rate-limit headers (using the OAuth token Claude Code already
stores on this machine) and delivers your 5h / 7d usage to a desk device by any of:

  * serial  — write JSON lines over USB CDC (the original Clawdmeter ESP32-S3)
  * push    — HTTP POST to the device   (SmallTV behind Wi-Fi client isolation)
  * serve   — HTTP server the device polls (SmallTV pull mode / anything)

Pick one or several; they all share the same poller, token handling and tray icon.

    pip install -r requirements.txt
    python clawdmeter_daemon.py --serial                 # auto-detect the COM port
    python clawdmeter_daemon.py --push-to 192.168.1.50    # push to a SmallTV
    python clawdmeter_daemon.py --serve --port 8787       # serve for the device to pull
    python clawdmeter_daemon.py --serial --serve          # several at once

Firmware that speaks the contract:
  * Clawdmeter (ESP32-S3): https://github.com/giovi321/clawdmeter-win
  * SmallTV (ESP8266):     https://github.com/giovi321/smalltv-mod

Payload contract: {"s":29,"sr":142,"w":4,"wr":9876,"st":"allowed","ok":true}
  s/w  = 5h / 7d utilization %     sr/wr = minutes until each window resets
  st   = rate-limit status         ok    = false => no data (e.g. not logged in)
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

# ---- Config ---------------------------------------------------------------

DEFAULT_POLL_INTERVAL = 60     # seconds between Claude API refreshes
DEFAULT_PUSH_INTERVAL = 20     # seconds between HTTP pushes to the device
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787

# Serial auto-detect (the Clawdmeter ESP32-S3 enumerates as Espressif CDC).
ESPRESSIF_VID = 0x303A
DEVICE_PID = 0x1001
BAUD_RATE = 115200
SERIAL_TIMEOUT = 1            # s, non-blocking readline
PORT_CHECK_INTERVAL = 5      # s, re-verify the COM port still exists

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
TOKEN_ENDPOINT = "https://platform.claude.com/v1/oauth/token"
TOKEN_REFRESH_MARGIN = 300    # refresh 5 min before expiry

API_URL = "https://api.anthropic.com/v1/messages"
API_HEADERS_TEMPLATE = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "oauth-2025-04-20",
    "Content-Type": "application/json",
    "User-Agent": "claude-code/2.1.146",
}
API_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}],
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# Run a child process without flashing a console window on Windows (important when
# launched via pythonw — otherwise spawning `claude` pops a visible window).
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def _run(cmd, **kw):
    if _NO_WINDOW:
        kw["creationflags"] = kw.get("creationflags", 0) | _NO_WINDOW
    return subprocess.run(cmd, **kw)


# Spawning Claude Code is a last-resort token refresh; never do it more than once
# per this many seconds, so a failing direct refresh can't pop it every poll.
_CLAUDE_REFRESH_COOLDOWN = 900
_last_claude_refresh = 0.0


# ---- Config persistence ---------------------------------------------------
# Remembers the transport you pick in the tray, so it survives restarts.

CONFIG_PATH = Path.home() / ".clawdmeter-daemon.json"


def load_config() -> dict:
    cfg = {
        "transport": None,        # "serial" | "push" | "serve"
        "push_url": "",
        "serve_host": DEFAULT_HOST,
        "serve_port": DEFAULT_PORT,
        "serial_port": None,      # None => auto-detect
        "push_interval": DEFAULT_PUSH_INTERVAL,
    }
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except OSError as e:
        log(f"Could not save config: {e}")


# ---- Shared state ---------------------------------------------------------

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "Starting..."
        self.payload: dict = {"ok": False}
        self.version = 0           # bumped on every set_payload (serial change-detect)
        self.last_update = 0.0
        self.port = None           # serial COM port, if serial transport active
        self.push_target = ""      # device URL, if push transport active
        self.endpoint = ""         # serve URL, if serve transport active
        self.hid_enabled = True
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()

    def set_status(self, status: str, port: str | None = ...) -> None:
        with self.lock:
            self.status = status
            if port is not ...:
                self.port = port

    def set_payload(self, payload: dict, keep_last_good: bool = True) -> None:
        with self.lock:
            if payload.get("ok") or not (keep_last_good and self.payload.get("ok")):
                self.payload = payload
                self.version += 1
            if payload.get("ok"):
                self.last_update = time.time()

    def get_payload(self) -> dict:
        with self.lock:
            return dict(self.payload)

    def get_payload_versioned(self):
        with self.lock:
            return dict(self.payload), self.version

    def get_tooltip(self) -> str:
        with self.lock:
            lines = [f"clawdmeter — {self.status}"]
            p = self.payload
            if p.get("ok"):
                lines.append(f"5h {p['s']}%   7d {p['w']}%")
            if self.port:
                lines.append("serial " + self.port)
            if self.push_target:
                lines.append("push -> " + self.push_target)
            if self.endpoint and not self.push_target:
                lines.append(self.endpoint)
            return "\n".join(lines)

    def get_status_key(self) -> str:
        with self.lock:
            s = self.status.lower()
            if "token" in s or "login" in s or "error" in s:
                return "error"
            if self.payload.get("ok"):
                return "ok"
            return "searching"


state = State()
# Last reason read_token() returned None — shown in the tray/console.
_auth_hint = ""


# ---- Credential / token management ----------------------------------------

def _read_credentials_file() -> dict | None:
    try:
        return json.loads(CREDENTIALS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_credentials_file(data: dict) -> None:
    try:
        tmp = CREDENTIALS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(CREDENTIALS_PATH)
    except OSError as e:
        log(f"Error writing credentials: {e}")


def _get_oauth_block(creds: dict) -> dict | None:
    return creds.get("claudeAiOauth") if isinstance(creds, dict) else None


def _extract_access_token(blob: str) -> str | None:
    blob = blob.strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        if isinstance(data.get("accessToken"), str):
            return data["accessToken"]
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("accessToken"), str):
                return v["accessToken"]
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', blob)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob):
        return blob
    return None


def _is_token_expired(oauth: dict) -> bool:
    expires_at = oauth.get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        return False
    return time.time() >= (expires_at / 1000.0 - TOKEN_REFRESH_MARGIN)


def _refresh_token(oauth: dict, creds: dict) -> str | None:
    refresh_tok = oauth.get("refreshToken")
    if not refresh_tok:
        log("No refresh token available")
        return None
    log("Refreshing OAuth token...")
    try:
        resp = httpx.post(
            TOKEN_ENDPOINT,
            data={"grant_type": "refresh_token", "refresh_token": refresh_tok},
            headers={"User-Agent": API_HEADERS_TEMPLATE["User-Agent"]},
            timeout=20.0,
        )
    except httpx.HTTPError as e:
        log(f"Token refresh request failed: {e}")
        return None
    if resp.status_code >= 400:
        log(f"Token refresh HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError):
        log("Token refresh returned invalid JSON")
        return None
    new_access = body.get("access_token")
    if not new_access:
        log("Token refresh response missing access_token")
        return None
    oauth["accessToken"] = new_access
    if "refresh_token" in body:
        oauth["refreshToken"] = body["refresh_token"]
    if "expires_in" in body:
        oauth["expiresAt"] = int((time.time() + body["expires_in"]) * 1000)
    elif "expires_at" in body:
        oauth["expiresAt"] = int(body["expires_at"] * 1000)
    _write_credentials_file(creds)
    log("Token refreshed successfully")
    return new_access


def _refresh_via_claude_code() -> str | None:
    """Spawn Claude Code (windowless, rate-limited) so it refreshes its own token."""
    global _last_claude_refresh
    now = time.time()
    if now - _last_claude_refresh < _CLAUDE_REFRESH_COOLDOWN:
        return None
    _last_claude_refresh = now
    log("Spawning Claude Code to refresh token...")
    try:
        _run(["claude", "-p", "hi", "--max-turns", "1"], capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        log(f"Could not refresh via Claude Code: {e}")
        return None
    creds = _read_credentials_file()
    oauth = _get_oauth_block(creds) if creds else None
    if oauth and not _is_token_expired(oauth):
        log("Token refreshed via Claude Code")
        return oauth.get("accessToken")
    log("Claude Code did not refresh the token - re-login may be required")
    return None


def _read_token_keychain() -> str | None:
    import getpass
    try:
        out = _run(
            ["security", "find-generic-password", "-s",
             "Claude Code-credentials", "-a", getpass.getuser(), "-w"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError,
            subprocess.TimeoutExpired) as e:
        log(f"Keychain read failed: {e}")
        return None
    return _extract_access_token(out.stdout)


def read_token() -> str | None:
    """Return a Claude OAuth token.

    Prefers CLAUDE_CODE_OAUTH_TOKEN — a long-lived token from `claude setup-token`,
    the robust choice for an always-on daemon. Otherwise falls back to the
    credentials Claude Code stores on disk (which expire and, for some subscription
    logins, carry no refresh token, so they can't be renewed headlessly).
    """
    global _auth_hint
    env_tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if env_tok:
        _auth_hint = ""
        return env_tok

    if sys.platform == "darwin":
        tok = _read_token_keychain()
        _auth_hint = "" if tok else "Not logged in - run 'claude' to log in"
        return tok

    creds = _read_credentials_file()
    if not creds:
        _auth_hint = "No Claude credentials - run 'claude setup-token' or 'claude'"
        return None
    oauth = _get_oauth_block(creds)
    if not oauth or not isinstance(oauth.get("accessToken"), str):
        _auth_hint = "Not logged in - run 'claude setup-token' or 'claude'"
        return None

    if _is_token_expired(oauth):
        # The OAuth refresh grant + a spawned `claude` are the same autonomous
        # mechanisms the original daemon used; both need a usable refresh path. If
        # there's no refresh token and a fresh `claude` 401s, only a long-lived
        # token fixes it: `claude setup-token` -> set CLAUDE_CODE_OAUTH_TOKEN.
        tok = _refresh_token(oauth, creds) or _refresh_via_claude_code()
        _auth_hint = "" if tok else "Token expired - run: claude setup-token (long-lived)"
        return tok

    _auth_hint = ""
    return oauth.get("accessToken")


# ---- API polling ----------------------------------------------------------

def poll_api(token: str) -> tuple[dict | None, bool]:
    """Minimal API call; extract usage headers. Returns (payload, auth_failed)."""
    headers = dict(API_HEADERS_TEMPLATE)
    headers["Authorization"] = f"Bearer {token}"
    try:
        resp = httpx.post(API_URL, headers=headers, json=API_BODY, timeout=20.0)
    except httpx.HTTPError as e:
        log(f"API call failed: {e}")
        return None, False
    if resp.status_code in (401, 403):
        return None, True
    if resp.status_code >= 400:
        log(f"API HTTP {resp.status_code}: {resp.text[:200]}")
        return None, False

    now = time.time()

    def hdr(name, default="0"):
        return resp.headers.get(name, default)

    def reset_minutes(ts):
        try:
            mins = (float(ts) - now) / 60.0
        except ValueError:
            return 0
        return int(round(mins)) if mins > 0 else 0

    def pct(util):
        try:
            return int(round(float(util) * 100))
        except ValueError:
            return 0

    payload = {
        "s":  pct(hdr("anthropic-ratelimit-unified-5h-utilization")),
        "sr": reset_minutes(hdr("anthropic-ratelimit-unified-5h-reset")),
        "w":  pct(hdr("anthropic-ratelimit-unified-7d-utilization")),
        "wr": reset_minutes(hdr("anthropic-ratelimit-unified-7d-reset")),
        "st": hdr("anthropic-ratelimit-unified-5h-status", "unknown"),
        "ok": True,
    }
    return payload, False


def do_poll() -> None:
    """One poll cycle: token -> API -> update shared state."""
    token = read_token()
    if not token:
        state.set_status(_auth_hint or "No token - run 'claude setup-token'")
        state.set_payload({"ok": False})
        return
    payload, auth_failed = poll_api(token)
    if auth_failed:
        state.set_status("Refreshing token...")
        creds = _read_credentials_file()
        oauth = _get_oauth_block(creds) if creds else None
        if oauth and creds:
            new_token = _refresh_token(oauth, creds)
            if new_token:
                payload, _ = poll_api(new_token)
    if payload is not None:
        state.set_payload(payload)
        state.set_status("Connected")
        log(f"5h={payload['s']}% 7d={payload['w']}% st={payload['st']}")
    elif "token" not in state.status.lower():
        state.set_status("API error - retrying")


def poller_loop(interval: float) -> None:
    log(f"Polling Claude every {interval:.0f}s")
    while not state.stop_event.is_set():
        do_poll()
        state.refresh_event.wait(interval)
        state.refresh_event.clear()


# ---- Transport: serial (USB CDC) ------------------------------------------

def find_device_port(explicit: str | None) -> str | None:
    import serial.tools.list_ports
    if explicit:
        return explicit
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if p.vid == ESPRESSIF_VID and p.pid == DEVICE_PID:
            return p.device
    for p in ports:
        desc = (p.description or "").lower() + (p.product or "").lower()
        if "claude controller" in desc or "clawdmeter" in desc:
            return p.device
    return None


def serial_loop(stop: threading.Event, explicit_port: str | None) -> None:
    """Maintain the USB serial link: write the latest payload when it changes, and
    let the device request refreshes. Polling is done by poller_loop; we just ship.
    `stop` is the per-transport event so the tray can switch transports at runtime."""
    import serial
    import serial.tools.list_ports

    backoff = 1
    while not stop.is_set():
        port = find_device_port(explicit_port)
        if not port:
            state.set_status("Searching for serial device...", port=None)
            stop.wait(backoff)
            backoff = min(backoff * 2, 30)
            continue
        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        except serial.SerialException as e:
            log(f"Serial open failed: {e}")
            state.set_status(f"Serial error: {e}", port=None)
            stop.wait(backoff)
            backoff = min(backoff * 2, 30)
            continue

        log(f"Serial connected: {port}")
        state.set_status("Connected", port=port)
        backoff = 1
        last_sent_version = -1
        last_port_check = time.time()
        state.refresh_event.set()   # ask the poller for fresh data on connect

        if not state.hid_enabled:
            try:
                ser.write((json.dumps({"hid": False}, separators=(",", ":")) + "\n").encode())
                ser.flush()
                log("Sent HID-disabled config to device")
            except serial.SerialException:
                pass

        try:
            while not stop.is_set():
                now = time.time()
                if now - last_port_check >= PORT_CHECK_INTERVAL:
                    last_port_check = now
                    live = {p.device for p in serial.tools.list_ports.comports()}
                    if port not in live:
                        log(f"{port} disappeared - device unplugged")
                        break

                try:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                except serial.SerialException:
                    log("Serial read error - device disconnected")
                    break
                if line:
                    try:
                        msg = json.loads(line)
                        if msg.get("refresh") or msg.get("ready"):
                            state.refresh_event.set()   # device wants fresh data
                        elif not (msg.get("ack") or msg.get("err")):
                            log(f"Device: {line}")
                    except json.JSONDecodeError:
                        log(f"Device: {line}")

                payload, version = state.get_payload_versioned()
                if version != last_sent_version and payload.get("ok"):
                    try:
                        ser.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
                        ser.flush()
                        last_sent_version = version
                    except serial.SerialException:
                        log("Serial write error - device disconnected")
                        break
        finally:
            try:
                ser.close()
            except Exception:
                pass
            with state.lock:
                state.port = None
        if not stop.is_set():
            state.set_status("Serial disconnected - reconnecting...", port=None)
            stop.wait(2)


# ---- Transport: HTTP server (device pulls) --------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: dict):
        data = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path.rstrip("/") in ("/healthz", "/health"):
            self._send(200, {"ok": True})
            return
        self._send(200, state.get_payload())

    def log_message(self, *args):
        pass


# ---- Transport: HTTP push (daemon POSTs to device) ------------------------

def normalize_push_url(v: str) -> str:
    v = v.strip()
    if not v.startswith(("http://", "https://")):
        v = "http://" + v
    if "/api/usage" not in v:
        v = v.rstrip("/") + "/api/usage"
    return v


def push_loop(stop: threading.Event, url: str, interval: float) -> None:
    log(f"Pushing usage to {url} every {interval:.0f}s")
    state.push_target = url
    first_ok = True
    while not stop.is_set():
        payload = state.get_payload()
        if payload.get("ok"):
            try:
                r = httpx.post(url, json=payload, timeout=10.0)
                if r.status_code >= 400:
                    log(f"Push HTTP {r.status_code}")
                elif first_ok:
                    log("Pushing to device OK")
                    first_ok = False
            except httpx.HTTPError as e:
                log(f"Push failed: {e}")
                first_ok = True
        stop.wait(interval)


# ---- Transport supervisor (runtime switch from the tray) ------------------

class Transports:
    NAMES = ("serial", "push", "serve")
    LABELS = {
        "serial": "Serial (USB)",
        "push":   "HTTP push to device",
        "serve":  "HTTP serve (device pulls)",
    }

    def __init__(self, cfg: dict):
        self.lock = threading.RLock()
        self.cfg = cfg
        self.active = None
        self._stop = None        # per-transport stop event for the running thread
        self._server = None      # ThreadingHTTPServer while serving

    def select(self, name: str) -> None:
        if name not in self.NAMES:
            return
        with self.lock:
            if name == self.active:
                return
            self._teardown()
            self.active = name
            self.cfg["transport"] = name
            save_config(self.cfg)
            stop = threading.Event()
            self._stop = stop
            if name == "serial":
                threading.Thread(target=serial_loop,
                                 args=(stop, self.cfg.get("serial_port")), daemon=True).start()
            elif name == "push":
                url = (self.cfg.get("push_url") or "").strip()
                if not url:
                    state.set_status("HTTP push: set CLAWDMETER_PUSH_URL")
                    log("Push selected but no target - set CLAWDMETER_PUSH_URL or --push-to")
                else:
                    threading.Thread(
                        target=push_loop,
                        args=(stop, normalize_push_url(url),
                              float(self.cfg.get("push_interval", DEFAULT_PUSH_INTERVAL))),
                        daemon=True).start()
            elif name == "serve":
                host = self.cfg.get("serve_host", DEFAULT_HOST)
                port = int(self.cfg.get("serve_port", DEFAULT_PORT))
                try:
                    self._server = ThreadingHTTPServer((host, port), Handler)
                except OSError as e:
                    state.set_status(f"serve error: {e}")
                    log(f"serve bind failed: {e}")
                    return
                state.endpoint = f"http://{host}:{port}/"
                threading.Thread(target=self._server.serve_forever, daemon=True).start()
            log(f"Transport -> {name}")

    def _teardown(self) -> None:
        if self._stop is not None:
            self._stop.set()
            self._stop = None
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        state.endpoint = ""
        state.push_target = ""
        with state.lock:
            state.port = None
        self.active = None

    def shutdown(self) -> None:
        with self.lock:
            self._teardown()


# ---- System tray ----------------------------------------------------------

# Mascot pose for the tray icon (claudepix idle frame; digits index MASCOT_PALETTE).
MASCOT_ROWS = [
    "00000000000000000000",
    "00000000000000000000",
    "00000000000000000000",
    "00000000000000000000",
    "00000111111111110000",
    "00000111111111110000",
    "00000112111112110000",
    "00011112111112111100",
    "00011111111111111100",
    "00011111111111111100",
    "00010111111111110100",
    "00000111111111110000",
    "00000111111111110000",
    "00000111111111110000",
    "00000100100010010000",
    "00000100100010010000",
    "00000100100010010000",
    "00000000000000000000",
    "00000000000000000000",
    "00000000000000000000",
]
MASCOT_PALETTE = [0x0000, 0xCBED, 0x0861, 0, 0, 0, 0, 0, 0, 0]  # RGB565; 1=body, 2=eye


def _rgb565(c: int) -> tuple:
    r, g, b = (c >> 11) & 0x1F, (c >> 5) & 0x3F, c & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


def _make_icon_image(status_key: str):
    """Render the mascot into a tray icon, tinted by status."""
    from PIL import Image
    scale = 4
    n = len(MASCOT_ROWS)
    img = Image.new("RGBA", (n * scale, n * scale), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(MASCOT_ROWS):
        for x, ch in enumerate(row):
            idx = int(ch)
            if idx == 0:
                continue
            r, g, b = _rgb565(MASCOT_PALETTE[idx])
            if status_key == "searching":             # dim grey while waiting
                lum = (r * 30 + g * 59 + b * 11) // 100
                r = g = b = lum
            elif status_key == "error" and idx == 1:   # redden the body on error
                r, g, b = 200, 70, 55
            for dy in range(scale):
                for dx in range(scale):
                    px[x * scale + dx, y * scale + dy] = (r, g, b, 255)
    return img


def run_with_tray(transports: "Transports") -> None:
    import pystray
    icons = {k: _make_icon_image(k) for k in ("ok", "searching", "error")}

    def on_refresh(icon, item):
        state.refresh_event.set()

    def on_quit(icon, item):
        state.stop_event.set()
        state.refresh_event.set()
        transports.shutdown()
        icon.stop()

    def transport_item(name):
        # Radio item: pick how the daemon sends data; switches live + is remembered.
        return pystray.MenuItem(
            Transports.LABELS[name],
            lambda icon, item, n=name: transports.select(n),
            checked=lambda item, n=name: transports.active == n,
            radio=True,
        )

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: state.get_tooltip(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        transport_item("serial"),
        transport_item("push"),
        transport_item("serve"),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Refresh now", on_refresh),
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("clawdmeter", icon=icons["searching"],
                        title="clawdmeter - starting...", menu=menu)

    def updater():
        last = None
        while not state.stop_event.is_set():
            key = state.get_status_key()
            if key != last:
                last = key
                icon.icon = icons.get(key, icons["searching"])
            icon.title = state.get_tooltip()
            state.stop_event.wait(2)

    threading.Thread(target=updater, daemon=True).start()
    icon.run()
    state.stop_event.set()


def run_console() -> None:
    def _stop(*_):
        log("Stopping")
        state.stop_event.set()
        state.refresh_event.set()
    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (ValueError, AttributeError):
        pass
    state.stop_event.wait()


# ---- Entry point ----------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Deliver Claude usage to a desk device (serial / push / serve).")
    # Transports (any combination; defaults to --serve if none chosen).
    ap.add_argument("--serial", nargs="?", const="auto", default=None,
                    metavar="PORT", help="use USB serial; optional COM port (else auto-detect)")
    ap.add_argument("--no-hid", action="store_true", help="tell the serial device to disable HID keys")
    ap.add_argument("--push-to", default=None,
                    metavar="DEVICE", help="use HTTP push to this device, e.g. 192.168.1.50 or smalltv.local")
    ap.add_argument("--push-interval", type=float, default=None)
    ap.add_argument("--serve", action="store_true", help="use the HTTP server (device polls)")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--interval", type=float, default=DEFAULT_POLL_INTERVAL,
                    help="seconds between Claude API refreshes (default 60)")
    ap.add_argument("--tray", action="store_true", help="show the tray icon (default)")
    ap.add_argument("--no-tray", action="store_true", help="run headless in the console")
    args = ap.parse_args()

    state.hid_enabled = not args.no_hid

    # Remembered config; a transport flag (or the tray menu) overrides it.
    cfg = load_config()
    if not cfg.get("push_url"):
        cfg["push_url"] = (os.environ.get("CLAWDMETER_PUSH_URL")
                           or os.environ.get("SMALLTV_PUSH_URL") or "")
    chosen = None
    if args.serial is not None:
        cfg["serial_port"] = None if args.serial == "auto" else args.serial
        chosen = "serial"
    if args.push_to:
        cfg["push_url"] = args.push_to
        chosen = "push"
    if args.serve:
        chosen = "serve"
    if args.host is not None:
        cfg["serve_host"] = args.host
    if args.port is not None:
        cfg["serve_port"] = args.port
    if args.push_interval is not None:
        cfg["push_interval"] = args.push_interval

    initial = chosen or cfg.get("transport") or "serve"
    save_config(cfg)

    threading.Thread(target=poller_loop, args=(args.interval,), daemon=True).start()
    transports = Transports(cfg)
    transports.select(initial)
    log(f"clawdmeter-daemon: transport = {initial}  (switch from the tray menu)")

    use_tray = not args.no_tray
    if use_tray:
        try:
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
            run_with_tray(transports)
        except ImportError:
            log("pystray/Pillow not installed - running headless (pip install pystray Pillow)")
            run_console()
    else:
        run_console()
    transports.shutdown()
    log("Stopped")


if __name__ == "__main__":
    main()
