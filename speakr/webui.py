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

from __future__ import annotations

import json
import logging
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from speakr import config as cfg_mod

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
        try:
            # Published for duplicate launches (double-clicking the app while
            # it's already running opens this panel instead of doing nothing).
            cfg_mod.PANEL_URL_PATH.write_text(self.url(), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not write %s: %s", cfg_mod.PANEL_URL_PATH, exc)
        log.info("Control panel at %s", self.url())

    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def stop(self):
        try:
            cfg_mod.PANEL_URL_PATH.unlink()
        except OSError:
            pass
        if self._server is not None:
            threading.Thread(target=self._server.shutdown, daemon=True).start()

    # ----- state for the page ----------------------------------------------

    def state(self, authed=False):
        app = self.app
        tray_state = getattr(app.tray, "state", "idle")
        state = tray_state if app.enabled else "disabled"
        hotkey = app.config.get("hotkey")
        out = {
            "enabled": app.enabled,
            "hotkey": hotkey,
            "state": state,
            "status": STATE_LABELS.get(state, state).format(key=hotkey),
            "mac": sys.platform == "darwin",
            "level": getattr(app.recorder, "level", 0.0),
            "words": app.session_words,
            "seq": app.last_seq,
        }
        if authed:
            # Dictated text only ever goes to the panel itself: the token is
            # embedded in the served page, and the custom header forces a CORS
            # preflight (never approved) for anything cross-origin.
            out["last_text"] = app.last_text
            out["last_duration"] = app.last_duration
        return out

    def pulse(self):
        """Tiny fast-poll payload driving the live orb while recording."""
        app = self.app
        tray_state = getattr(app.tray, "state", "idle")
        return {
            "level": getattr(app.recorder, "level", 0.0),
            "state": tray_state if app.enabled else "disabled",
            "seq": app.last_seq,
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
                self._send(200, json.dumps(ui.state(authed=self._authed())))
            elif self.path == "/api/pulse":
                self._send(200, json.dumps(ui.pulse()))
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
<html lang="en" class="boot">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Speakr</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%234D9FFF'/%3E%3Cstop offset='1' stop-color='%238B5CF6'/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx='32' cy='32' r='30' fill='url(%23g)'/%3E%3Crect x='25' y='13' width='14' height='26' rx='7' fill='white'/%3E%3Cpath d='M18 34a14 14 0 0 0 28 0' stroke='white' stroke-width='5' fill='none' stroke-linecap='round'/%3E%3Cpath d='M32 48v6M24 54h16' stroke='white' stroke-width='5' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
:root{
  --bg:#030409; --ink:#eef1fb; --dim:#8a92ad;
  --blue:#4da2ff; --violet:#8b5cf6; --pink:#e879f9; --mint:#5effb0; --red:#ff4d6a; --amber:#ffb84d;
  --line:rgba(140,160,255,.16); --glass:rgba(14,18,36,.55);
  --font:system-ui,-apple-system,'Segoe UI Variable Display','Segoe UI',sans-serif;
  --mono:ui-monospace,'SF Mono','Cascadia Code',Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{overflow-x:hidden}
body{background:var(--bg);color:var(--ink);font-family:var(--font);min-height:100vh;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  display:flex;flex-direction:column;align-items:center}
::selection{background:rgba(139,92,246,.45);color:#fff}
button{font:inherit;color:inherit;background:none;border:0}
a{color:inherit}
button:focus-visible,a:focus-visible{outline:2px solid var(--blue);outline-offset:4px;border-radius:4px}

.srOnly{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* ---------- backdrop: aurora + grain ---------- */
.aurora{position:fixed;inset:-20%;z-index:0;pointer-events:none;filter:blur(74px);opacity:.85;transition:opacity .8s ease}
body.dim-aurora .aurora{opacity:.14}
.aurora span{position:absolute;border-radius:50%;mix-blend-mode:screen}
.aurora .a1{width:78vmax;height:78vmax;left:-20vmax;top:-26vmax;
  background:radial-gradient(circle,rgba(45,90,255,.95) 0%,rgba(45,90,255,.55) 42%,transparent 72%);
  animation:drift1 24s ease-in-out infinite alternate}
.aurora .a2{width:70vmax;height:70vmax;right:-22vmax;bottom:-24vmax;
  background:radial-gradient(circle,rgba(139,92,246,.92) 0%,rgba(139,92,246,.5) 42%,transparent 72%);
  animation:drift2 29s ease-in-out infinite alternate}
@keyframes drift1{to{transform:translate(7vmax,6vmax)}}
@keyframes drift2{to{transform:translate(-6vmax,-7vmax)}}
.grain{position:fixed;inset:0;z-index:30;pointer-events:none;opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23n)'/%3E%3C/svg%3E")}
.vignette{position:fixed;inset:0;z-index:1;pointer-events:none;opacity:0;
  background:radial-gradient(circle at 50% 30%,rgba(255,77,106,.16),transparent 62%)}

/* ---------- layout ---------- */
.wrap{position:relative;z-index:2;width:min(460px,92vw);padding:16px 0 20px;
  display:flex;flex-direction:column;align-items:center}
header{width:100%;display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:1.1rem;letter-spacing:-.02em}
.brand svg{width:27px;height:27px;filter:drop-shadow(0 0 12px rgba(99,132,255,.55))}
.pill{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:.64rem;letter-spacing:.1em;
  color:#9db4ff;border:1px solid var(--line);padding:6px 12px;border-radius:99px;background:rgba(30,45,120,.16)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:#4a5568;transition:background .3s,box-shadow .3s}
.pill.mint .dot{background:var(--mint);box-shadow:0 0 8px var(--mint)}
.pill.rec .dot{background:var(--red);box-shadow:0 0 8px var(--red);animation:dotPulse 1s ease-in-out infinite}
.pill.amber .dot{background:var(--amber);box-shadow:0 0 8px var(--amber)}
.pill.red .dot{background:var(--red);box-shadow:0 0 8px var(--red)}
.pill.gray .dot{background:#4a5568;box-shadow:none}
@keyframes dotPulse{50%{opacity:.3}}

/* ---------- orb ---------- */
.orbwrap{position:relative;width:280px;height:280px;max-width:100%;display:grid;place-items:center}
.orbGlow{position:absolute;width:220px;height:220px;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,rgba(77,162,255,.65) 0%,rgba(139,92,246,.4) 45%,transparent 72%);
  filter:blur(30px);opacity:.3}
#orbCanvas{position:absolute;inset:0;width:280px;height:280px;pointer-events:none;transition:filter .5s}
.orbwrap[data-vstate="off"] #orbCanvas,.orbwrap[data-vstate="down"] #orbCanvas{filter:saturate(.25) brightness(.7)}

.power{position:relative;width:150px;height:150px;border-radius:50%;cursor:pointer;
  background:linear-gradient(#0a0e1e,#0a0e1e) padding-box,linear-gradient(135deg,var(--blue),var(--violet),var(--pink)) border-box;
  border:2px solid transparent;display:grid;place-items:center;
  transform:translateZ(0) scale(1);transition:filter .5s}
.power:active{transform:scale(.96)}
.power::before{content:"";position:absolute;inset:0;border-radius:50%;
  background:
    radial-gradient(circle at 30% 25%, rgba(255,255,255,.5), rgba(255,255,255,0) 40%),
    radial-gradient(circle at 62% 80%, rgba(0,0,0,.55), transparent 62%),
    linear-gradient(135deg,#2563eb,#7c3aed 55%,#d946ef);
  box-shadow:inset 0 -10px 20px rgba(0,0,0,.45),inset 0 3px 5px rgba(255,255,255,.22);
  opacity:0;transition:opacity .45s}
.power.on::before{opacity:1}
.power svg{position:relative;width:56px;height:56px;stroke:#3a4266;fill:none;stroke-width:2.4;
  stroke-linecap:round;transition:stroke .4s}
.power.on svg{stroke:#f5f7ff;
  filter:drop-shadow(0 0 7px rgba(245,247,255,.9)) drop-shadow(0 1px 3px rgba(0,0,0,.4))}
.power.sonar::after{content:"";position:absolute;inset:-14px;border-radius:50%;
  border:1px solid rgba(120,140,255,.35);pointer-events:none;animation:sonarRing 2.4s ease-out infinite}
@keyframes sonarRing{0%{transform:scale(.92);opacity:.7}100%{transform:scale(1.26);opacity:0}}
.power.breathe{animation:breathe 4s ease-in-out infinite}
@keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.022)}}
.power.snap{animation:snapSpring .42s cubic-bezier(.2,1.6,.3,1) 1}
@keyframes snapSpring{0%{transform:scale(1)}55%{transform:scale(1.06)}100%{transform:scale(1)}}
.orbwrap[data-vstate="off"] .power,.orbwrap[data-vstate="down"] .power{filter:saturate(.25) brightness(.7)}
.orbwrap[data-vstate="loading"] .power{filter:brightness(.72)}
.power:focus-visible{outline:2px solid var(--blue);outline-offset:6px}

/* ---------- state word + statusline ---------- */
.bigstate{margin-top:-16px;min-height:2.9rem;display:flex;align-items:center;justify-content:center;position:relative;z-index:2}
.bigstate-text{font-size:clamp(2rem,9vw,2.6rem);font-weight:800;letter-spacing:-.03em;color:#69719c}
.bigstate-text.grad{background:linear-gradient(100deg,var(--blue),var(--violet) 55%,var(--pink));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent}
.statusline{margin-top:2px;min-height:1.3em;font-family:var(--mono);font-size:.78rem;
  color:var(--dim);letter-spacing:.03em;text-align:center}
.statusline b{color:var(--ink);font-weight:600}

/* ---------- glass cards ---------- */
.card{width:100%;border:1px solid var(--line);border-radius:20px;background:var(--glass);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);padding:14px 18px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 24px 60px -18px rgba(0,0,0,.65);position:relative}
.card h2{font-family:var(--mono);font-size:.62rem;font-weight:500;letter-spacing:.2em;
  text-transform:uppercase;color:#69719c;margin-bottom:9px}

.lastcard{margin-top:14px}
.lastcard::before{content:"";position:absolute;inset:-1px;border-radius:20px;padding:1px;
  background:linear-gradient(120deg,var(--blue),var(--violet));
  -webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);
  -webkit-mask-composite:xor;mask-composite:exclude;opacity:0;pointer-events:none}
.lastcard.glow::before{animation:cardGlowFade .9s ease 1}
@keyframes cardGlowFade{0%{opacity:0}30%{opacity:1}100%{opacity:0}}
.lasttextWrap{max-height:8.2em;overflow-y:auto;position:relative}
.lasttextWrap.masked{
  -webkit-mask-image:linear-gradient(to bottom,#000 calc(100% - 22px),transparent 100%);
  mask-image:linear-gradient(to bottom,#000 calc(100% - 22px),transparent 100%)}
.lasttext{font-size:.95rem;line-height:1.5;min-height:2.3em}
.lasttext.empty{color:var(--dim);font-style:italic}
.lasttext .word{display:inline-block;opacity:0;transform:translateY(4px);
  transition:opacity .25s ease,transform .25s ease}
.lasttext .word.in{opacity:1;transform:translateY(0)}
.caret{display:inline-block;width:2px;height:1em;background:var(--blue);vertical-align:-2px;
  margin-left:1px;animation:caretBlink .9s steps(1) infinite}
.caret.hide{display:none}
@keyframes caretBlink{50%{opacity:0}}
.lastmeta{margin-top:10px;font-family:var(--mono);font-size:.68rem;letter-spacing:.06em;
  color:var(--dim);opacity:0;transition:opacity .3s ease}
.lastmeta.show{opacity:1}

.cards2{display:flex;gap:12px;width:100%;margin-top:10px}
.cards2 .card{flex:1;min-width:0;display:flex;flex-direction:column}
@media (max-width:400px){.cards2{flex-direction:column}}

.keycap{align-self:flex-start;font-family:var(--mono);font-size:.82rem;letter-spacing:.06em;
  color:#c7d2ff;cursor:pointer;background:linear-gradient(160deg,#1b2140,#12162c);
  border:1px solid rgba(140,160,255,.3);border-bottom:3px solid rgba(6,8,18,.9);
  border-radius:10px;padding:9px 16px;min-width:104px;text-align:center;
  transition:border-color .25s,box-shadow .25s,color .25s;white-space:nowrap}
.keycap:hover{border-color:rgba(150,170,255,.6);box-shadow:0 0 20px rgba(90,110,255,.22);color:#fff}
.keycap:active{transform:translateY(1px)}
.keycap:focus-visible{outline:2px solid var(--blue);outline-offset:3px}
.keycap.shake,.overlayKeycap.shake{animation:shakeX .35s ease-in-out 1}
@keyframes shakeX{10%,90%{transform:translateX(-6px)}20%,80%{transform:translateX(6px)}
  30%,50%,70%{transform:translateX(-4px)}40%,60%{transform:translateX(4px)}}
.keycap.pop{animation:popKey .28s cubic-bezier(.2,1.6,.3,1) 1}
@keyframes popKey{0%{transform:scale(1)}50%{transform:scale(1.12)}100%{transform:scale(1)}}

.odomWrap{position:relative;margin-top:auto}
.odometer{display:flex;gap:1px}
.odoDigit{height:2.2rem;width:1.15em;overflow:hidden;position:relative}
.odoStrip{display:flex;flex-direction:column;transition:transform .6s cubic-bezier(.2,1,.3,1);
  background:linear-gradient(180deg,var(--blue),var(--violet));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.odoStrip span{height:2.2rem;line-height:2.2rem;font-family:var(--mono);font-size:2rem;
  font-weight:600;text-align:center}
.wordsChip{position:absolute;right:0;top:-4px;font-family:var(--mono);font-size:.72rem;
  color:var(--mint);pointer-events:none;animation:chipRise .95s ease forwards}
@keyframes chipRise{0%{opacity:0;transform:translateY(4px)}15%{opacity:1;transform:translateY(0)}
  75%{opacity:1}100%{opacity:0;transform:translateY(-20px)}}

footer{margin-top:14px;font-family:var(--mono);font-size:.63rem;letter-spacing:.07em;
  color:#464e78;text-align:center}
footer a{color:#93a5e8;text-decoration:none}
footer a:hover{color:#c7d2ff}

/* ---------- hotkey capture theater ---------- */
.captureOverlay{position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:24px;background:rgba(3,4,9,.72);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  opacity:0;pointer-events:none;transition:opacity .3s ease}
.captureOverlay.open{opacity:1;pointer-events:auto}
.overlayLabel{font-family:var(--mono);font-size:.72rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim)}
.overlayKeycap{position:relative;width:140px;height:104px;border-radius:20px;
  background:linear-gradient(160deg,#1b2140,#12162c);
  border:1px solid rgba(140,160,255,.32);border-bottom:4px solid rgba(4,6,14,.9);
  display:flex;align-items:center;justify-content:center;
  transition:transform .15s ease,border-bottom-width .15s ease}
.overlayKeycap::after{content:"";position:absolute;inset:-10px;border-radius:26px;
  border:1px solid rgba(120,140,255,.4);animation:overlayPulse 1.1s ease-out infinite}
@keyframes overlayPulse{0%{transform:scale(.94);opacity:.8}100%{transform:scale(1.12);opacity:0}}
.overlayKeycap.press{transform:translateY(4px);border-bottom-width:0}
.burstRing{position:absolute;inset:-10px;border-radius:26px;border:2px solid rgba(139,92,246,.6);
  opacity:0;pointer-events:none}
.burstRing.show{animation:burstRingAnim .5s ease-out 1}
@keyframes burstRingAnim{0%{transform:scale(.9);opacity:.9}100%{transform:scale(1.7);opacity:0}}
.keytext{display:inline-block;font-family:var(--mono);font-size:1.25rem;letter-spacing:.05em;color:var(--ink)}
.keytext.slam{animation:slamIn .18s cubic-bezier(.2,1.6,.3,1) 1}
@keyframes slamIn{0%{transform:scale(1.5);opacity:0}100%{transform:scale(1);opacity:1}}
.keytext.placeholder{color:#69719c;letter-spacing:.2em;animation:phPulse 1.3s ease-in-out infinite}
@keyframes phPulse{0%,100%{opacity:.22}50%{opacity:.6}}
.overlayHint{font-family:var(--mono);font-size:.68rem;letter-spacing:.08em;color:#464e78}

/* ---------- entrance choreography (once, skipped under reduced motion) ---------- */
html.boot .aurora{opacity:0;animation:auroraIn .6s ease forwards}
html.boot .orbwrap{opacity:0;transform:scale(.6);
  animation:orbIn .5s cubic-bezier(.2,1.6,.3,1) .08s forwards}
html.boot .bigstate-text{opacity:0;transform:translateY(14px);
  animation:riseIn .4s ease .2s forwards}
html.boot .lastcard{opacity:0;transform:translateY(18px);
  animation:cardIn .4s ease .28s forwards}
html.boot .cards2 .keycard{opacity:0;transform:translateY(18px);
  animation:cardIn .4s ease .35s forwards}
html.boot .cards2 .statcard{opacity:0;transform:translateY(18px);
  animation:cardIn .4s ease .42s forwards}
html.boot .pill .dot{opacity:0;animation:dotIn .15s ease .5s forwards}
@keyframes auroraIn{from{opacity:0}to{opacity:.45}}
@keyframes orbIn{from{opacity:0;transform:scale(.6)}to{opacity:1;transform:scale(1)}}
@keyframes riseIn{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes cardIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
@keyframes dotIn{from{opacity:0}to{opacity:1}}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms !important;animation-iteration-count:1 !important;
    transition-duration:.01ms !important;scroll-behavior:auto !important}
  html.boot .aurora,html.boot .orbwrap,html.boot .bigstate-text,html.boot .lastcard,
  html.boot .cards2 .keycard,html.boot .cards2 .statcard,html.boot .pill .dot{
    opacity:1;transform:none;animation:none}
}
</style>
</head>
<body>
<div class="aurora" aria-hidden="true"><span class="a1"></span><span class="a2"></span></div>
<div class="vignette" id="vignette" aria-hidden="true"></div>

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
    <span class="pill gray" id="pill"><span class="dot"></span><span id="pilltxt">&hellip;</span></span>
  </header>

  <div class="orbwrap" id="orbwrap" data-vstate="loading">
    <div class="orbGlow" id="orbGlow" aria-hidden="true"></div>
    <canvas id="orbCanvas" width="280" height="280" aria-hidden="true"></canvas>
    <button class="power" id="power" aria-label="Toggle dictation" aria-pressed="false">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v8"/><path d="M6.2 5.6a8.5 8.5 0 1 0 11.6 0"/></svg>
    </button>
  </div>

  <div class="bigstate"><span class="bigstate-text" id="bigstateText"></span></div>
  <div class="statusline" id="statusline" aria-live="polite"></div>

  <div class="card lastcard" id="lastcard">
    <h2>Last dictation</h2>
    <div class="lasttextWrap" id="lasttextWrap">
      <div class="lasttext empty" id="lasttext" aria-live="polite">your words will appear here &mdash; hold the key and speak</div>
    </div>
    <div class="lastmeta" id="lastmeta"></div>
  </div>

  <div class="cards2">
    <div class="card keycard">
      <h2>Push-to-talk key</h2>
      <button class="keycap" id="keycapBtn" aria-label="Change push-to-talk key">&hellip;</button>
    </div>
    <div class="card statcard">
      <h2>Words this session</h2>
      <div class="odomWrap" id="odomWrap">
        <div class="odometer" id="odometer" aria-hidden="true"></div>
        <span class="srOnly" id="odomSR">0 words this session</span>
      </div>
    </div>
  </div>

  <footer>everything stays on this machine &middot; <a href="https://speakr.cloud" target="_blank" rel="noopener">speakr.cloud</a></footer>
</div>

<div class="captureOverlay" id="captureOverlay" role="dialog" aria-modal="true" aria-label="Capturing push-to-talk key" aria-hidden="true">
  <div class="overlayLabel" id="overlayLabel">PRESS YOUR PUSH-TO-TALK KEY</div>
  <div class="overlayKeycap" id="overlayKeycap">
    <span class="burstRing" id="burstRing" aria-hidden="true"></span>
    <span class="keytext" id="overlayKeyText"></span>
  </div>
  <div class="overlayHint" id="overlayHint">any key &middot; esc cancels</div>
</div>

<div class="grain" aria-hidden="true"></div>

<script>
(function(){
"use strict";
var TOKEN = "__TOKEN__";

/* ---------- element refs ---------- */
var htmlEl = document.documentElement;
var pill = document.getElementById("pill"), pilltxt = document.getElementById("pilltxt");
var orbwrap = document.getElementById("orbwrap");
var orbGlow = document.getElementById("orbGlow");
var canvas = document.getElementById("orbCanvas");
var ctx = canvas.getContext("2d");
var powerBtn = document.getElementById("power");
var bigstateText = document.getElementById("bigstateText");
var statusline = document.getElementById("statusline");
var vignette = document.getElementById("vignette");
var lastcard = document.getElementById("lastcard");
var lasttextWrap = document.getElementById("lasttextWrap");
var lasttext = document.getElementById("lasttext");
var lastmeta = document.getElementById("lastmeta");
var keycapBtn = document.getElementById("keycapBtn");
var odometerEl = document.getElementById("odometer");
var odomWrap = document.getElementById("odomWrap");
var odomSR = document.getElementById("odomSR");
var overlay = document.getElementById("captureOverlay");
var overlayLabel = document.getElementById("overlayLabel");
var overlayKeycapEl = document.getElementById("overlayKeycap");
var overlayKeyText = document.getElementById("overlayKeyText");
var overlayHint = document.getElementById("overlayHint");
var burstRing = document.getElementById("burstRing");

var reducedMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

/* ---------- app + orb state ---------- */
var app = {
  enabled:false, hotkey:null, state:"loading", status:"", mac:false,
  level:0, words:0, seq:null, last_text:"", last_duration:0, down:false
};
var prevVState = null;
var lastSeqSeen = null;
var capturing = false;
var hidden = document.hidden;
var pulseFailCount = 0;
var pulseTimer = null, stateTimer = null;
var pulseIntervalMs = 250;

var orb = { energy:0, peak:0.05, particles:[], rings:[] };

var DPR = Math.max(1, window.devicePixelRatio || 1);
var CSS_SIZE = 280;
var CENTER = CSS_SIZE/2;
var BTN_R = 75;
var INNER_R = BTN_R + 3;
var MAX_LEN = 52;
var BAR_COUNT = 96;
var TAU = Math.PI*2;

/* ================= helpers ================= */
function clamp01(v){ return v<0?0:(v>1?1:v); }

function keyLabel(k, mac){
  if (!k) return "—";
  var lower = String(k).toLowerCase();
  if (lower.indexOf("caps") !== -1) return "CAPS";
  var out = String(k).toUpperCase();
  out = out.replace("COMMAND","CMD").replace("CMD","⌘");
  out = out.replace("OPTION","⌥").replace("ALT","⌥");
  if (mac) out = out.replace("CONTROL","CTRL").replace("CTRL","⌃");
  return out;
}

function computeVState(){
  if (app.down) return "down";
  if (app.state === "disabled") return "off";
  return app.state;
}

function pillTextFor(v){
  switch(v){
    case "idle": return "READY";
    case "recording": return "REC";
    case "processing": return "WORKING";
    case "loading": return "LOADING";
    case "error": return "ERROR";
    case "down": return "OFFLINE";
    default: return "OFF";
  }
}
function pillClassFor(v){
  switch(v){
    case "idle": return "mint";
    case "recording": return "rec";
    case "processing": return "amber";
    case "loading": return "amber";
    case "error": return "red";
    default: return "gray";
  }
}
function bigStateText(v){
  switch(v){
    case "idle": return "Ready.";
    case "recording": return "Listening…";
    case "processing": return "Polishing…";
    case "loading": return "Warming up…";
    case "error": return "Hiccup.";
    case "down": return "Asleep.";
    default: return "Off.";
  }
}
function statuslineTextFor(v){
  switch(v){
    case "recording": return "release to finish";
    case "processing": return "cleaning up your words";
    case "off": return "the hotkey is ignored until you switch back on";
    case "loading": return app.status || "Warming up…";
    case "error": return app.status || "Hiccup.";
    case "down": return "speakr isn't running — reopen from the tray";
    default: return "";
  }
}

/* ================= render (DOM) ================= */
function render(){
  var v = computeVState();
  if (v !== prevVState){
    if (v === "error" && !reducedMotion) spawnErrorFlash();
    prevVState = v;
  }
  orbwrap.setAttribute("data-vstate", v);
  document.body.classList.toggle("dim-aurora", v === "off" || v === "down");

  var isOn = v !== "off" && v !== "down";
  powerBtn.classList.toggle("on", isOn);
  powerBtn.setAttribute("aria-pressed", String(isOn));
  if (!powerBtn.classList.contains("snap")){
    powerBtn.classList.toggle("breathe", v === "idle");
  }
  powerBtn.classList.toggle("sonar", v === "idle");

  pill.className = "pill " + pillClassFor(v);
  pilltxt.textContent = pillTextFor(v);

  bigstateText.textContent = bigStateText(v);
  bigstateText.classList.toggle("grad", isOn);

  if (v === "idle"){
    statusline.textContent = "";
    var hold = document.createTextNode("hold ");
    var b = document.createElement("b");
    b.textContent = keyLabel(app.hotkey, app.mac);
    var rest = document.createTextNode(" · speak · release");
    statusline.appendChild(hold); statusline.appendChild(b); statusline.appendChild(rest);
  } else {
    statusline.textContent = statuslineTextFor(v);
  }

  if (!capturing) keycapBtn.textContent = keyLabel(app.hotkey, app.mac);

  if (reducedMotion) drawFrame(performance.now());
}

/* ================= canvas: orb ================= */
function setupCanvas(){
  canvas.style.width = CSS_SIZE + "px";
  canvas.style.height = CSS_SIZE + "px";
  canvas.width = CSS_SIZE * DPR;
  canvas.height = CSS_SIZE * DPR;
  ctx.setTransform(DPR,0,0,DPR,0,0);
}

function drawBar(i, len, alpha, c0, c1){
  var angle = (i/BAR_COUNT)*Math.PI*2 - Math.PI/2;
  var cos = Math.cos(angle), sin = Math.sin(angle);
  var x0 = CENTER + cos*INNER_R, y0 = CENTER + sin*INNER_R;
  var x1 = CENTER + cos*(INNER_R+len), y1 = CENTER + sin*(INNER_R+len);
  var grad = ctx.createLinearGradient(x0,y0,x1,y1);
  grad.addColorStop(0, c0);
  grad.addColorStop(1, c1);
  ctx.strokeStyle = grad;
  ctx.lineCap = "round";
  ctx.globalAlpha = alpha*0.32; ctx.lineWidth = 4.5;
  ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke();
  ctx.globalAlpha = alpha; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke();
  ctx.globalAlpha = 1;
}

/* Spatial frequencies below are chosen as INTEGER cycle counts around the
   BAR_COUNT-bar ring (i.e. i*F completes a whole number of 2*PI turns from
   i=0 to i=BAR_COUNT). That guarantees sin(i*F + phase) wraps seamlessly —
   no discontinuity/spike between bar BAR_COUNT-1 and bar 0 (the 12 o'clock
   seam). The previous 0.35 / 0.11 / 0.3 constants were NOT integer multiples
   of TAU/BAR_COUNT, which produced a visible spike at the wrap point. */
function drawIdleRing(t, calm){
  if (calm){
    // reduced motion: perfectly even ring, no per-bar variation
    for (var i=0;i<BAR_COUNT;i++) drawBar(i, 2.75, 0.5, "#2d5aff", "#8b5cf6");
    return;
  }
  var F = 6*TAU/BAR_COUNT;
  for (var j=0;j<BAR_COUNT;j++){
    var shimmer = 0.5 + 0.5*Math.sin(j*F - t*0.6);
    var len = 2 + shimmer*1.5;
    drawBar(j, len, 0.5, "#2d5aff", "#8b5cf6");
  }
}
function drawEnergyRing(t, energy, calm){
  if (calm){
    // reduced motion: all bars the same length, proportional to energy only
    var flatLen = 2 + energy*MAX_LEN;
    var flatAlpha = 0.45 + energy*0.5;
    for (var i=0;i<BAR_COUNT;i++) drawBar(i, flatLen, flatAlpha, "#4da2ff", "#e879f9");
    return;
  }
  // F1: finer, faster texture (more cycles -> reads as grain, not lobes).
  // F2: the "slow" companion sine — kept at a higher spatial frequency than
  // the old 0.11 constant (was ~1.7 cycles, cause of the pentagon lobing)
  // and given less amplitude weight, so it adds subtle life without
  // deforming the ring's silhouette into a polygon.
  var F1 = 5*TAU/BAR_COUNT;
  var F2 = 3*TAU/BAR_COUNT;
  for (var j=0;j<BAR_COUNT;j++){
    var v1 = Math.sin(j*F1 + t*2.1);
    var v2 = Math.sin(j*F2 - t*1.3);
    var variation = v1*0.7 + v2*0.3;
    var w = 1 + variation*energy*0.3;
    var len = 2 + energy*MAX_LEN*w;
    if (len < 2) len = 2;
    var alpha = 0.45 + energy*0.5;
    drawBar(j, len, alpha, "#4da2ff", "#e879f9");
  }
}

/* Chasing-comet arc for processing/loading: one bright, glowing arc stroked
   directly on the ring's circumference (not radiating bars), so it reads
   unmistakably as motion instead of a handful of dim spokes. Bars are not
   drawn at all in this state — no idle-dot ghosting underneath. */
function drawComet(t, revPerSec, arcDeg, rgbHead, rgbTail, maxAlpha, radius, coreWidth, glowWidth){
  var period = 1/revPerSec;
  var frac = (t % period) / period;
  if (frac < 0) frac += 1;
  var headAngle = -Math.PI/2 + frac*TAU;
  var arcRad = arcDeg*Math.PI/180;
  var startAngle = headAngle - arcRad;
  var arcFrac = arcRad/TAU;

  var grad;
  if (typeof ctx.createConicGradient === "function"){
    /* The round line caps extend past both arc ends, where a conic gradient
       wraps around — without an explicit fade back to transparent after the
       head, the tail cap samples the wrapped-around head color and paints a
       detached bright dot behind the comet. capFrac covers the cap radius. */
    var capFrac = glowWidth / (TAU * radius);
    grad = ctx.createConicGradient(startAngle, CENTER, CENTER);
    grad.addColorStop(0, "rgba(" + rgbTail + ",0)");
    grad.addColorStop(Math.min(1, arcFrac*0.45), "rgba(" + rgbTail + "," + (maxAlpha*0.4) + ")");
    grad.addColorStop(Math.min(1, arcFrac), "rgba(" + rgbHead + "," + maxAlpha + ")");
    grad.addColorStop(Math.min(1, arcFrac + capFrac), "rgba(" + rgbHead + ",0)");
    grad.addColorStop(1, "rgba(" + rgbTail + ",0)");
  } else {
    grad = "rgba(" + rgbHead + "," + maxAlpha + ")";
  }

  ctx.save();
  ctx.lineCap = "round";
  ctx.shadowBlur = 20;
  ctx.shadowColor = "rgba(" + rgbHead + ",0.9)";
  ctx.strokeStyle = grad;
  ctx.lineWidth = glowWidth;
  ctx.globalAlpha = 0.55;
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, radius, startAngle, headAngle);
  ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.lineWidth = coreWidth;
  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, radius, startAngle, headAngle);
  ctx.stroke();
  ctx.restore();
}
function drawErrorRing(){
  for (var i=0;i<BAR_COUNT;i++){
    drawBar(i, 2, 0.4, "#ff4d6a", "#ff4d6a");
  }
}
function drawDots(){
  for (var i=0;i<BAR_COUNT;i++){
    drawBar(i, 1.5, 0.16, "#69719c", "#69719c");
  }
}

function drawRings(now){
  for (var i=orb.rings.length-1; i>=0; i--){
    var r = orb.rings[i];
    var p = (now - r.start)/r.duration;
    if (p >= 1){ orb.rings.splice(i,1); continue; }
    var rad = INNER_R + (CENTER - INNER_R)*p;
    var alpha = (1-p)*0.8;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, rad, 0, Math.PI*2);
    ctx.strokeStyle = "rgba(" + r.rgb + "," + alpha + ")";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}
function drawParticles(now){
  for (var i=orb.particles.length-1; i>=0; i--){
    var pt = orb.particles[i];
    var p = (now - pt.start)/pt.duration;
    if (p >= 1){ orb.particles.splice(i,1); continue; }
    var r = BTN_R + pt.dist*p;
    var x = CENTER + Math.cos(pt.angle)*r;
    var y = CENTER + Math.sin(pt.angle)*r;
    ctx.globalAlpha = 1-p;
    ctx.fillStyle = pt.color;
    ctx.beginPath();
    ctx.arc(x, y, 2.2, 0, Math.PI*2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
}

var PARTICLE_COLORS = ["#4da2ff","#8b5cf6","#e879f9","#5effb0"];
function spawnSnap(){
  var now = performance.now();
  orb.rings.push({ start: now, duration: 650, rgb: "139,92,246" });
  var n = 10 + Math.floor(Math.random()*5);
  for (var i=0;i<n;i++){
    orb.particles.push({
      angle: Math.random()*Math.PI*2,
      dist: 34 + Math.random()*36,
      start: now,
      duration: 550 + Math.random()*120,
      color: PARTICLE_COLORS[Math.floor(Math.random()*PARTICLE_COLORS.length)]
    });
  }
  powerBtn.classList.remove("breathe");
  powerBtn.classList.remove("snap");
  void powerBtn.offsetWidth;
  powerBtn.classList.add("snap");
  powerBtn.addEventListener("animationend", onSnapEnd, { once:true });
}
function onSnapEnd(){
  powerBtn.classList.remove("snap");
  if (computeVState() === "idle") powerBtn.classList.add("breathe");
}
function spawnErrorFlash(){
  orb.rings.push({ start: performance.now(), duration: 480, rgb: "255,77,106" });
}

function glowOpacityFor(v, energy){
  switch(v){
    case "idle": return 0.32;
    case "recording": return 0.32 + energy*0.55;
    case "processing": return 0.4;
    case "loading": return 0.18;
    case "error": return 0.28;
    default: return 0.04;
  }
}

function drawFrame(tsMs){
  var t = tsMs/1000;
  var v = computeVState();

  var rawLevel = app.level || 0;
  var gated = rawLevel < 0.04 ? 0 : rawLevel;
  orb.peak = Math.max(orb.peak*0.995, gated, 0.05);
  var norm = clamp01(gated/orb.peak);
  var target = (v === "recording") ? norm : 0;
  orb.energy += (target - orb.energy)*0.25;
  if (orb.energy < 0.0006) orb.energy = 0;

  ctx.clearRect(0,0,CSS_SIZE,CSS_SIZE);

  var cometR = INNER_R + MAX_LEN*0.34;
  switch(v){
    case "idle": drawIdleRing(t, reducedMotion); break;
    case "recording": drawEnergyRing(t, orb.energy, reducedMotion); break;
    case "processing": drawComet(t, 1.2, 80, "232,121,249", "139,92,246", 0.95, cometR, 8, 22); break;
    case "loading": drawComet(t, 0.3, 70, "125,180,255", "45,90,255", 0.42, cometR, 7, 18); break;
    case "error": drawErrorRing(); break;
    default: drawDots(); break;
  }
  drawRings(tsMs);
  drawParticles(tsMs);

  orbGlow.style.opacity = String(glowOpacityFor(v, orb.energy));
  vignette.style.opacity = String(v === "recording" ? orb.energy*0.12 : 0);
}

var rafId = null;
function loop(ts){
  drawFrame(ts);
  rafId = requestAnimationFrame(loop);
}
function startLoop(){
  if (rafId === null && !reducedMotion) rafId = requestAnimationFrame(loop);
}
function stopLoop(){
  if (rafId !== null){ cancelAnimationFrame(rafId); rafId = null; }
}

/* ================= last dictation type-on ================= */
function updateFadeMask(){
  // Only mask when the text genuinely overflows the box by a meaningful
  // amount (~8px+ = roughly a third of a line) — sub-pixel/rounding
  // differences between scrollHeight and clientHeight must never trip this,
  // or a normal 4-line dictation gets its last line dimmed for no reason.
  var overflowing = (lasttextWrap.scrollHeight - lasttextWrap.clientHeight) > 8;
  lasttextWrap.classList.toggle("masked", overflowing);
}

function setLastDictationInstant(text, duration){
  lasttext.innerHTML = "";
  if (!text){
    lasttext.classList.add("empty");
    lasttext.textContent = "your words will appear here — hold the key and speak";
    lastmeta.textContent = "";
    lastmeta.classList.remove("show");
    updateFadeMask();
    return;
  }
  lasttext.classList.remove("empty");
  var words = text.trim().split(/\s+/);
  for (var i=0;i<words.length;i++){
    var span = document.createElement("span");
    span.className = "word in";
    span.textContent = words[i] + (i < words.length-1 ? " " : "");
    lasttext.appendChild(span);
  }
  lastmeta.textContent = words.length + " word" + (words.length===1?"":"s") + " · " + (duration||0).toFixed(1) + "s";
  lastmeta.classList.add("show");
  updateFadeMask();
}

function cardGlow(el){
  el.classList.remove("glow");
  void el.offsetWidth;
  el.classList.add("glow");
}

function typeOnLastDictation(text, duration){
  cardGlow(lastcard);
  lasttext.classList.remove("empty");
  lasttext.innerHTML = "";
  lastmeta.textContent = "";
  lastmeta.classList.remove("show");

  var words = (text || "").trim().length ? text.trim().split(/\s+/) : [];
  var caret = document.createElement("span");
  caret.className = "caret";
  var frag = document.createDocumentFragment();
  var spans = [];
  for (var i=0;i<words.length;i++){
    var span = document.createElement("span");
    span.className = "word";
    span.textContent = words[i] + (i < words.length-1 ? " " : "");
    frag.appendChild(span);
    spans.push(span);
  }
  lasttext.appendChild(frag);
  lasttext.appendChild(caret);
  updateFadeMask();

  if (words.length === 0){
    caret.classList.add("hide");
    finalizeMeta(0, duration);
    return;
  }

  var maxTicks = Math.max(1, Math.floor(1600/30));
  var groupSize = Math.max(1, Math.ceil(words.length/maxTicks));
  var ticks = Math.ceil(words.length/groupSize);

  var revealTick = function(g){
    var start = g*groupSize, end = Math.min(words.length, start+groupSize);
    for (var k=start; k<end; k++) spans[k].classList.add("in");
    if (g === ticks-1){
      setTimeout(function(){
        caret.classList.add("hide");
        finalizeMeta(words.length, duration);
      }, 140);
    }
  };
  for (var g=0; g<ticks; g++){
    setTimeout((function(gg){ return function(){ revealTick(gg); }; })(g), g*30);
  }
}
function finalizeMeta(n, dur){
  lastmeta.textContent = n + " word" + (n===1?"":"s") + " · " + (typeof dur === "number" ? dur.toFixed(1) : "0.0") + "s";
  lastmeta.classList.add("show");
  updateFadeMask();
}

/* ================= words odometer ================= */
var odoDigits = [];
function buildDigit(){
  var col = document.createElement("span");
  col.className = "odoDigit";
  var strip = document.createElement("span");
  strip.className = "odoStrip";
  for (var d=0; d<10; d++){
    var s = document.createElement("span");
    s.textContent = String(d);
    strip.appendChild(s);
  }
  col.appendChild(strip);
  return { col: col, strip: strip };
}
function renderOdometer(n, animate){
  var str = String(Math.max(0, n||0));
  while (odoDigits.length < str.length){
    var nd = buildDigit();
    odometerEl.insertBefore(nd.col, odometerEl.firstChild);
    odoDigits.unshift(nd);
  }
  var pad = odoDigits.length - str.length;
  for (var i=0;i<odoDigits.length;i++){
    var ch = i < pad ? "0" : str[i-pad];
    var val = parseInt(ch, 10);
    var entry = odoDigits[i];
    if (!animate){
      entry.strip.style.transition = "none";
      entry.strip.style.transform = "translateY(-" + (val*10) + "%)";
      void entry.strip.offsetWidth;
      entry.strip.style.transition = "";
    } else {
      entry.strip.style.transform = "translateY(-" + (val*10) + "%)";
    }
  }
  odomSR.textContent = n + " words this session";
}
function spawnWordsChip(n){
  if (reducedMotion || n <= 0) return;
  var chip = document.createElement("span");
  chip.className = "wordsChip";
  chip.textContent = "+" + n;
  odomWrap.appendChild(chip);
  setTimeout(function(){ if (chip.parentNode) chip.parentNode.removeChild(chip); }, 980);
}
function setWordsInstant(n){ renderOdometer(n, false); }
function setWords(n){
  var prev = app.words || 0;
  renderOdometer(n, true);
  if (n > prev) spawnWordsChip(n-prev);
}

/* ================= hotkey capture theater ================= */
function shakeSettingsKeycap(){
  keycapBtn.classList.remove("shake");
  void keycapBtn.offsetWidth;
  keycapBtn.classList.add("shake");
  setTimeout(function(){ keycapBtn.classList.remove("shake"); }, 380);
}
function settingsKeycapPop(){
  keycapBtn.classList.remove("pop");
  void keycapBtn.offsetWidth;
  keycapBtn.classList.add("pop");
  setTimeout(function(){ keycapBtn.classList.remove("pop"); }, 320);
}
function shakeOverlayKeycap(){
  overlayKeycapEl.classList.remove("shake");
  void overlayKeycapEl.offsetWidth;
  overlayKeycapEl.classList.add("shake");
}
function slamOverlayKeycap(hotkeyStr){
  overlayKeyText.classList.remove("placeholder");
  overlayKeyText.textContent = keyLabel(hotkeyStr, app.mac);
  overlayKeyText.classList.remove("slam");
  void overlayKeyText.offsetWidth;
  overlayKeyText.classList.add("slam");
  overlayKeycapEl.classList.add("press");
  burstRing.classList.remove("show");
  void burstRing.offsetWidth;
  burstRing.classList.add("show");
  setTimeout(function(){ overlayKeycapEl.classList.remove("press"); }, 140);
}
function closeOverlay(){
  capturing = false;
  overlay.classList.remove("open");
  overlay.setAttribute("aria-hidden", "true");
  render();
}
function openCaptureFlow(){
  if (capturing) return;
  capturing = true;
  overlayKeycapEl.classList.remove("shake","press");
  overlayKeyText.classList.remove("slam");
  burstRing.classList.remove("show");
  overlayKeyText.textContent = "···";
  overlayKeyText.classList.add("placeholder");
  overlayLabel.textContent = app.mac ? "PRESS A MODIFIER KEY" : "PRESS YOUR PUSH-TO-TALK KEY";
  overlayHint.textContent = app.mac ? "fn · right ⌘ · right ⌥ · right ⌃ · caps lock" : "any key · esc cancels";
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");

  postCapture().then(function(res){
    if (res.status === 409){
      capturing = false;
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      shakeSettingsKeycap();
      return;
    }
    if (!capturing) return;
    if (res.data && res.data.ok && res.data.hotkey){
      app.hotkey = res.data.hotkey;
      render();
      slamOverlayKeycap(res.data.hotkey);
      setTimeout(function(){
        closeOverlay();
        settingsKeycapPop();
      }, 500);
    } else {
      shakeOverlayKeycap();
      setTimeout(closeOverlay, 400);
    }
  }).catch(function(){
    if (!capturing) return;
    shakeOverlayKeycap();
    setTimeout(closeOverlay, 400);
  });
}

/* ================= network ================= */
function getPulse(){
  return fetch("/api/pulse").then(function(r){ return r.json(); });
}
function getState(){
  return fetch("/api/state", { headers: { "X-Speakr-Token": TOKEN } }).then(function(r){ return r.json(); });
}
function postToggle(){
  return fetch("/api/toggle", { method:"POST", headers:{ "X-Speakr-Token": TOKEN } }).then(function(r){ return r.json(); });
}
function postCapture(){
  return fetch("/api/capture", { method:"POST", headers:{ "X-Speakr-Token": TOKEN } }).then(function(r){
    var status = r.status;
    return r.json().catch(function(){ return {}; }).then(function(data){ return { status:status, data:data }; });
  });
}

function applyState(s){
  if (!s) return;
  var firstLoad = (lastSeqSeen === null);
  app.enabled = !!s.enabled;
  app.hotkey = s.hotkey;
  app.state = s.state;
  app.status = s.status || "";
  app.mac = !!s.mac;
  if (typeof s.level === "number") app.level = s.level;
  if (typeof s.last_text === "string") app.last_text = s.last_text;
  if (typeof s.last_duration === "number") app.last_duration = s.last_duration;

  var newSeq = (typeof s.seq === "number") ? s.seq : null;
  var newWords = (typeof s.words === "number") ? s.words : app.words;

  render();

  if (firstLoad){
    setLastDictationInstant(app.last_text, app.last_duration);
    setWordsInstant(newWords);
    if (newSeq !== null) lastSeqSeen = newSeq;
  } else {
    // seq only ever increases for a genuine new dictation; guard against it
    // going backwards/resetting (e.g. a server restart) so we never wipe a
    // real transcript back to the empty state or "animate" an empty one.
    if (newSeq !== null && newSeq > lastSeqSeen && app.last_text){
      if (reducedMotion){
        setLastDictationInstant(app.last_text, app.last_duration);
      } else {
        spawnSnap();
        setTimeout(function(){ typeOnLastDictation(app.last_text, app.last_duration); }, 150);
      }
    }
    if (newSeq !== null && newSeq > lastSeqSeen) lastSeqSeen = newSeq;
    setWords(newWords);
  }
  app.words = newWords;
}

function fetchStateNow(){
  if (capturing) return Promise.resolve();
  return getState().then(applyState).catch(function(){});
}

function pollPulse(){
  if (document.hidden) return;
  getPulse().then(function(p){
    pulseFailCount = 0;
    var wasDown = app.down;
    app.down = false;
    var stateChanged = p.state !== app.state;
    var seqChanged = (lastSeqSeen !== null) && (typeof p.seq === "number") && p.seq > lastSeqSeen;
    if (typeof p.level === "number") app.level = p.level;
    if (typeof p.state === "string") app.state = p.state;
    render();
    if (wasDown || ((stateChanged || seqChanged) && !capturing)) fetchStateNow();
    pulseIntervalMs = (p.state === "recording" || p.state === "processing") ? 90 : 250;
  }).catch(function(){
    pulseFailCount++;
    if (pulseFailCount >= 4 && !app.down){
      app.down = true;
      render();
    }
  }).then(function(){
    if (!document.hidden) pulseTimer = setTimeout(pollPulse, pulseIntervalMs);
  });
}
function scheduleState(){
  if (document.hidden) return;
  stateTimer = setTimeout(function(){
    fetchStateNow().then(scheduleState);
  }, 2000);
}

/* ================= wiring ================= */
function bindUI(){
  powerBtn.addEventListener("click", function(){
    postToggle().then(applyState).catch(function(){});
  });
  keycapBtn.addEventListener("click", function(){
    openCaptureFlow();
  });
  overlay.addEventListener("click", function(e){
    if (e.target === overlay) closeOverlay();
  });
  document.addEventListener("visibilitychange", function(){
    hidden = document.hidden;
    if (hidden){
      stopLoop();
      if (pulseTimer){ clearTimeout(pulseTimer); pulseTimer = null; }
      if (stateTimer){ clearTimeout(stateTimer); stateTimer = null; }
    } else {
      startLoop();
      pollPulse();
      fetchStateNow().then(scheduleState);
    }
  });
}

function init(){
  setupCanvas();
  bindUI();
  render();
  fetchStateNow().then(scheduleState);
  pollPulse();
  startLoop();
  setTimeout(function(){ htmlEl.classList.remove("boot"); }, 900);
}
init();
})();
</script>
</body>
</html>
"""
