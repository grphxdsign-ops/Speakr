"""Local recovery interface used only when native Qt is unavailable or when
the user explicitly chooses "Open recovery panel in browser".

The server binds to loopback, serves no remote assets, and never exposes
transcript, Practice, vocabulary, clipboard, selection, or screen-context data.
Every read and mutation after the tokenized initial navigation requires the
per-run token in a custom header.
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from speakr import config as cfg_mod
from speakr.hotkey import resolve_hotkey_mode

log = logging.getLogger("speakr.webui")

PREFERRED_PORT = 43117
MAX_BODY = 16_384


class WebUI:
    def __init__(self, app):
        self.app = app
        self.token = secrets.token_urlsafe(24)
        self.nonce = secrets.token_urlsafe(18)
        self.port = None
        self._server = None
        self._capture_lock = threading.Lock()

    def start(self):
        if self._server is not None:
            return
        handler = _make_handler(self)
        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", PREFERRED_PORT), handler)
        except OSError:
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="webui", daemon=True).start()
        try:
            cfg_mod.PANEL_URL_PATH.write_text(self.url(), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not publish recovery URL: %s", exc)
        log.info("Recovery control panel available on loopback")

    def url(self):
        if self.port is None:
            return ""
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    def stop(self):
        try:
            cfg_mod.PANEL_URL_PATH.unlink()
        except OSError:
            pass
        server, self._server = self._server, None
        self.port = None
        if server is not None:
            threading.Thread(target=server.shutdown, daemon=True).start()

    def state(self):
        state = getattr(self.app, "interface_state", None)
        if state is not None:
            return state.snapshot()
        tray_state = getattr(getattr(self.app, "tray", None), "state", "idle")
        enabled = bool(getattr(self.app, "enabled", True))
        return {
            "version": 0,
            "availability": "ready" if enabled else "disabled",
            "capture": "listening" if tray_state == "recording" else "idle",
            "pipeline": "transcribing" if tray_state == "processing" else "idle",
            "enabled": enabled,
            "hotkey": self.app.config.get("hotkey"),
            "primary_text": "Ready" if enabled else "Dictation is off",
            "secondary_text": "",
            "last_issue": None,
        }

    def settings(self):
        config = self.app.config
        platform_name = "mac" if sys.platform == "darwin" else "windows"
        settings = {
            "hotkey": config.get("hotkey"),
            "toggle_mode": bool(config.get("toggle_mode")),
            "keep_mic_stream_open": bool(config.get("keep_mic_stream_open")),
            "preroll_seconds": float(config.get("preroll_seconds", default=0.4)),
            "screen_context": bool(config.get("screen_context", "enabled", default=True)),
            "edit_mode": bool(config.get("edit_mode", "enabled", default=True)),
            "recent_context": bool(config.get("formatting", "include_recent_context", default=True)),
            "log_transcripts": bool(config.get("log_transcripts", default=False)),
            "log_path": str(cfg_mod.LOG_PATH),
            "platform": platform_name,
            "capturing_hotkey": bool(getattr(self.app, "capturing_hotkey", False)),
            "pending_hotkey": getattr(self.app, "pending_hotkey", None) or "",
        }
        settings.update(
            resolve_hotkey_mode(
                settings["hotkey"],
                settings["toggle_mode"],
                platform=platform_name,
            )
        )
        return settings

    def wait_state(self, after: int, timeout: float = 20.0):
        state = getattr(self.app, "interface_state", None)
        if state is not None and hasattr(state, "wait"):
            return state.wait(after, timeout) or self.state()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.state()
            if int(current.get("version", 0)) > after:
                return current
            time.sleep(0.25)
        return self.state()

    def capture(self):
        if not self._capture_lock.acquire(blocking=False):
            return {"ok": False, "busy": True}
        try:
            name = self.app.capture_hotkey(timeout=None)
            return {
                "ok": name is not None,
                "busy": False,
                "hotkey": self.app.config.get("hotkey"),
            }
        finally:
            self._capture_lock.release()


def _make_handler(ui: WebUI):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SpeakrRecovery/1"

        def log_message(self, fmt, *args):
            pass

        def _allowed_host(self):
            host = self.headers.get("Host", "")
            return host in {f"127.0.0.1:{ui.port}", f"localhost:{ui.port}"}

        def _allowed_origin(self):
            origin = self.headers.get("Origin")
            return origin in (None, "null", f"http://127.0.0.1:{ui.port}", f"http://localhost:{ui.port}")

        def _authed(self):
            return secrets.compare_digest(self.headers.get("X-Speakr-Token", ""), ui.token)

        def _initial_authed(self, parsed):
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            return bool(supplied) and secrets.compare_digest(supplied, ui.token)

        def _security_headers(self, ctype):
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
                "clipboard-read=(), clipboard-write=()",
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                f"script-src 'nonce-{ui.nonce}'; style-src 'unsafe-inline'; "
                "connect-src 'self'; img-src data:; font-src 'none'; "
                "frame-ancestors 'none'; form-action 'none'; base-uri 'none'",
            )

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self._security_headers(ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code, value):
            self._send(code, json.dumps(value, ensure_ascii=False, separators=(",", ":")))

        def _read_json(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if size < 0 or size > MAX_BODY:
                return None
            try:
                return json.loads(self.rfile.read(size) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

        def _request_allowed(self):
            if not self._allowed_host() or not self._allowed_origin():
                self._json(403, {"ok": False})
                return False
            return True

        def do_OPTIONS(self):
            self._json(403, {"ok": False})

        def do_GET(self):
            if not self._request_allowed():
                return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                if not self._initial_authed(parsed):
                    self._json(403, {"ok": False})
                    return
                page = PAGE.replace("__TOKEN__", ui.token).replace("__NONCE__", ui.nonce)
                self._send(200, page, "text/html")
                return
            if not self._authed():
                self._json(403, {"ok": False})
                return
            if parsed.path == "/api/state":
                self._json(200, ui.state())
            elif parsed.path == "/api/settings":
                self._json(200, ui.settings())
            elif parsed.path == "/api/wait":
                try:
                    after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                except ValueError:
                    after = 0
                self._json(200, ui.wait_state(after, timeout=20.0))
            else:
                self._json(404, {"ok": False})

        def do_POST(self):
            if not self._request_allowed():
                return
            if not self._authed():
                self._json(403, {"ok": False})
                return
            parsed = urlparse(self.path)
            body = self._read_json()
            if body is None:
                self._json(400, {"ok": False, "message": "Invalid request."})
                return
            if parsed.path == "/api/action":
                action = body.get("action")
                if action == "toggle_dictation":
                    ok = ui.app.toggle_enabled()
                elif action == "begin_hotkey_capture":
                    ok = ui.app.begin_hotkey_capture()
                elif action == "cancel_hotkey_capture":
                    ui.app.cancel_hotkey_capture()
                    ok = True
                elif action == "confirm_hotkey":
                    ok = ui.app.confirm_hotkey()
                elif action == "dismiss_issue":
                    ok = ui.app.dismiss_issue()
                elif action == "open_system_settings":
                    ok = ui.app.open_system_settings()
                elif action == "retry_model":
                    ok = ui.app.retry_model()
                elif action == "retry_setup":
                    ok = ui.app.retry_setup()
                elif action == "open_local" and body.get("kind") in {"config", "log"}:
                    ok = ui.app.open_local(body["kind"])
                else:
                    self._json(404, {"ok": False})
                    return
                self._json(200, {"ok": bool(ok), "state": ui.state(), "settings": ui.settings()})
            elif parsed.path == "/api/setting":
                safe_paths = {
                    "toggle_mode", "keep_mic_stream_open", "screen_context.enabled",
                    "edit_mode.enabled", "formatting.include_recent_context", "log_transcripts",
                }
                path = str(body.get("path", ""))
                if path not in safe_paths:
                    self._json(403, {"ok": False})
                    return
                ok = ui.app.set_setting(path, body.get("value"))
                self._json(200, {"ok": bool(ok), "settings": ui.settings(), "state": ui.state()})
            else:
                self._json(404, {"ok": False})

    return Handler


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Speakr recovery panel</title>
<style>
:root{color-scheme:light dark;--canvas:#EDF1FA;--surface:#F8FAFF;--surface-glass:#F8FAFF;--surface-soft:#F8FAFF;--well:#F8FAFF;--ink:#17182A;--muted:#55596D;--line:#747A92;--line-soft:rgba(116,122,146,.4);--accent:#6657D8;--accent-hover:#5749C4;--accent-text:#F8FAFF;--good:#24694D;--good-soft:rgba(36,105,77,.1);--warn:#765000;--bad:#9A3044;--bad-soft:rgba(154,48,68,.08);--focus:#6657D8;--shadow:0 24px 70px rgba(42,45,79,.16),0 3px 14px rgba(42,45,79,.08);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-size:16px}
@media(prefers-color-scheme:dark){:root{--canvas:#090B18;--surface:#20243A;--surface-glass:#20243A;--surface-soft:#20243A;--well:#282C45;--ink:#F2F3FC;--muted:#B4B7C9;--line:#737A99;--line-soft:rgba(115,122,153,.42);--accent:#A89AFB;--accent-hover:#B9AEFC;--accent-text:#17182A;--good:#7DD7B0;--good-soft:rgba(125,215,176,.11);--warn:#F0C56A;--bad:#FF9CAA;--bad-soft:rgba(255,156,170,.09);--focus:#C3BBFF;--shadow:0 30px 80px rgba(1,2,10,.42),0 3px 16px rgba(1,2,10,.3)}}
*{box-sizing:border-box}
html{min-width:320px;background:var(--canvas)}
body{isolation:isolate;margin:0;min-height:100vh;color:var(--ink);background:radial-gradient(circle at 12% 8%,rgba(102,87,216,.19) 0,rgba(102,87,216,0) 34%),radial-gradient(circle at 88% 18%,rgba(74,174,201,.14) 0,rgba(74,174,201,0) 31%),radial-gradient(circle at 72% 94%,rgba(205,119,156,.12) 0,rgba(205,119,156,0) 34%),var(--canvas);overflow-x:hidden}
body::before,body::after{content:"";position:fixed;z-index:0;pointer-events:none;border:1px solid var(--line-soft);border-radius:50%;opacity:.48}
body::before{width:min(76vw,880px);height:min(76vw,880px);left:-31vw;top:18vh;transform:rotate(-18deg)}
body::after{width:min(58vw,680px);height:min(34vw,400px);right:-18vw;top:8vh;transform:rotate(24deg)}
button,input{font:inherit}
button{min-height:44px;border:1px solid var(--line);border-radius:14px;background:var(--well);color:var(--ink);padding:10px 16px;font-weight:600;cursor:pointer;box-shadow:0 1px 0 rgba(255,255,255,.08);transition:background-color 100ms cubic-bezier(.22,1,.36,1),border-color 100ms cubic-bezier(.22,1,.36,1),color 100ms cubic-bezier(.22,1,.36,1),transform 100ms cubic-bezier(.22,1,.36,1)}
button:hover{border-color:var(--line);background:var(--surface)}
button:active{transform:scale(.99)}
button:focus-visible,input:focus-visible,[tabindex="-1"]:focus-visible{outline:2px solid var(--focus);outline-offset:3px}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-text)}
button.primary:hover{background:var(--accent-hover);border-color:var(--accent-hover)}
.shell{position:relative;z-index:1;width:min(100%,1080px);margin:0 auto;padding:clamp(18px,4vw,46px)}
.top{display:flex;gap:24px;align-items:center;justify-content:space-between;margin-bottom:18px;padding:12px 4px}
.brandgroup{display:flex;align-items:center;gap:13px;min-height:44px}
.brand{font-size:1.75rem;font-weight:720;letter-spacing:-.035em}
.signal{display:flex;align-items:center;gap:5px;color:var(--accent)}
.signal i{display:block;width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:none}
.signal i:nth-of-type(2){width:9px;height:9px}
.signal span{display:block;width:14px;height:1px;background:currentColor;opacity:.65}
.local{display:flex;align-items:center;gap:9px;min-height:44px;padding:9px 14px;border:1px solid var(--line);border-radius:999px;background:var(--surface-soft);color:var(--muted);font-size:.94rem;font-weight:550}
.local i{flex:0 0 auto;width:10px;height:10px;border-radius:50%;background:var(--good);box-shadow:0 0 0 4px var(--good-soft)}
nav{display:flex;align-items:center;gap:6px;width:max-content;max-width:100%;margin:0 0 14px;padding:6px;border:1px solid var(--line);border-radius:20px;background:var(--surface-soft);box-shadow:0 6px 24px rgba(23,24,42,.07)}
.navbtn{border-color:transparent;background:transparent;color:var(--muted);box-shadow:none;white-space:nowrap}
.navbtn:hover{border-color:transparent;background:var(--well);color:var(--ink)}
.navbtn[aria-current=page]{background:var(--well);border-color:var(--line);color:var(--ink);box-shadow:0 5px 14px rgba(23,24,42,.09)}
main{position:relative;overflow:hidden;min-height:520px;padding:clamp(24px,4vw,44px);border:1px solid var(--line);border-radius:28px;background:var(--surface-glass);box-shadow:var(--shadow)}
main::before{content:"";position:absolute;inset:0 0 auto;height:1px;background:rgba(255,255,255,.34);pointer-events:none}
section{position:relative}
section[hidden]{display:none}
section>h1{margin:0 0 8px;font-size:1.75rem;line-height:1.2;letter-spacing:-.025em}
section>h1+p{max-width:62ch;margin:0 0 24px;color:var(--muted);line-height:1.55}
.status{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:18px;align-items:center;margin-bottom:10px;padding:20px;border:1px solid var(--line-soft);border-radius:20px;background:var(--well)}
.stateicon{display:grid;place-items:center;width:52px;height:52px;border:1px solid var(--line);border-radius:18px;background:var(--good-soft);color:var(--good);font-size:1.35rem;font-weight:700}
.status h1{margin:0 0 5px;font-size:1.75rem;line-height:1.2;letter-spacing:-.025em}
.status p,h2+p{max-width:65ch;margin:0;color:var(--muted);line-height:1.5}
.setting{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center;padding:20px 4px;border-bottom:1px solid var(--line-soft)}
.setting:last-child{border-bottom:0}
.setting strong{display:block;margin-bottom:5px;font-size:1rem}
.setting small{display:block;max-width:62ch;color:var(--muted);font-size:.94rem;line-height:1.5}
.setting>div:last-child{min-width:150px;text-align:right}
.switch{display:flex;gap:10px;align-items:center;min-height:44px;color:var(--muted);font-weight:550}
.switch input{width:24px;height:24px;margin:0;accent-color:var(--accent)}
.issue{margin-top:18px;padding:18px 20px;border:1px solid var(--bad);border-radius:20px;background:var(--bad-soft)}
.issue strong{color:var(--bad)}
.issue p{margin-top:8px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.privacylist{margin:8px 0 0;padding:0;list-style:none;border-top:1px solid var(--line-soft)}
.privacylist li{padding:18px 4px;border-bottom:1px solid var(--line-soft)}
.privacylist b{display:block;margin-bottom:5px}
.privacylist span{display:block;max-width:68ch;color:var(--muted);line-height:1.55}
.hotkey{display:inline-block;min-height:34px;padding:7px 11px;border:1px solid var(--line-soft);border-radius:10px;background:var(--surface);font-variant-numeric:tabular-nums;font-weight:700;line-height:1.2}
.warning{margin-top:8px;color:var(--warn)}
.fine{max-width:70ch;color:var(--muted);font-size:.94rem;line-height:1.6}
h2{margin:30px 0 7px;font-size:1.15rem;letter-spacing:-.01em}
@media(max-width:760px){.shell{padding:18px}.top{align-items:flex-start}.local{max-width:330px}nav{width:100%;overflow-x:auto}.navbtn{flex:1 0 auto}main{min-height:0;padding:26px}.status{grid-template-columns:auto minmax(0,1fr)}.status .primary{grid-column:1/-1;width:100%}}
@media(max-width:540px){.shell{padding:12px}.top{display:grid;gap:8px;padding:5px 2px 8px}.local{justify-content:flex-start;width:100%;max-width:none;border-radius:14px}nav{display:grid;grid-template-columns:1fr;padding:5px;border-radius:18px;overflow:visible}.navbtn{width:100%;text-align:left}main{padding:20px;border-radius:22px}.status,.setting{grid-template-columns:1fr;gap:14px}.stateicon{width:46px;height:46px;border-radius:14px}.setting>div:last-child{min-width:0;text-align:left}.setting .actions{margin-top:10px}.switch{justify-content:flex-start}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition-duration:0s!important;animation-duration:0s!important;animation-iteration-count:1!important}}
@media(prefers-contrast:more){:root{--surface-glass:var(--surface);--surface-soft:var(--surface);--well:var(--surface);--line-soft:var(--line);--shadow:none}body{background:var(--canvas)}body::before,body::after{display:none}.local,.navbtn[aria-current=page],main,.status,.issue{border-width:2px}}
@media(forced-colors:active){:root{--shadow:none}body{background:Canvas}body::before,body::after,main::before{display:none}.local,nav,main{background:Canvas;border-color:CanvasText;box-shadow:none}.navbtn[aria-current=page],button.primary,.status,.hotkey,.issue{background:Canvas;border:2px solid CanvasText;color:CanvasText;box-shadow:none}.local i{background:CanvasText;box-shadow:none}.stateicon{border:2px solid CanvasText;background:Canvas;color:CanvasText}.issue strong{color:CanvasText}}
</style>
</head>
<body>
<div class="shell">
  <header class="top"><div class="brandgroup"><div class="brand">Speakr</div><div class="signal" aria-hidden="true"><i></i><span></span><i></i><span></span><i></i></div></div><div class="local"><i aria-hidden="true"></i><span>Everything stays on this device</span></div></header>
  <nav aria-label="Recovery panel"><button class="navbtn" data-page="home" aria-current="page">Home</button><button class="navbtn" data-page="privacy">Privacy &amp; local data</button><button class="navbtn" data-page="help">Help</button></nav>
  <main>
    <section id="home">
      <div class="status" role="status" aria-live="polite" aria-atomic="true"><div class="stateicon" id="stateicon" aria-hidden="true">✓</div><div><h1 id="primary" tabindex="-1">Getting Speakr ready</h1><p id="secondary">Preparing the local speech model.</p></div><button class="primary" id="toggle">Turn dictation off</button></div>
      <div id="issue" class="issue" hidden role="alert"><strong id="issueTitle"></strong><p id="issueDetail" class="fine"></p><div class="actions"><button id="issueAction" hidden>Open system settings</button><button id="recheckIssue" hidden>Recheck setup</button><button id="dismissIssue">Dismiss</button></div></div>
      <div class="setting"><div><strong>Activation shortcut</strong><small id="shortcutHelp">Choose Change, then press one key. Speakr listens system-wide until you choose Cancel or press Escape. This browser page never receives the key.</small></div><div><span class="hotkey" id="hotkey">...</span><div class="actions"><button id="captureKey">Change</button><button id="cancelKey" hidden>Cancel</button><button id="confirmKey" hidden class="primary">Confirm</button></div></div></div>
      <div class="actions"><button id="openSettings">Open system privacy settings</button><button id="openConfig">Open local config</button><button id="openLog">Open local log</button></div>
    </section>
    <section id="privacy" hidden>
      <h1 tabindex="-1">Privacy &amp; local data</h1><p>These controls describe exactly what Speakr keeps while it runs.</p>
      <ul class="privacylist">
        <li><b>Microphone readiness</b><span id="micDisclosure">When enabled, a short rolling audio buffer is held only in RAM and continuously replaced.</span></li>
        <li><b>Screen context</b><span>Reads nearby focused-control text locally for spelling hints. It is not placed in this panel or stored.</span></li>
        <li><b>Edit mode</b><span>May inspect selected text locally so a spoken edit instruction can replace it.</span></li>
        <li><b>Recent cleanup context</b><span>Keeps the last few inserted results in memory only to improve local cleanup.</span></li>
      </ul>
      <div class="setting"><div><strong id="keepMicLabel">Keep microphone ready</strong><small id="prerollText"></small></div><label class="switch" for="keepMic"><input type="checkbox" id="keepMic" aria-labelledby="keepMicLabel" aria-describedby="prerollText"><span id="keepMicState" aria-hidden="true">Off</span></label></div>
      <div class="setting"><div><strong id="screenContextLabel">Screen context</strong><small id="screenContextHelp">Focused text is read locally and discarded after the dictation.</small></div><label class="switch" for="screenContext"><input type="checkbox" id="screenContext" aria-labelledby="screenContextLabel" aria-describedby="screenContextHelp"><span id="screenContextState" aria-hidden="true">Off</span></label></div>
      <div class="setting"><div><strong id="editModeLabel">Edit selected text</strong><small id="editModeHelp">The original stays unchanged if local editing fails.</small></div><label class="switch" for="editMode"><input type="checkbox" id="editMode" aria-labelledby="editModeLabel" aria-describedby="editModeHelp"><span id="editModeState" aria-hidden="true">Off</span></label></div>
      <div class="setting"><div><strong id="recentContextLabel">Recent in-memory context</strong><small id="recentContextHelp">Never written by this feature.</small></div><label class="switch" for="recentContext"><input type="checkbox" id="recentContext" aria-labelledby="recentContextLabel" aria-describedby="recentContextHelp"><span id="recentContextState" aria-hidden="true">Off</span></label></div>
      <div class="setting"><div><strong id="logTranscriptsLabel">Write transcripts to the local log</strong><small id="logWarning">Off is recommended. Enabling writes dictated text to speakr.log on this device.</small></div><label class="switch" for="logTranscripts"><input type="checkbox" id="logTranscripts" aria-labelledby="logTranscriptsLabel" aria-describedby="logWarning"><span id="logTranscriptsState" aria-hidden="true">Off</span></label></div>
    </section>
    <section id="help" hidden>
      <h1 tabindex="-1">Help</h1><p>This recovery panel is a local fallback. The normal interface is the native Speakr window.</p>
      <h2>Dictate</h2><p class="fine" id="dictateHelp">Hold your shortcut, speak, then release.</p>
      <h2>Nothing was inserted</h2><p class="fine">Check microphone access, make sure the target field still has focus, then try again. Speakr never displays dictated content in this recovery panel.</p>
      <h2>Local cleanup</h2><p class="fine">If Ollama is not available, Speakr continues with its built-in rule-based cleanup.</p>
    </section>
  </main>
</div>
<script nonce="__NONCE__">
(function(){
"use strict";
var TOKEN="__TOKEN__", state={}, settings={}, stopped=false, issueCommand="";
history.replaceState(null,"","/");
function api(path, options){options=options||{};options.headers=Object.assign({"X-Speakr-Token":TOKEN,"Content-Type":"application/json"},options.headers||{});return fetch(path,options).then(function(r){if(!r.ok)throw new Error("request failed");return r.json();});}
function action(name, extra){return api("/api/action",{method:"POST",body:JSON.stringify(Object.assign({action:name},extra||{}))}).then(function(v){if(v.state)state=v.state;if(v.settings)settings=v.settings;render();return v;});}
function setSetting(path,value){return api("/api/setting",{method:"POST",body:JSON.stringify({path:path,value:value})}).then(function(v){settings=v.settings||settings;state=v.state||state;render();return v;}).catch(function(error){render();throw error;});}
function $(id){return document.getElementById(id);}
function hotkeyName(){return settings.hotkey||state.hotkey||"your shortcut";}
function toggleInstruction(listening){if(settings.effective_toggle_mode)return listening?"Press "+hotkeyName()+" again to stop.":"Press "+hotkeyName()+" once to start; press again to stop.";return listening?"Release "+hotkeyName()+" when you are finished.":"Hold "+hotkeyName()+", speak, then release.";}
function renderSwitch(inputId,stateId,value){var checked=!!value;$(inputId).checked=checked;$(stateId).textContent=checked?"On":"Off";}
function render(){
 var enabled=state.enabled!==false, capture=state.capture, pipeline=state.pipeline;
 $("primary").textContent=state.primary_text||state.primaryText||(capture==="listening"?"Listening":pipeline&&pipeline!=="idle"?"Processing locally":enabled?"Ready":"Dictation is off");
 $("secondary").textContent=capture==="listening"?toggleInstruction(true):(state.secondary_text||state.secondaryText||(enabled?toggleInstruction(false):"The shortcut is paused and microphone audio is cleared."));
 $("toggle").textContent=enabled?"Turn dictation off":"Turn dictation on";$("stateicon").textContent=capture==="listening"?"●":pipeline==="error"?"!":enabled?"✓":"Ⅱ";
 $("hotkey").textContent=(settings.pending_hotkey||settings.hotkey||state.hotkey||"Not set");
 $("captureKey").hidden=!!settings.capturing_hotkey;$("cancelKey").hidden=!settings.capturing_hotkey;$("confirmKey").hidden=!settings.pending_hotkey;
 var captureDisclosure="Choose Change, then press one key. Speakr listens system-wide until you choose Cancel or press Escape. This browser page never receives the key.";
 if(settings.toggle_mode_forced)captureDisclosure+=" This Windows key combination always uses press-to-start and press-to-stop.";
 $("shortcutHelp").textContent=captureDisclosure;$("dictateHelp").textContent=toggleInstruction(false);
 var issue=state.last_issue||state.lastIssue, issueAction=issue&&String(issue.action||""), issueChoice=null;
 if(issueAction==="open_system_settings")issueChoice={command:"open_system_settings",label:"Open system settings"};
 else if(issueAction==="retry_model")issueChoice={command:"retry_model",label:"Retry speech model"};
 else if(issueAction==="retry_setup")issueChoice={command:"retry_setup",label:"Recheck setup"};
 issueCommand=issueChoice?issueChoice.command:"";$("issue").hidden=!issue;$("issueAction").hidden=!issueChoice;$("recheckIssue").hidden=!(issue&&issueAction==="open_system_settings");
 if(issue){$("issueTitle").textContent=issue.message||"Speakr needs attention";$("issueDetail").textContent=issue.detail||"";if(issueChoice)$("issueAction").textContent=issueChoice.label;}
 renderSwitch("keepMic","keepMicState",settings.keep_mic_stream_open);renderSwitch("screenContext","screenContextState",settings.screen_context);renderSwitch("editMode","editModeState",settings.edit_mode);renderSwitch("recentContext","recentContextState",settings.recent_context);renderSwitch("logTranscripts","logTranscriptsState",settings.log_transcripts);
 var seconds=Number(settings.preroll_seconds||0).toFixed(1);$("prerollText").textContent="Keeps "+seconds+" seconds of rolling audio in RAM and continuously replaces it.";$("micDisclosure").textContent=settings.keep_mic_stream_open?"The microphone connection stays open while Ready. Only "+seconds+" seconds are held in RAM and continuously replaced.":"The microphone opens only when recording starts.";
}
function refresh(){return Promise.all([api("/api/state"),api("/api/settings")]).then(function(v){state=v[0];settings=v[1];render();});}
 function wait(){if(stopped)return;var after=Number(state.version||0);api("/api/wait?after="+after).then(function(v){if(v)state=v;render();return api("/api/settings");}).then(function(v){if(v)settings=v;render();wait();}).catch(function(){setTimeout(wait,1200);});}
document.querySelectorAll(".navbtn").forEach(function(btn){btn.addEventListener("click",function(){document.querySelectorAll(".navbtn").forEach(function(n){n.removeAttribute("aria-current");});btn.setAttribute("aria-current","page");document.querySelectorAll("main section").forEach(function(s){s.hidden=s.id!==btn.dataset.page;});document.querySelector("#"+btn.dataset.page+" h1, #"+btn.dataset.page+" .status h1").focus&&document.querySelector("#"+btn.dataset.page+" h1, #"+btn.dataset.page+" .status h1").focus();});});
$("toggle").onclick=function(){action("toggle_dictation");};$("captureKey").onclick=function(){action("begin_hotkey_capture");};$("cancelKey").onclick=function(){action("cancel_hotkey_capture");};$("confirmKey").onclick=function(){action("confirm_hotkey");};$("dismissIssue").onclick=function(){action("dismiss_issue");};$("issueAction").onclick=function(){if(issueCommand)action(issueCommand);};$("recheckIssue").onclick=function(){action("retry_setup");};$("openSettings").onclick=function(){action("open_system_settings");};$("openConfig").onclick=function(){action("open_local",{kind:"config"});};$("openLog").onclick=function(){action("open_local",{kind:"log"});};
[["keepMic","keep_mic_stream_open"],["screenContext","screen_context.enabled"],["editMode","edit_mode.enabled"],["recentContext","formatting.include_recent_context"],["logTranscripts","log_transcripts"]].forEach(function(pair){$(pair[0]).onchange=function(){if(pair[1]==="log_transcripts"&&this.checked&&!confirm("Dictated text will be written to the local file:\n"+(settings.log_path||"speakr.log")+"\n\nContinue?")){this.checked=false;renderSwitch("logTranscripts","logTranscriptsState",false);return;}setSetting(pair[1],this.checked).catch(function(){render();});};});
refresh().then(wait).catch(wait);window.addEventListener("beforeunload",function(){stopped=true;});
})();
</script>
</body>
</html>
"""
