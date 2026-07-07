"""Speakr's control panel: a loopback-only HTTP server rendering a small
window that mirrors the speakr.cloud site — one power toggle, one setting
(click to change the push-to-talk key, captured natively so even the Mac
fn key works). Opened from the tray; identical on Windows and macOS.

Security model: bound to 127.0.0.1 only, and every state-changing request
must carry a per-run random token that is embedded in the served page —
another website can fire blind cross-origin POSTs at localhost but can
never read the token, and the custom header forces a CORS preflight that
this server never approves.
"""

import json
import logging
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("speakr.webui")

PREFERRED_PORT = 43117

STATE_LABELS = {
    "loading": "Loading model…",
    "idle": "Listening for {key}",
    "recording": "Recording…",
    "processing": "Processing…",
    "disabled": "Dictation is off",
    "error": "Error — check the tray",
}


class WebUI:
    def __init__(self, app):
        self.app = app
        self.token = secrets.token_urlsafe(16)
        self.port = None
        self._server = None
        self._capture_lock = threading.Lock()

    def start(self):
        handler = _make_handler(self)
        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", PREFERRED_PORT), handler)
        except OSError:
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="webui", daemon=True).start()
        log.info("Control panel at %s", self.url())

    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def stop(self):
        if self._server is not None:
            threading.Thread(target=self._server.shutdown, daemon=True).start()

    # ----- state for the page ----------------------------------------------

    def state(self):
        app = self.app
        tray_state = getattr(app.tray, "state", "idle")
        state = tray_state if app.enabled else "disabled"
        hotkey = app.config.get("hotkey")
        return {
            "enabled": app.enabled,
            "hotkey": hotkey,
            "state": state,
            "status": STATE_LABELS.get(state, state).format(key=hotkey),
            "mac": sys.platform == "darwin",
        }

    def capture(self):
        if not self._capture_lock.acquire(blocking=False):
            return {"ok": False, "busy": True}
        try:
            name = self.app.capture_hotkey(timeout=8.0)
            return {"ok": name is not None, "busy": False, "hotkey": self.app.config.get("hotkey")}
        finally:
            self._capture_lock.release()


def _make_handler(ui: WebUI):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep HTTP chatter out of speakr.log
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authed(self):
            return self.headers.get("X-Speakr-Token") == ui.token

        def do_GET(self):
            if self.path.split("?")[0] == "/":
                self._send(200, PAGE.replace("__TOKEN__", ui.token), ctype="text/html")
            elif self.path == "/api/state":
                self._send(200, json.dumps(ui.state()))
            else:
                self._send(404, "{}")

        def do_POST(self):
            if not self._authed():
                self._send(403, "{}")
                return
            if self.path == "/api/toggle":
                ui.app.toggle_enabled()
                self._send(200, json.dumps(ui.state()))
            elif self.path == "/api/capture":
                result = ui.capture()
                self._send(200 if not result.get("busy") else 409, json.dumps(result))
            else:
                self._send(404, "{}")

    return Handler


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Speakr</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%234D9FFF'/%3E%3Cstop offset='1' stop-color='%238B5CF6'/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx='32' cy='32' r='30' fill='url(%23g)'/%3E%3Crect x='25' y='13' width='14' height='26' rx='7' fill='white'/%3E%3Cpath d='M18 34a14 14 0 0 0 28 0' stroke='white' stroke-width='5' fill='none' stroke-linecap='round'/%3E%3Cpath d='M32 48v6M24 54h16' stroke='white' stroke-width='5' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
:root{
  --bg:#04050a; --ink:#eef1fb; --dim:#8a92ad;
  --blue:#4d9fff; --violet:#8b5cf6; --pink:#c084fc;
  --line:rgba(140,160,255,.14); --glass:rgba(16,20,38,.55);
  --font:'Space Grotesk',system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--font);min-height:100vh;
  overflow-x:hidden;-webkit-font-smoothing:antialiased;display:flex;flex-direction:column;align-items:center}
::selection{background:rgba(139,92,246,.45);color:#fff}
.aurora{position:fixed;inset:-25%;z-index:0;pointer-events:none;filter:blur(80px);opacity:.5}
.aurora span{position:absolute;border-radius:50%;mix-blend-mode:screen}
.aurora .a1{width:70vmax;height:70vmax;left:-20vmax;top:-30vmax;background:radial-gradient(circle,rgba(45,90,255,.5),transparent 65%);animation:d1 22s ease-in-out infinite alternate}
.aurora .a2{width:60vmax;height:60vmax;right:-25vmax;bottom:-30vmax;background:radial-gradient(circle,rgba(139,92,246,.45),transparent 65%);animation:d2 28s ease-in-out infinite alternate}
@keyframes d1{to{transform:translate(8vmax,6vmax)}}
@keyframes d2{to{transform:translate(-7vmax,-8vmax)}}
.grain{position:fixed;inset:0;z-index:30;pointer-events:none;opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23n)'/%3E%3C/svg%3E")}
.wrap{position:relative;z-index:2;width:min(430px,92vw);padding:34px 0 42px;display:flex;flex-direction:column;align-items:center}
header{width:100%;display:flex;align-items:center;justify-content:space-between;margin-bottom:38px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:1.15rem;letter-spacing:-.02em}
.brand svg{width:30px;height:30px;filter:drop-shadow(0 0 12px rgba(99,132,255,.6))}
.pill{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:.68rem;letter-spacing:.08em;
  color:#9db4ff;border:1px solid var(--line);padding:7px 14px;border-radius:99px;background:rgba(30,45,120,.16)}
.pill .dot{width:8px;height:8px;border-radius:50%;background:#5eff9d;box-shadow:0 0 10px #5eff9d;transition:.3s}
.pill.off .dot{background:#4a5568;box-shadow:none}
.pill.rec .dot{background:#ff4d6a;box-shadow:0 0 10px #ff4d6a;animation:pulse 1s infinite}
.pill.busy .dot{background:#ffb84d;box-shadow:0 0 10px #ffb84d}
@keyframes pulse{50%{opacity:.35}}

.power{position:relative;width:172px;height:172px;border-radius:50%;cursor:pointer;border:none;outline:none;
  background:linear-gradient(#0a0e1e,#0a0e1e) padding-box,linear-gradient(135deg,var(--blue),var(--violet),var(--pink)) border-box;
  border:2px solid transparent;display:grid;place-items:center;transition:box-shadow .45s,transform .15s;
  box-shadow:0 0 0 rgba(0,0,0,0)}
.power:active{transform:scale(.96)}
/* Inverse fill: an absolutely-positioned gradient layer crossfades in via
   opacity on ".on" — transitioning "background" itself doesn't animate
   (gradients aren't interpolatable), so a separate layer is the reliable way
   to get a smooth fill-in rather than a hard cut between the two looks. */
.power::before{content:"";position:absolute;inset:0;border-radius:50%;
  background:linear-gradient(135deg,var(--blue),var(--violet),var(--pink));
  opacity:0;transition:opacity .45s}
.power.on::before{opacity:1}
.power svg{position:relative;width:64px;height:64px;stroke:#3a4266;fill:none;stroke-width:2.4;stroke-linecap:round;transition:stroke .4s,filter .4s}
.power.on{box-shadow:0 0 70px rgba(100,120,255,.5),0 0 24px rgba(139,92,246,.45)}
.power.on svg{stroke:#04050a;filter:drop-shadow(0 2px 6px rgba(0,0,0,.35))}
.power::after{content:"";position:absolute;inset:-14px;border-radius:50%;border:1px solid rgba(120,140,255,.35);
  opacity:0;pointer-events:none}
.power.on::after{animation:ring 2.4s ease-out infinite}
@keyframes ring{0%{transform:scale(.92);opacity:.7}100%{transform:scale(1.22);opacity:0}}
.power:focus-visible{outline:2px solid var(--blue);outline-offset:6px}
.statusline{margin-top:26px;font-family:var(--mono);font-size:.8rem;color:var(--dim);letter-spacing:.04em;
  min-height:1.4em;text-align:center}
.statusline b{color:var(--ink);font-weight:500}
.bigstate{margin-top:6px;font-size:1.5rem;font-weight:700;letter-spacing:-.02em}
.bigstate .grad{background:linear-gradient(100deg,var(--blue),var(--violet) 60%,var(--pink));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}

.card{width:100%;margin-top:42px;border:1px solid var(--line);border-radius:18px;background:var(--glass);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);padding:20px 22px;
  box-shadow:0 18px 60px rgba(0,0,0,.45)}
.card h2{font-family:var(--mono);font-size:.66rem;font-weight:500;letter-spacing:.18em;text-transform:uppercase;
  color:#69719c;margin-bottom:16px}
.row{display:flex;align-items:center;justify-content:space-between;gap:14px}
.row .lbl{font-size:.95rem}
.row .lbl small{display:block;color:var(--dim);font-size:.74rem;margin-top:3px;line-height:1.45}
.keybtn{font-family:var(--mono);font-size:.8rem;letter-spacing:.06em;color:#c7d2ff;cursor:pointer;
  background:linear-gradient(#1b2140,#12162c);border:1px solid rgba(140,160,255,.3);border-bottom-width:3px;
  border-radius:10px;padding:10px 20px;min-width:132px;text-align:center;transition:.25s;white-space:nowrap}
.keybtn:hover{border-color:rgba(150,170,255,.6);box-shadow:0 0 22px rgba(90,110,255,.25);color:#fff}
.keybtn.listening{color:#04050a;background:linear-gradient(90deg,var(--blue),var(--violet));border-color:transparent;
  animation:pulse 1.1s infinite}
.keybtn:focus-visible{outline:2px solid var(--blue);outline-offset:3px}
footer{margin-top:34px;font-family:var(--mono);font-size:.64rem;letter-spacing:.08em;color:#464e78;text-align:center}
footer a{color:#93a5e8;text-decoration:none}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01ms !important;transition-duration:.01ms !important}}
</style>
</head>
<body>
<div class="aurora" aria-hidden="true"><span class="a1"></span><span class="a2"></span></div>

<div class="wrap">
  <header>
    <span class="brand">
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#4D9FFF"/><stop offset="1" stop-color="#8B5CF6"/>
        </linearGradient></defs>
        <circle cx="32" cy="32" r="30" fill="url(#lg)"/>
        <rect x="25" y="13" width="14" height="26" rx="7" fill="#fff"/>
        <path d="M18 34a14 14 0 0 0 28 0" stroke="#fff" stroke-width="5" fill="none" stroke-linecap="round"/>
        <path d="M32 48v6M24 54h16" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
      </svg>
      Speakr
    </span>
    <span class="pill" id="pill"><span class="dot"></span><span id="pilltxt">…</span></span>
  </header>

  <button class="power" id="power" aria-label="Toggle dictation">
    <svg viewBox="0 0 24 24"><path d="M12 3v8"/><path d="M6.2 5.6a8.5 8.5 0 1 0 11.6 0"/></svg>
  </button>
  <div class="bigstate" id="bigstate"><span class="grad">…</span></div>
  <div class="statusline" id="statusline"></div>

  <div class="card">
    <h2>Settings</h2>
    <div class="row">
      <span class="lbl">Push-to-talk key
        <small id="keyhint"></small>
      </span>
      <button class="keybtn" id="keybtn">…</button>
    </div>
  </div>

  <footer><a href="https://speakr.cloud" target="_blank" rel="noopener">speakr.cloud</a> · everything stays on this machine</footer>
</div>
<div class="grain" aria-hidden="true"></div>

<script>
(function(){
"use strict";
var TOKEN = "__TOKEN__";
var power = document.getElementById("power");
var pill = document.getElementById("pill"), pilltxt = document.getElementById("pilltxt");
var bigstate = document.getElementById("bigstate"), statusline = document.getElementById("statusline");
var keybtn = document.getElementById("keybtn"), keyhint = document.getElementById("keyhint");
var capturing = false, state = null;

function keyLabel(k){
  if (!k) return "—";
  return k.replace("cmd","⌘").replace("option","⌥").toUpperCase();
}
function render(){
  if (!state) return;
  power.classList.toggle("on", state.enabled);
  pill.className = "pill " + (!state.enabled ? "off" :
    state.state === "recording" ? "rec" :
    (state.state === "processing" || state.state === "loading") ? "busy" : "");
  pilltxt.textContent = state.enabled ? state.state.toUpperCase() : "OFF";
  bigstate.innerHTML = state.enabled
    ? 'Speakr is <span class="grad">on</span>'
    : 'Speakr is <span style="color:#69719c">off</span>';
  statusline.innerHTML = state.enabled
    ? 'hold <b>' + keyLabel(state.hotkey) + '</b> · speak · release'
    : 'the hotkey is ignored until you switch back on';
  if (!capturing) keybtn.textContent = keyLabel(state.hotkey);
  keyhint.textContent = state.mac
    ? "Modifier keys only: fn, right ⌘, right ⌥, right ⌃, caps lock…"
    : "Click, then press any key. Esc cancels.";
}
function refresh(){
  fetch("/api/state").then(function(r){ return r.json(); }).then(function(s){
    state = s; render();
  }).catch(function(){});
}
function post(path){
  return fetch(path, { method:"POST", headers:{ "X-Speakr-Token": TOKEN } })
    .then(function(r){ return r.json(); });
}
power.addEventListener("click", function(){
  post("/api/toggle").then(function(s){ state = s; render(); });
});
keybtn.addEventListener("click", function(){
  if (capturing) return;
  capturing = true;
  keybtn.classList.add("listening");
  keybtn.textContent = state && state.mac ? "PRESS A MODIFIER…" : "PRESS A KEY…";
  post("/api/capture").then(function(res){
    capturing = false;
    keybtn.classList.remove("listening");
    if (res && res.hotkey && state) state.hotkey = res.hotkey;
    render();
  }).catch(function(){
    capturing = false;
    keybtn.classList.remove("listening");
    render();
  });
});
refresh();
setInterval(function(){ if (!capturing) refresh(); }, 2000);
})();
</script>
</body>
</html>
"""
