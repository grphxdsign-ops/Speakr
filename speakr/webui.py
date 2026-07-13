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
        return {
            "hotkey": config.get("hotkey"),
            "toggle_mode": bool(config.get("toggle_mode")),
            "keep_mic_stream_open": bool(config.get("keep_mic_stream_open")),
            "preroll_seconds": float(config.get("preroll_seconds", default=0.4)),
            "screen_context": bool(config.get("screen_context", "enabled", default=True)),
            "edit_mode": bool(config.get("edit_mode", "enabled", default=True)),
            "recent_context": bool(config.get("formatting", "include_recent_context", default=True)),
            "log_transcripts": bool(config.get("log_transcripts", default=False)),
            "log_path": str(cfg_mod.LOG_PATH),
            "platform": "mac" if sys.platform == "darwin" else "windows",
            "capturing_hotkey": bool(getattr(self.app, "capturing_hotkey", False)),
            "pending_hotkey": getattr(self.app, "pending_hotkey", None) or "",
        }

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
:root{color-scheme:light dark;--bg:#f4f6fa;--surface:#fbfcfe;--surface2:#e9edf5;--ink:#202531;--muted:#596274;--line:#c7cedb;--accent:#315fd4;--accentText:#f7f9ff;--good:#247a52;--warn:#8a5a00;--bad:#a93546;--focus:#174ebd;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-size:16px}
@media(prefers-color-scheme:dark){:root{--bg:#161a22;--surface:#1d222c;--surface2:#272e3a;--ink:#f0f3fa;--muted:#b5bdcb;--line:#4a5364;--accent:#7ea3ff;--accentText:#101723;--good:#73d5a4;--warn:#efbd63;--bad:#ff929c;--focus:#a9c1ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);min-height:100vh}.shell{max-width:980px;margin:auto;padding:28px}.top{display:flex;gap:20px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:20px}.brand{font-size:1.75rem;font-weight:700}.local{display:flex;align-items:center;gap:8px;color:var(--muted)}.local i{width:11px;height:11px;border-radius:50%;background:var(--good)}nav{display:flex;gap:8px;margin:20px 0}button,.navbtn{font:inherit;min-height:44px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);padding:10px 16px;cursor:pointer}button:hover,.navbtn:hover{background:var(--surface2)}button:focus-visible,input:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.navbtn[aria-current=page],button.primary{background:var(--accent);color:var(--accentText);border-color:var(--accent)}main{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:clamp(20px,4vw,40px)}section[hidden]{display:none}.status{display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:24px}.stateicon{display:grid;place-items:center;width:48px;height:48px;border:2px solid var(--line);border-radius:50%;font-size:1.4rem}.status h1{font-size:1.75rem;margin:0 0 5px}.status p,h2+p{color:var(--muted);margin:0;line-height:1.5}.setting{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:center;padding:18px 0;border-bottom:1px solid var(--line)}.setting:last-child{border-bottom:0}.setting strong{display:block;margin-bottom:4px}.setting small{color:var(--muted);line-height:1.45;display:block;max-width:62ch}.switch{display:flex;gap:10px;align-items:center}.switch input{width:24px;height:24px}.issue{margin-top:20px;padding:18px;border:1px solid var(--bad);border-radius:10px}.issue strong{color:var(--bad)}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}.privacylist{padding:0;list-style:none}.privacylist li{padding:16px 0;border-bottom:1px solid var(--line)}.privacylist b{display:block;margin-bottom:5px}.privacylist span{color:var(--muted);line-height:1.5}.hotkey{font-variant-numeric:tabular-nums;font-weight:650}.warning{color:var(--warn);margin-top:8px}.fine{color:var(--muted);font-size:.94rem;line-height:1.55;max-width:70ch}@media(max-width:680px){.shell{padding:16px}.top{align-items:flex-start}.local{max-width:180px}nav{overflow:auto}main{padding:20px}.status,.setting{grid-template-columns:1fr}.stateicon{display:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
@media(forced-colors:active){*{forced-color-adjust:auto}.local i{background:CanvasText}.issue{border:2px solid CanvasText}}
</style>
</head>
<body>
<div class="shell">
  <header class="top"><div class="brand">Speakr</div><div class="local"><i aria-hidden="true"></i><span>Everything stays on this device</span></div></header>
  <nav aria-label="Recovery panel"><button class="navbtn" data-page="home" aria-current="page">Home</button><button class="navbtn" data-page="privacy">Privacy &amp; local data</button><button class="navbtn" data-page="help">Help</button></nav>
  <main>
    <section id="home">
      <div class="status" role="status" aria-live="polite" aria-atomic="true"><div class="stateicon" id="stateicon" aria-hidden="true">✓</div><div><h1 id="primary">Getting Speakr ready</h1><p id="secondary">Preparing the local speech model.</p></div><button class="primary" id="toggle">Turn dictation off</button></div>
      <div id="issue" class="issue" hidden role="alert"><strong id="issueTitle"></strong><p id="issueDetail" class="fine"></p><div class="actions"><button id="issueAction">Open system settings</button><button id="dismissIssue">Dismiss</button></div></div>
      <div class="setting"><div><strong>Activation shortcut</strong><small>Use Hold to talk or Tap to start and stop. Shortcut capture has no hidden background access.</small></div><div><span class="hotkey" id="hotkey">...</span><div class="actions"><button id="captureKey">Change</button><button id="cancelKey" hidden>Cancel</button><button id="confirmKey" hidden class="primary">Confirm</button></div></div></div>
      <div class="actions"><button id="openSettings">Open system privacy settings</button><button id="openConfig">Open local config</button><button id="openLog">Open local log</button></div>
    </section>
    <section id="privacy" hidden>
      <h1>Privacy &amp; local data</h1><p>These controls describe exactly what Speakr keeps while it runs.</p>
      <ul class="privacylist">
        <li><b>Microphone readiness</b><span id="micDisclosure">When enabled, a short rolling audio buffer is held only in RAM and continuously replaced.</span></li>
        <li><b>Screen context</b><span>Reads nearby focused-control text locally for spelling hints. It is not placed in this panel or stored.</span></li>
        <li><b>Edit mode</b><span>May inspect selected text locally so a spoken edit instruction can replace it.</span></li>
        <li><b>Recent cleanup context</b><span>Keeps the last few inserted results in memory only to improve local cleanup.</span></li>
      </ul>
      <div class="setting"><div><strong>Keep microphone ready</strong><small id="prerollText"></small></div><label class="switch"><input type="checkbox" id="keepMic"><span>Enabled</span></label></div>
      <div class="setting"><div><strong>Screen context</strong><small>Focused text is read locally and discarded after the dictation.</small></div><label class="switch"><input type="checkbox" id="screenContext"><span>Enabled</span></label></div>
      <div class="setting"><div><strong>Edit selected text</strong><small>The original stays unchanged if local editing fails.</small></div><label class="switch"><input type="checkbox" id="editMode"><span>Enabled</span></label></div>
      <div class="setting"><div><strong>Recent in-memory context</strong><small>Never written by this feature.</small></div><label class="switch"><input type="checkbox" id="recentContext"><span>Enabled</span></label></div>
      <div class="setting"><div><strong>Write transcripts to the local log</strong><small id="logWarning">Off is recommended. Enabling writes dictated text to speakr.log on this device.</small></div><label class="switch"><input type="checkbox" id="logTranscripts"><span>Enabled</span></label></div>
    </section>
    <section id="help" hidden>
      <h1>Help</h1><p>This recovery panel is a local fallback. The normal interface is the native Speakr window.</p>
      <h2>Dictate</h2><p class="fine">Hold your shortcut, speak, then release. In Tap mode, press once to start and again to stop.</p>
      <h2>Nothing was inserted</h2><p class="fine">Check microphone access, make sure the target field still has focus, then try again. Speakr never displays dictated content in this recovery panel.</p>
      <h2>Local cleanup</h2><p class="fine">If Ollama is not available, Speakr continues with its built-in rule-based cleanup.</p>
    </section>
  </main>
</div>
<script nonce="__NONCE__">
(function(){
"use strict";
var TOKEN="__TOKEN__", state={}, settings={}, stopped=false;
history.replaceState(null,"","/");
function api(path, options){options=options||{};options.headers=Object.assign({"X-Speakr-Token":TOKEN,"Content-Type":"application/json"},options.headers||{});return fetch(path,options).then(function(r){if(!r.ok)throw new Error("request failed");return r.json();});}
function action(name, extra){return api("/api/action",{method:"POST",body:JSON.stringify(Object.assign({action:name},extra||{}))}).then(function(v){if(v.state)state=v.state;if(v.settings)settings=v.settings;render();return v;});}
function setSetting(path,value){return api("/api/setting",{method:"POST",body:JSON.stringify({path:path,value:value})}).then(function(v){settings=v.settings||settings;state=v.state||state;render();});}
function $(id){return document.getElementById(id);}
function render(){
 var enabled=state.enabled!==false, capture=state.capture, pipeline=state.pipeline;
 $("primary").textContent=state.primary_text||state.primaryText||(capture==="listening"?"Listening":pipeline&&pipeline!=="idle"?"Processing locally":enabled?"Ready":"Dictation is off");
 $("secondary").textContent=state.secondary_text||state.secondaryText||(enabled?"Hold "+(settings.hotkey||state.hotkey||"your shortcut")+", speak, then release.":"The shortcut is paused and microphone audio is cleared.");
 $("toggle").textContent=enabled?"Turn dictation off":"Turn dictation on";$("stateicon").textContent=capture==="listening"?"●":pipeline==="error"?"!":enabled?"✓":"Ⅱ";
 $("hotkey").textContent=(settings.pending_hotkey||settings.hotkey||state.hotkey||"Not set");
 $("captureKey").hidden=!!settings.capturing_hotkey;$("cancelKey").hidden=!settings.capturing_hotkey;$("confirmKey").hidden=!settings.pending_hotkey;
 var issue=state.last_issue||state.lastIssue;$("issue").hidden=!issue;if(issue){$("issueTitle").textContent=issue.message||"Speakr needs attention";$("issueDetail").textContent=issue.detail||"";$("issueAction").hidden=issue.action!=="open_system_settings";}
 $("keepMic").checked=!!settings.keep_mic_stream_open;$("screenContext").checked=!!settings.screen_context;$("editMode").checked=!!settings.edit_mode;$("recentContext").checked=!!settings.recent_context;$("logTranscripts").checked=!!settings.log_transcripts;
 var seconds=Number(settings.preroll_seconds||0).toFixed(1);$("prerollText").textContent="Keeps "+seconds+" seconds of rolling audio in RAM and continuously replaces it.";$("micDisclosure").textContent=settings.keep_mic_stream_open?"The microphone connection stays open while Ready. Only "+seconds+" seconds are held in RAM and continuously replaced.":"The microphone opens only when recording starts.";
}
function refresh(){return Promise.all([api("/api/state"),api("/api/settings")]).then(function(v){state=v[0];settings=v[1];render();});}
 function wait(){if(stopped)return;var after=Number(state.version||0);api("/api/wait?after="+after).then(function(v){if(v)state=v;render();return api("/api/settings");}).then(function(v){if(v)settings=v;render();wait();}).catch(function(){setTimeout(wait,1200);});}
document.querySelectorAll(".navbtn").forEach(function(btn){btn.addEventListener("click",function(){document.querySelectorAll(".navbtn").forEach(function(n){n.removeAttribute("aria-current");});btn.setAttribute("aria-current","page");document.querySelectorAll("main section").forEach(function(s){s.hidden=s.id!==btn.dataset.page;});document.querySelector("#"+btn.dataset.page+" h1, #"+btn.dataset.page+" .status h1").focus&&document.querySelector("#"+btn.dataset.page+" h1, #"+btn.dataset.page+" .status h1").focus();});});
$("toggle").onclick=function(){action("toggle_dictation");};$("captureKey").onclick=function(){action("begin_hotkey_capture");};$("cancelKey").onclick=function(){action("cancel_hotkey_capture");};$("confirmKey").onclick=function(){action("confirm_hotkey");};$("dismissIssue").onclick=function(){action("dismiss_issue");};$("issueAction").onclick=function(){action("open_system_settings");};$("openSettings").onclick=function(){action("open_system_settings");};$("openConfig").onclick=function(){action("open_local",{kind:"config"});};$("openLog").onclick=function(){action("open_local",{kind:"log"});};
[["keepMic","keep_mic_stream_open"],["screenContext","screen_context.enabled"],["editMode","edit_mode.enabled"],["recentContext","formatting.include_recent_context"],["logTranscripts","log_transcripts"]].forEach(function(pair){$(pair[0]).onchange=function(){if(pair[1]==="log_transcripts"&&this.checked&&!confirm("Dictated text will be written to the local file:\n"+(settings.log_path||"speakr.log")+"\n\nContinue?")){this.checked=false;return;}setSetting(pair[1],this.checked);};});
refresh().then(wait).catch(wait);window.addEventListener("beforeunload",function(){stopped=true;});
})();
</script>
</body>
</html>
"""
