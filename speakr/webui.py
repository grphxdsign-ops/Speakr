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
  --bg:#05060a; --ink:#e8ecfa; --dim:#78829f; --silk:#3d465f;
  --hr0:rgba(160,175,215,.10); --hr1:rgba(160,175,215,.18);
  --blue:#4da2ff; --violet:#8b5cf6; --pink:#e879f9; --hot:#ff3d00; --mint:#5effb0; --amber:#ffb84d;
  --mono:ui-monospace,'SF Mono','Cascadia Code',Consolas,monospace;
  --sans:system-ui,-apple-system,'Segoe UI Variable Display','Segoe UI',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
::selection{background:rgba(139,92,246,.4);color:#fff}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
a{color:inherit;text-decoration:none}
button:focus-visible,a:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.srOnly{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* ---- surface texture ---- */
.grain{position:fixed;inset:0;z-index:45;pointer-events:none;opacity:.04;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23n)'/%3E%3C/svg%3E")}
.scan{position:fixed;inset:0;z-index:44;pointer-events:none;
  background:repeating-linear-gradient(to bottom,rgba(255,255,255,.03) 0px,rgba(255,255,255,.03) 1px,transparent 1px,transparent 3px)}

/* ---- corner silkscreen legends ---- */
.legend{position:fixed;z-index:46;font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;color:var(--silk);
  pointer-events:none;opacity:0;transition:opacity .25s ease}
.legend.in{opacity:1}
.legend.tl{top:6px;left:10px}
.legend.tr{top:6px;right:10px}
.legend.bl{bottom:6px;left:10px}
.legend.br{bottom:6px;right:10px;font-variant-numeric:tabular-nums}

/* ---- chassis grid ---- */
.chassis{position:relative;z-index:1;height:100vh;width:100vw;display:grid;
  grid-template-rows:56px minmax(160px,34vh) 120px 96px minmax(120px,1fr) 34px;background:var(--bg)}
.chassis[data-vstate="disabled"],.chassis[data-vstate="down"]{--ink:rgba(232,236,250,.55)}
.rail{position:relative;border-bottom:1px solid transparent;transition:border-color .15s ease}
html:not(.boot) .rail{border-bottom-color:var(--hr1)}
.bottomrail{border-bottom:0}
@media (max-height:600px){
  .chassis{grid-template-rows:56px minmax(110px,22vh) 80px 96px minmax(90px,1fr) 34px}
}

/* ---- top rail ---- */
.toprail{display:flex;align-items:center;justify-content:space-between;padding:0 16px}
.brandplate{display:flex;align-items:center;gap:10px}
.micbox{width:30px;height:30px;border:1px solid var(--hr1);border-radius:3px;display:grid;place-items:center;color:var(--ink);flex:none}
.micbox svg{width:15px;height:15px}
.brandword{font-weight:800;font-size:1rem;letter-spacing:-.01em;color:var(--ink)}
.lampcluster{display:flex;align-items:center;gap:9px}
.lamp{width:10px;height:10px;border-radius:50%;background:#1c2130;box-shadow:inset 0 1px 2px rgba(0,0,0,.6);flex:none}
.lamp.blink{animation:lampBlink .28s steps(1) 2}
@keyframes lampBlink{0%,100%{opacity:1}50%{opacity:.12}}
.lampcode{font-family:var(--mono);font-size:.68rem;letter-spacing:.12em;color:var(--dim);min-width:3.4em}

/* ---- state stage ---- */
.statestage{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:10px;padding:0 12px;overflow:hidden;text-align:center}
.statestage:active .stateword{transform:translateY(1px) scale(var(--fit,1))}
.stateword{font-family:var(--sans);font-weight:400;font-size:clamp(3.2rem,13vw,7rem);line-height:1;
  color:var(--ink);white-space:nowrap;display:inline-block;transform-origin:center;user-select:none}
.stateword .ch{display:inline-block;font-weight:inherit}
.stateword.outline{color:transparent;-webkit-text-stroke:1px var(--dim)}
.stateword.flash{color:var(--hot)!important}
.stateword.stamp{animation:stamp .22s cubic-bezier(.2,1.6,.3,1)}
@keyframes stamp{0%{transform:scale(1.02)}100%{transform:scale(1)}}
.statehint{font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;color:var(--dim)}

/* ---- scope lane ---- */
.scopelane{overflow:hidden}
.scopelegend{position:absolute;top:7px;right:12px;font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;color:var(--silk);z-index:2}
#scopeCanvas{position:absolute;inset:0;width:100%;height:100%;display:block;
  -webkit-mask-image:linear-gradient(to right,transparent 0,#000 32px);mask-image:linear-gradient(to right,transparent 0,#000 32px)}

/* ---- instrument rail ---- */
.instrumentrail{display:grid;grid-template-columns:1.3fr 1fr 1fr}
.izone{position:relative;padding:10px 16px;display:flex;flex-direction:column;justify-content:center;gap:6px;border-left:1px solid var(--hr0)}
.izone:first-child{border-left:0}
.ilabel{font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;color:var(--silk);text-transform:uppercase}
.ladder{display:flex;gap:3px;align-items:stretch;height:14px}
.seg{flex:1;border-radius:1px;background:#161a26;transition:background-color .04s linear,box-shadow .04s linear}
.dbread{font-family:var(--mono);font-size:.72rem;color:var(--dim);letter-spacing:.03em;font-variant-numeric:tabular-nums}
.odomrow{display:flex;align-items:baseline;gap:8px}
.odometer{display:flex;gap:2px}
.odocell{width:1.05em;height:1.6rem;border:1px solid var(--hr1);border-radius:2px;overflow:hidden;position:relative;background:#0a0c14}
.odocell::after{content:"";position:absolute;left:0;right:0;top:50%;height:1px;background:var(--hr0)}
.odostrip{display:flex;flex-direction:column;transition:transform .6s cubic-bezier(.2,1,.3,1)}
.odostrip span{height:1.6rem;line-height:1.6rem;font-family:var(--mono);font-size:1.05rem;text-align:center;color:var(--ink)}
.chip{width:34px;flex:none;font-family:var(--mono);font-size:.68rem;color:var(--ink);opacity:0}
.chip.show{animation:chipRise .9s ease forwards}
@keyframes chipRise{0%{opacity:0;transform:translateY(3px)}15%{opacity:1;transform:translateY(0)}75%{opacity:1}100%{opacity:0;transform:translateY(-12px)}}
.keycap{align-self:flex-start;font-family:var(--mono);font-size:.78rem;letter-spacing:.05em;color:var(--ink);
  background:#0d0f18;border:1px solid var(--hr1);border-bottom:2px solid rgba(4,5,10,.9);border-radius:4px;
  padding:7px 14px;min-width:88px;text-align:center;transition:transform .1s,border-bottom-width .1s}
.keycap:active{transform:translateY(2px);border-bottom-width:0}
.keycap.shake{animation:shakeX .3s ease-in-out}
@keyframes shakeX{20%,80%{transform:translateX(-4px)}40%,60%{transform:translateX(4px)}}
.hint{position:absolute;left:16px;bottom:6px;font-family:var(--mono);font-size:.62rem;color:var(--dim);opacity:0;transition:opacity .12s}
.iptt:hover .hint,.iptt:focus-within .hint{opacity:1}

/* ---- transcript log ---- */
.translog{padding:10px 16px;display:flex;flex-direction:column;gap:6px;overflow:hidden}
/* The bar element spans the FULL width of the REC.LOG zone's top hairline;
   it wipes in left-to-right (scaleX from a left origin), so any mid-
   animation frame shows a lit run growing from the left edge rather than a
   narrow comet confined to the middle column. */
.sweepbar{position:absolute;top:-1px;left:0;width:100%;height:2px;opacity:0;pointer-events:none;
  transform:scaleX(0);transform-origin:left center}
.sweepbar.run{animation:sweep .3s ease-out}
@keyframes sweep{0%{transform:scaleX(0);opacity:1}70%{transform:scaleX(1);opacity:1}100%{transform:scaleX(1);opacity:0}}
.logwrap{max-height:calc(1.35rem*6);overflow-y:auto;position:relative}
.logwrap.masked{-webkit-mask-image:linear-gradient(to bottom,transparent 0,#000 14px);mask-image:linear-gradient(to bottom,transparent 0,#000 14px)}
.logtext{font-family:var(--mono);font-size:.9rem;line-height:1.35rem;color:var(--ink);white-space:pre-wrap;word-break:break-word}
.logtext.empty{color:var(--dim)}
.cursor{display:inline-block;width:.55em;background:var(--ink);animation:blink 1s steps(1) infinite}
.cursor.hide{display:none}
@keyframes blink{50%{opacity:0}}
.logmeta{font-family:var(--mono);font-size:.68rem;color:var(--dim);letter-spacing:.05em;min-height:1em}
.logmeta .take{display:inline-block}
.logmeta .take.snap{animation:takeSnap .18s ease-out}
@keyframes takeSnap{0%{transform:scale(1.15)}100%{transform:scale(1)}}

/* ---- bottom rail ---- */
.bottomrail{display:flex;align-items:center;justify-content:space-between;padding:0 16px;
  font-family:var(--mono);font-size:.62rem;letter-spacing:.07em;color:var(--dim)}
.bottomrail a{border-bottom:1px solid transparent}
.bottomrail a:hover{border-bottom-color:var(--dim)}

/* ---- capture theater ---- */
.captureOverlay{position:fixed;inset:0;z-index:60;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:22px;background:rgba(5,6,10,.985);opacity:0;pointer-events:none;transition:opacity .25s ease}
.captureOverlay.open{opacity:1;pointer-events:auto}
.overlegend{font-family:var(--mono);font-size:.68rem;letter-spacing:.2em;color:var(--dim)}
.overkeycap{position:relative;width:220px;height:150px;border:1px solid var(--hr1);border-bottom:3px solid rgba(4,5,10,.9);
  border-radius:4px;background:#0d0f18;display:flex;align-items:center;justify-content:center;
  transition:transform .1s,border-bottom-width .1s,border-color .15s}
.overkeycap.press{transform:translateY(3px);border-bottom-width:0}
.overkeycap.shake{animation:shakeX .3s ease-in-out}
.overkeycap.flash{border-color:var(--hot)}
.keytext{font-family:var(--mono);font-size:1.6rem;letter-spacing:.06em;color:var(--ink)}
.keytext.ph{color:var(--dim);animation:phPulse 1.2s ease-in-out infinite}
@keyframes phPulse{0%,100%{opacity:.25}50%{opacity:.7}}
.keytext.slam{animation:slam .16s cubic-bezier(.2,1.6,.3,1)}
@keyframes slam{0%{transform:scale(1.4);opacity:0}100%{transform:scale(1);opacity:1}}
.overhint{font-family:var(--mono);font-size:.66rem;letter-spacing:.06em;color:var(--silk)}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
}
</style>
</head>
<body>
<div class="scan" aria-hidden="true"></div>

<span class="legend tl" id="legTl">SPEAKR VOICE UNIT</span>
<span class="legend tr" id="legTr">LOCAL-ONLY // NO CLOUD</span>
<span class="legend bl" id="legBl">SN 43117</span>
<span class="legend br" id="legBr">UPTIME 00:00:00</span>

<div class="chassis" id="chassis" data-vstate="loading">
  <header class="rail toprail">
    <div class="brandplate">
      <span class="micbox" aria-hidden="true">
        <svg viewBox="0 0 64 64" aria-hidden="true">
          <rect x="25" y="13" width="14" height="26" rx="7" fill="currentColor"/>
          <path d="M18 34a14 14 0 0 0 28 0" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round"/>
          <path d="M32 48v6M24 54h16" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
        </svg>
      </span>
      <span class="brandword">SPEAKR</span>
    </div>
    <div class="lampcluster">
      <span class="lamp" id="lamp" aria-hidden="true"></span>
      <span class="lampcode" id="lampcode">BOOT</span>
    </div>
  </header>

  <button class="rail statestage" id="stateStage" aria-label="Toggle dictation" aria-pressed="false">
    <span class="stateword" id="stateWord" aria-live="polite"></span>
    <span class="statehint" id="stateHint"></span>
  </button>

  <div class="rail scopelane">
    <span class="scopelegend">INPUT MONITOR &mdash; 16 kHz MONO</span>
    <canvas id="scopeCanvas" aria-hidden="true"></canvas>
  </div>

  <div class="rail instrumentrail">
    <div class="izone imeter">
      <span class="ilabel">Input</span>
      <div class="ladder" id="ladder" aria-hidden="true"></div>
      <span class="dbread" id="dbRead">-&infin; dB</span>
    </div>
    <div class="izone isession">
      <span class="ilabel">Words this session</span>
      <div class="odomrow">
        <div class="odometer" id="odometer" aria-hidden="true"></div>
        <span class="chip" id="chip"></span>
      </div>
      <span class="srOnly" id="odomSR">0 words this session</span>
    </div>
    <div class="izone iptt">
      <span class="ilabel">Push-to-talk</span>
      <button class="keycap" id="keybtn" aria-label="Change push-to-talk key">&hellip;</button>
      <span class="hint">TAP TO REMAP</span>
    </div>
  </div>

  <div class="rail translog">
    <span class="ilabel">REC.LOG</span>
    <span class="sweepbar" id="sweepBar" aria-hidden="true"></span>
    <div class="logwrap" id="logWrap">
      <div class="logtext empty" id="logText" aria-live="polite">// AWAITING FIRST TAKE</div>
    </div>
    <div class="logmeta" id="logMeta"></div>
  </div>

  <footer class="rail bottomrail">
    <span>EVERYTHING STAYS ON THIS MACHINE</span>
    <a href="https://speakr.cloud" target="_blank" rel="noopener">SPEAKR.CLOUD</a>
  </footer>
</div>

<div class="captureOverlay" id="captureOverlay" role="dialog" aria-modal="true" aria-label="Capturing push-to-talk key" aria-hidden="true">
  <span class="overlegend">AWAITING INPUT</span>
  <div class="overkeycap" id="overKeycap">
    <span class="keytext ph" id="overlayKeyText">&middot;&middot;&middot;</span>
  </div>
  <span class="overhint" id="overHint"></span>
</div>

<div class="grain" aria-hidden="true"></div>

<script>
(function(){
"use strict";
var TOKEN = "__TOKEN__";

/* ================= dom refs ================= */
var htmlEl = document.documentElement;
var chassis = document.getElementById("chassis");
var lamp = document.getElementById("lamp");
var lampcode = document.getElementById("lampcode");
var stateStage = document.getElementById("stateStage");
var stateWordEl = document.getElementById("stateWord");
var stateHint = document.getElementById("stateHint");
var scopeCanvas = document.getElementById("scopeCanvas");
var sctx = scopeCanvas.getContext("2d");
var ladderEl = document.getElementById("ladder");
var dbRead = document.getElementById("dbRead");
var odometerEl = document.getElementById("odometer");
var odomSR = document.getElementById("odomSR");
var chipEl = document.getElementById("chip");
var keybtn = document.getElementById("keybtn");
var sweepBar = document.getElementById("sweepBar");
var logWrap = document.getElementById("logWrap");
var logText = document.getElementById("logText");
var logMeta = document.getElementById("logMeta");
var overlay = document.getElementById("captureOverlay");
var overKeycap = document.getElementById("overKeycap");
var overlayKeyText = document.getElementById("overlayKeyText");
var overHint = document.getElementById("overHint");
var legTl = document.getElementById("legTl"), legTr = document.getElementById("legTr");
var legBl = document.getElementById("legBl"), legBr = document.getElementById("legBr");

var reducedMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

/* ================= app state ================= */
var app = { enabled:false, hotkey:null, state:"loading", status:"", mac:false,
  level:0, words:0, seq:null, last_text:"", last_duration:0, down:false };
var lastSeqSeen = null;
var capturing = false;
var pulseFailCount = 0;
var pulseTimer = null, stateTimer = null, uptimeTimer = null;
var pulseIntervalMs = 250;
var bootDone = reducedMotion;

var STATE_WORDS = { idle:"READY", recording:"LISTENING", processing:"WORKING",
  disabled:"OFF", loading:"WARMING", error:"ERROR", down:"SIGNAL LOST" };
var LAMP_CODES = { idle:"RDY", recording:"REC", processing:"WRK",
  disabled:"OFF", loading:"BOOT", error:"ERR", down:"LOST" };
var LAMP_COLOR = { idle:"#5effb0", recording:"#ff3d00", processing:"#ffb84d",
  loading:"#ffb84d", error:"#ff3d00" };

function clamp01(v){ return v<0?0:(v>1?1:v); }
function pad3(n){ n = Math.max(0, n|0); var s = String(n); while (s.length<3) s = "0"+s; return s; }

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
  if (app.state === "disabled") return "disabled";
  return app.state;
}

/* ================= color ramp ================= */
function rampRGB(t){
  t = t<0?0:(t>1?1:t);
  var c0=[77,162,255], c1=[139,92,246], c2=[232,121,249], a,b,f;
  if (t<0.55){ a=c0; b=c1; f=t/0.55; } else { a=c1; b=c2; f=(t-0.55)/0.45; }
  return [Math.round(a[0]+(b[0]-a[0])*f), Math.round(a[1]+(b[1]-a[1])*f), Math.round(a[2]+(b[2]-a[2])*f)];
}
function rampColor(t, alpha){ var c = rampRGB(t); return "rgba("+c[0]+","+c[1]+","+c[2]+","+alpha+")"; }

/* ================= energy / ballistics (adaptive gain, noise gate, spring) ================= */
var rollPeak = 0.05, meterEnergy = 0, meterVel = 0, takeEnergyPeak = 0;
/* "Violence" (hot-red) is judged on RAW rms against an absolute ceiling, never
   on the adaptive-gain-normalized energy — normalized energy reaches ~1.0 for
   any sustained level, which would falsely paint violence color on ordinary
   speech. Raw >= 0.30 means the mic is genuinely loud right now. */
var RAW_CLIP = 0.30;
var violent = false;
function computeNorm(){
  var raw = app.level || 0;
  var gated = raw < 0.04 ? 0 : raw;
  rollPeak = Math.max(rollPeak*0.995, gated, 0.05);
  var n = clamp01(gated/rollPeak);
  var target = (app.state === "recording") ? n : 0;
  var clip = app.state === "recording" && raw >= RAW_CLIP;
  return { target:target, clip:clip, raw:raw, gated:gated };
}
function stepMeterEnergy(dt){
  var c = computeNorm();
  violent = c.clip;
  var rising = c.target > meterEnergy;
  var k = rising ? 90 : 22;
  var damp = rising ? 13 : 9;
  var accel = (c.target - meterEnergy)*k - meterVel*damp;
  meterVel += accel*dt;
  meterEnergy += meterVel*dt;
  if (meterEnergy < 0){ meterEnergy = 0; meterVel = 0; }
  if (meterEnergy > 1.3){ meterEnergy = 1.3; }
  if (computeVState() === "recording") takeEnergyPeak = Math.max(takeEnergyPeak, meterEnergy);
  return c;
}
var dbSmooth = 0;
function fmtDb(raw){
  dbSmooth += (raw - dbSmooth) * 0.3;
  if (dbSmooth < 0.04) return "-∞ dB";
  var db = 20 * Math.log10(dbSmooth);
  if (db < -60) db = -60;
  if (db > 0) db = 0;
  return db.toFixed(1) + " dB";
}

/* ================= LED ladder ================= */
var SEG_COUNT = 28, TOP_ZONE = 24 /* 0-based index; segments 25-28 */, segEls = [], segColors = [], segColorNow = [], segOn = [];
var HOT_RGB = "rgb(255,61,0)";
function buildLadder(){
  for (var i=0;i<SEG_COUNT;i++){
    var n = i+1, rgb;
    if (n <= 20){ rgb = rampRGB((n-1)/19 * 0.55); }
    else { rgb = [232,121,249]; } /* 21-28 baseline pink; top zone (25-28) only
      upgrades to violence-hot when the raw signal is genuinely loud (see drawLadder) */
    segColors.push("rgb("+rgb[0]+","+rgb[1]+","+rgb[2]+")");
    var el = document.createElement("span");
    el.className = "seg";
    ladderEl.appendChild(el);
    segEls.push(el);
    segOn.push(false);
    segColorNow.push(null);
  }
}
var peakSeg = 0, peakHoldT = 0, lastPeakStep = 0;
var bootSweeping = false, bootSweepStart = 0;
function drawLadder(now){
  var litCount;
  if (bootSweeping){
    var frac = (now - bootSweepStart) / 250;
    if (frac >= 1){ bootSweeping = false; litCount = 0; }
    else {
      var tri = frac < 0.5 ? frac*2 : (1-frac)*2;
      litCount = Math.round(tri * SEG_COUNT);
    }
    peakSeg = litCount; peakHoldT = now;
  } else {
    var e = clamp01(meterEnergy);
    litCount = Math.round(e * SEG_COUNT);
    if (litCount >= peakSeg){ peakSeg = litCount; peakHoldT = now; }
    else if (now - peakHoldT > 700 && now - lastPeakStep > 40){
      peakSeg = Math.max(litCount, peakSeg - 1);
      lastPeakStep = now;
    }
  }
  /* Only touch style (incl. box-shadow) on the handful of segments whose lit
     state or color actually changed this frame — never repaint all 28
     unconditionally, which is the "animating box-shadow per frame" trap. */
  for (var i=0;i<SEG_COUNT;i++){
    var on = i < litCount || i === peakSeg - 1;
    var color = (i >= TOP_ZONE && violent) ? HOT_RGB : segColors[i];
    if (on === segOn[i] && color === segColorNow[i]) continue;
    segOn[i] = on;
    segColorNow[i] = color;
    segEls[i].style.background = on ? color : "#161a26";
    segEls[i].style.boxShadow = on ? ("0 0 4px " + color) : "none";
  }
  dbRead.textContent = fmtDb(app.level || 0);
}

/* ================= scope lane ================= */
var DPR = Math.max(1, window.devicePixelRatio || 1);
var SCOPE_WINDOW = 6000;
var scopeBuf = [];
function setupScopeCanvas(){
  var w = scopeCanvas.clientWidth || window.innerWidth;
  var h = scopeCanvas.clientHeight || 120;
  scopeCanvas.width = Math.round(w*DPR);
  scopeCanvas.height = Math.round(h*DPR);
  sctx.setTransform(DPR,0,0,DPR,0,0);
}
function scopePush(){
  if (reducedMotion) return;
  var vs = computeVState();
  if (vs === "disabled" || vs === "down") return;
  var c = computeNorm();
  var now = performance.now();
  scopeBuf.push({ t:now, v:c.target, clip:c.clip });
  var cutoff = now - SCOPE_WINDOW - 500;
  while (scopeBuf.length && scopeBuf[0].t < cutoff) scopeBuf.shift();
}
function drawDot(x,y,color){ sctx.fillStyle = color; sctx.fillRect(x, y, 2, 2); }
/* Dot rows grow FROM the 1px center reference line outward — row 0 sits
   immediately adjacent to it on each side (near=2 is just enough clearance
   for the dot's own 2px height, not a dead band). */
var SCOPE_NEAR = 2, SCOPE_ROW_PITCH = 4, SCOPE_COL_PITCH = 4;
function scopeRowY(cy, r, down){
  return down ? (cy + 1 + r*SCOPE_ROW_PITCH) : (cy - SCOPE_NEAR - r*SCOPE_ROW_PITCH);
}
function drawScope(now){
  var w = scopeCanvas.width / DPR, h = scopeCanvas.height / DPR;
  sctx.clearRect(0,0,w,h);
  var cy = h/2;
  sctx.fillStyle = "rgba(255,255,255,.08)";
  sctx.fillRect(0, Math.round(cy), w, 1);
  var vs = computeVState();
  var colPitch = SCOPE_COL_PITCH, rowPitch = SCOPE_ROW_PITCH;
  var maxHalf = Math.max(1, Math.min(cy - SCOPE_NEAR - 2, 44));
  var maxRows = Math.floor(maxHalf/rowPitch);
  if (vs === "disabled" || vs === "down"){
    for (var x0=2; x0<w; x0+=colPitch) drawDot(x0, cy-1, "rgba(120,130,160,.25)");
    return;
  }
  var idx = scopeBuf.length - 1;
  for (var x = w - 2; x >= 0; x -= colPitch){
    var age = (1 - x/w) * SCOPE_WINDOW;
    var target = now - age;
    while (idx > 0 && scopeBuf[idx].t > target) idx--;
    var s = scopeBuf[idx];
    var amp = s ? s.v : 0;
    var clip = s ? s.clip : false;
    /* history age fade: newest (right edge, x near w) ~100% alpha, oldest
       (left edge, x near 0) ~40% alpha, so the lane reads directional */
    var ageMul = clamp01(0.4 + 0.6*(x/w));
    if (amp <= 0){
      /* idle/silent: a single dim center dot-row, never a hollow tram-track
         pair — matches the OFF-state frozen line rendering */
      drawDot(x, cy-1, "rgba(120,130,160," + (0.25*ageMul).toFixed(3) + ")");
      continue;
    }
    var rows = Math.max(1, Math.min(maxRows, Math.round(amp * maxRows)));
    var alpha = clamp01((0.28 + amp*0.72) * ageMul);
    var col = rampColor(amp, alpha);
    for (var r=0;r<rows;r++){
      var yUp = scopeRowY(cy, r, false);
      var yDn = scopeRowY(cy, r, true);
      var isOuter = r === rows - 1;
      var c2 = (isOuter && clip) ? ("rgba(255,61,0," + ageMul.toFixed(2) + ")") : col;
      drawDot(x, yUp, c2);
      drawDot(x, yDn, c2);
    }
  }
}

/* ================= state word engine ================= */
var curWordText = null, wordChars = [], curMode = null;
var lastFlash = -9999, flashUntil = 0;
var SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
function fitWord(){
  stateWordEl.style.transform = "scale(1)";
  var avail = stateStage.clientWidth * 0.92;
  var need = stateWordEl.scrollWidth;
  var scale = need > avail && need > 0 ? avail/need : 1;
  stateWordEl.style.transform = "scale(" + scale.toFixed(3) + ")";
  stateStage.style.setProperty("--fit", scale.toFixed(3));
}
function setWordText(txt){
  if (txt === curWordText) return;
  curWordText = txt;
  stateWordEl.innerHTML = "";
  wordChars = [];
  for (var i=0;i<txt.length;i++){
    var ch = txt.charAt(i);
    var span = document.createElement("span");
    span.className = "ch";
    span.textContent = ch === " " ? " " : ch;
    stateWordEl.appendChild(span);
    wordChars.push(span);
  }
  fitWord();
}
function modeFor(vs){
  if (vs === "recording") return "wave";
  if (vs === "processing") return "scramble";
  if (vs === "disabled" || vs === "down") return "outline";
  return "breathe";
}
/* Letters lock left-to-right over SCRAMBLE_LOCK_MS, then the fully-locked
   word HOLDS (legible, full ink) for SCRAMBLE_HOLD_MS before the next cycle —
   without the hold, a mid-cycle frame reads as illegible noise. */
var SCRAMBLE_LOCK_MS = 700, SCRAMBLE_HOLD_MS = 900;
var SCRAMBLE_PERIOD = SCRAMBLE_LOCK_MS + SCRAMBLE_HOLD_MS;
function scrambleUpdate(now){
  var phase = now % SCRAMBLE_PERIOD, n = wordChars.length;
  for (var i=0;i<n;i++){
    var ch = curWordText.charAt(i);
    if (ch === " "){ wordChars[i].textContent = " "; wordChars[i].style.opacity = "1"; continue; }
    var lockAt = (i/n) * SCRAMBLE_LOCK_MS;
    var locked = phase >= lockAt;
    if (!locked){
      var seed = Math.floor(phase/55) + i*7;
      wordChars[i].textContent = SCRAMBLE_CHARS.charAt(seed % SCRAMBLE_CHARS.length);
      wordChars[i].style.opacity = "0.5";
    } else {
      wordChars[i].textContent = ch;
      wordChars[i].style.opacity = "1";
    }
    wordChars[i].style.fontWeight = 400;
  }
}
function updateWordVisual(now, energy, mode){
  if (mode !== curMode){
    stateWordEl.classList.toggle("outline", mode === "outline");
    if (mode !== "wave"){
      stateWordEl.classList.remove("flash");
      stateWordEl.style.letterSpacing = "0em";
    }
    if (mode === "outline"){
      for (var k=0;k<wordChars.length;k++) wordChars[k].style.fontWeight = 600;
    }
    if (mode !== "scramble"){
      for (var m=0;m<wordChars.length;m++) wordChars[m].style.opacity = "";
    }
    curMode = mode;
  }
  if (mode === "breathe"){
    var w = Math.round(380 + 40 * Math.sin(now/2600 * Math.PI*2));
    for (var i=0;i<wordChars.length;i++) wordChars[i].style.fontWeight = w;
  } else if (mode === "wave"){
    var en = clamp01(energy);
    for (var j=0;j<wordChars.length;j++){
      var w2 = 400 + Math.round(260 * en * Math.sin(now/380 - j*0.85));
      if (w2 < 300) w2 = 300; if (w2 > 900) w2 = 900;
      wordChars[j].style.fontWeight = w2;
    }
    stateWordEl.style.letterSpacing = (en*0.06).toFixed(3) + "em";
    if (stateWordEl.classList.contains("flash")){
      if (now >= flashUntil) stateWordEl.classList.remove("flash");
    } else if (violent && now - lastFlash > 600){
      lastFlash = now; flashUntil = now + 120;
      stateWordEl.classList.add("flash");
    }
  } else if (mode === "scramble"){
    scrambleUpdate(now);
  }
}
function renderWordStatic(vs, mode){
  stateWordEl.classList.toggle("outline", mode === "outline");
  stateWordEl.classList.remove("flash");
  stateWordEl.style.letterSpacing = "0em";
  var w = mode === "outline" ? 600 : 400;
  for (var i=0;i<wordChars.length;i++){
    wordChars[i].style.fontWeight = w;
    wordChars[i].style.opacity = "";
    wordChars[i].textContent = curWordText.charAt(i) === " " ? " " : curWordText.charAt(i);
  }
  curMode = mode;
}

/* ================= lamp / hint / render ================= */
function hintFor(vs){
  switch(vs){
    case "idle": return "HOLD " + keyLabel(app.hotkey, app.mac) + " · SPEAK · RELEASE";
    case "recording": return "RELEASE TO COMMIT";
    case "processing": return "CLEANING TRANSCRIPT";
    case "disabled": return "HOTKEY DISARMED";
    case "loading": return (app.status || "WARMING UP").toUpperCase();
    case "error": return (app.status || "ERROR").toUpperCase();
    case "down": return "PROCESS NOT RUNNING — REOPEN FROM TRAY";
  }
  return "";
}
var prevVState = null;
function render(){
  var vs = computeVState();
  chassis.setAttribute("data-vstate", vs);
  lampcode.textContent = LAMP_CODES[vs];
  var col = LAMP_COLOR[vs];
  if (col){
    lamp.style.background = col;
    lamp.style.boxShadow = "0 0 6px " + col + ", inset 0 1px 2px rgba(0,0,0,.6)";
  } else {
    lamp.style.background = "#22283a";
    lamp.style.boxShadow = "inset 0 1px 2px rgba(0,0,0,.6)";
  }
  setWordText(STATE_WORDS[vs]);
  stateHint.textContent = hintFor(vs);
  stateStage.setAttribute("aria-pressed", String(vs !== "disabled" && vs !== "down"));
  if (!capturing) keybtn.textContent = keyLabel(app.hotkey, app.mac);
  if (vs !== prevVState){
    if (reducedMotion) renderWordStatic(vs, modeFor(vs));
    prevVState = vs;
  }
  if (reducedMotion) drawStaticFrame();
}
function drawScopeStatic(){
  var w = scopeCanvas.width / DPR, h = scopeCanvas.height / DPR;
  sctx.clearRect(0,0,w,h);
  var cy = h/2;
  sctx.fillStyle = "rgba(255,255,255,.08)";
  sctx.fillRect(0, Math.round(cy), w, 1);
  var vs = computeVState();
  var colPitch = SCOPE_COL_PITCH, rowPitch = SCOPE_ROW_PITCH;
  var maxHalf = Math.max(1, Math.min(cy - SCOPE_NEAR - 2, 44));
  var maxRows = Math.floor(maxHalf/rowPitch);
  var amp = (vs === "recording") ? clamp01(meterEnergy) : 0;
  var clip = vs === "recording" && (app.level || 0) >= RAW_CLIP;
  if (amp <= 0){
    for (var x1 = 2; x1 < w; x1 += colPitch) drawDot(x1, cy-1, "rgba(120,130,160,.25)");
    return;
  }
  var rows = Math.max(1, Math.min(maxRows, Math.round(amp * maxRows)));
  var alpha = clamp01(0.28 + amp*0.72);
  var col = rampColor(amp, alpha);
  for (var x = 2; x < w; x += colPitch){
    for (var r=0;r<rows;r++){
      var yUp = scopeRowY(cy, r, false), yDn = scopeRowY(cy, r, true);
      var isOuter = r === rows - 1;
      var c2 = (isOuter && clip) ? "rgba(255,61,0,1)" : col;
      drawDot(x, yUp, c2); drawDot(x, yDn, c2);
    }
  }
}
/* A single non-scrolling frame per real data update — never a rAF-driven
   animation — satisfies "prefers-reduced-motion = fully static page". */
function drawStaticFrame(){
  var c = computeNorm();
  meterEnergy = c.target;
  drawLadder(performance.now());
  drawScopeStatic();
}

/* ================= words odometer ================= */
var odoDigits = [];
function buildDigit(){
  var col = document.createElement("span"); col.className = "odocell";
  var strip = document.createElement("span"); strip.className = "odostrip";
  for (var d=0; d<10; d++){ var s = document.createElement("span"); s.textContent = String(d); strip.appendChild(s); }
  col.appendChild(strip);
  return { col:col, strip:strip };
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
    var ch = i < pad ? "0" : str.charAt(i-pad);
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
function spawnChip(n){
  if (reducedMotion || n <= 0) return;
  chipEl.textContent = "+" + n;
  chipEl.classList.remove("show");
  void chipEl.offsetWidth;
  chipEl.classList.add("show");
}
function setWordsInstant(n){ renderOdometer(n, false); }
function setWords(n){
  var prev = app.words || 0;
  renderOdometer(n, true);
  if (n > prev) spawnChip(n - prev);
}

/* ================= transcript log ================= */
var logTimer = null;
function updateLogMask(){
  var overflowing = (logWrap.scrollHeight - logWrap.clientHeight) > 8;
  logWrap.classList.toggle("masked", overflowing);
}
function metaStr(text, duration, seq){
  var words = text.trim().length ? text.trim().split(/\s+/).length : 0;
  return words + " WORD" + (words===1?"":"S") + " · " + (duration||0).toFixed(1) + " SEC · " +
    "<span class=\"take\" id=\"takeNum\">TAKE " + pad3(seq) + "</span>";
}
function setLogInstant(text, duration, seq){
  if (logTimer){ clearTimeout(logTimer); logTimer = null; }
  logText.classList.toggle("empty", !text);
  logText.textContent = text ? text : "// AWAITING FIRST TAKE";
  logMeta.innerHTML = text ? metaStr(text, duration, seq) : "";
  updateLogMask();
}
function celebrateLog(text, duration, seq){
  if (logTimer){ clearTimeout(logTimer); logTimer = null; }
  var col = rampColor(clamp01(takeEnergyPeak) || 0.15, 1);
  sweepBar.style.background = col;
  sweepBar.classList.remove("run");
  if (!reducedMotion){ void sweepBar.offsetWidth; sweepBar.classList.add("run"); }
  takeEnergyPeak = 0;
  if (reducedMotion || !text){ setLogInstant(text, duration, seq); return; }
  logText.classList.remove("empty");
  logText.textContent = "";
  logMeta.innerHTML = "";
  var textNode = document.createTextNode("");
  var cursor = document.createElement("span");
  cursor.className = "cursor"; cursor.textContent = "█";
  logText.appendChild(textNode); logText.appendChild(cursor);
  updateLogMask();
  var len = text.length;
  if (len === 0){ cursor.classList.add("hide"); finalizeMeta(text, duration, seq); return; }
  var perChar = Math.min(8, 1400/len);
  var i = 0;
  function tick(){
    i++;
    textNode.data = text.slice(0, i);
    updateLogMask();
    if (i >= len){
      cursor.classList.add("hide");
      finalizeMeta(text, duration, seq);
      return;
    }
    logTimer = setTimeout(tick, perChar);
  }
  logTimer = setTimeout(tick, perChar);
}
function finalizeMeta(text, duration, seq){
  logMeta.innerHTML = metaStr(text, duration, seq);
  updateLogMask();
  if (reducedMotion) return;
  var takeEl = document.getElementById("takeNum");
  if (takeEl){
    takeEl.classList.remove("snap");
    void takeEl.offsetWidth;
    takeEl.classList.add("snap");
  }
}

/* ================= hotkey capture theater ================= */
function shakeKeybtn(){
  keybtn.classList.remove("shake");
  void keybtn.offsetWidth;
  keybtn.classList.add("shake");
  setTimeout(function(){ keybtn.classList.remove("shake"); }, 380);
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
  overKeycap.classList.remove("shake","press","flash");
  overlayKeyText.classList.remove("slam");
  overlayKeyText.classList.add("ph");
  overlayKeyText.textContent = "···";
  overHint.textContent = app.mac ? "FN · RIGHT ⌘ · RIGHT ⌥ · RIGHT ⌃ · CAPS" : "ANY KEY — ESC CANCELS";
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");

  postCapture().then(function(res){
    if (res.status === 409){
      capturing = false;
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      shakeKeybtn();
      return;
    }
    if (!capturing) return;
    if (res.data && res.data.ok && res.data.hotkey){
      app.hotkey = res.data.hotkey;
      render();
      overlayKeyText.classList.remove("ph");
      overlayKeyText.textContent = keyLabel(res.data.hotkey, app.mac);
      overlayKeyText.classList.remove("slam");
      void overlayKeyText.offsetWidth;
      overlayKeyText.classList.add("slam");
      overKeycap.classList.add("press");
      setTimeout(function(){
        overKeycap.classList.remove("press");
        overKeycap.classList.add("flash");
        setTimeout(function(){ overKeycap.classList.remove("flash"); }, 150);
      }, 140);
      setTimeout(closeOverlay, 500);
    } else {
      overlayKeyText.classList.remove("ph");
      overlayKeyText.textContent = "NO INPUT";
      overKeycap.classList.remove("shake");
      void overKeycap.offsetWidth;
      overKeycap.classList.add("shake");
      setTimeout(closeOverlay, 500);
    }
  }).catch(function(){
    if (!capturing) return;
    overlayKeyText.classList.remove("ph");
    overlayKeyText.textContent = "NO INPUT";
    overKeycap.classList.add("shake");
    setTimeout(closeOverlay, 500);
  });
}

/* ================= network ================= */
function getPulse(){ return fetch("/api/pulse").then(function(r){ return r.json(); }); }
function getState(){ return fetch("/api/state", { headers:{ "X-Speakr-Token":TOKEN } }).then(function(r){ return r.json(); }); }
function postToggle(){ return fetch("/api/toggle", { method:"POST", headers:{ "X-Speakr-Token":TOKEN } }).then(function(r){ return r.json(); }); }
function postCapture(){
  return fetch("/api/capture", { method:"POST", headers:{ "X-Speakr-Token":TOKEN } }).then(function(r){
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
  maybeStartBoot();

  if (firstLoad){
    setLogInstant(app.last_text, app.last_duration, newSeq || 0);
    setWordsInstant(newWords);
    if (newSeq !== null) lastSeqSeen = newSeq;
  } else {
    if (newSeq !== null && newSeq > lastSeqSeen && app.last_text){
      celebrateLog(app.last_text, app.last_duration, newSeq);
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
    scopePush();
    render();
    if (wasDown || ((stateChanged || seqChanged) && !capturing)) fetchStateNow();
    pulseIntervalMs = (p.state === "recording" || p.state === "processing") ? 90 : 250;
  }).catch(function(){
    pulseFailCount++;
    if (pulseFailCount >= 4 && !app.down){ app.down = true; render(); }
  }).then(function(){
    if (!document.hidden) pulseTimer = setTimeout(pollPulse, pulseIntervalMs);
  });
}
function scheduleState(){
  if (document.hidden) return;
  stateTimer = setTimeout(function(){ fetchStateNow().then(scheduleState); }, 2000);
}

/* ================= boot sequence ================= */
var bootStarted = false;
function maybeStartBoot(){
  if (bootStarted) return;
  bootStarted = true;
  if (reducedMotion){ finishBootInstant(); return; }
  startBootSequence();
}
function finishBootInstant(){
  htmlEl.classList.remove("boot");
  legTl.classList.add("in"); legTr.classList.add("in"); legBl.classList.add("in"); legBr.classList.add("in");
  bootDone = true;
}
function startBootSequence(){
  setTimeout(function(){
    var now = performance.now();
    bootSweeping = true; bootSweepStart = now;
    lamp.classList.add("blink");
  }, 150);
  setTimeout(function(){ lamp.classList.remove("blink"); }, 450);
  setTimeout(function(){
    stateWordEl.style.opacity = "1";
    stateWordEl.classList.remove("stamp");
    void stateWordEl.offsetWidth;
    stateWordEl.classList.add("stamp");
  }, 460);
  setTimeout(function(){
    htmlEl.classList.remove("boot");
    legTl.classList.add("in"); legTr.classList.add("in"); legBl.classList.add("in"); legBr.classList.add("in");
  }, 650);
  setTimeout(function(){ bootDone = true; }, 900);
}

/* ================= uptime clock ================= */
var uptimeStart = Date.now();
function tickUptime(){
  var s = Math.floor((Date.now() - uptimeStart)/1000);
  var hh = Math.floor(s/3600), mm = Math.floor((s%3600)/60), ss = s%60;
  function p2(n){ return (n<10?"0":"")+n; }
  legBr.textContent = "UPTIME " + p2(hh) + ":" + p2(mm) + ":" + p2(ss);
}

/* ================= main rAF loop ================= */
var rafId = null, lastTs = 0;
function frame(ts){
  var dt = lastTs ? Math.min((ts - lastTs)/1000, 0.05) : 0.016;
  lastTs = ts;
  stepMeterEnergy(dt);
  var vs = computeVState();
  updateWordVisual(ts, meterEnergy, modeFor(vs));
  drawLadder(ts);
  drawScope(ts);
  rafId = requestAnimationFrame(frame);
}
function startLoop(){ if (rafId === null && !reducedMotion) rafId = requestAnimationFrame(frame); }
function stopLoop(){ if (rafId !== null){ cancelAnimationFrame(rafId); rafId = null; } }

/* ================= wiring ================= */
function bindUI(){
  stateStage.addEventListener("click", function(){
    postToggle().then(applyState).catch(function(){});
  });
  keybtn.addEventListener("click", function(){ openCaptureFlow(); });
  overlay.addEventListener("click", function(e){ if (e.target === overlay) closeOverlay(); });
  window.addEventListener("resize", function(){ setupScopeCanvas(); fitWord(); });
  document.addEventListener("visibilitychange", function(){
    if (document.hidden){
      stopLoop();
      if (pulseTimer){ clearTimeout(pulseTimer); pulseTimer = null; }
      if (stateTimer){ clearTimeout(stateTimer); stateTimer = null; }
      if (uptimeTimer){ clearInterval(uptimeTimer); uptimeTimer = null; }
    } else {
      startLoop();
      pollPulse();
      fetchStateNow().then(scheduleState);
      tickUptime();
      uptimeTimer = setInterval(tickUptime, 1000);
    }
  });
}

function init(){
  buildLadder();
  setupScopeCanvas();
  bindUI();
  render();
  tickUptime();
  uptimeTimer = setInterval(tickUptime, 1000);
  fetchStateNow().then(scheduleState);
  pollPulse();
  startLoop();
}
init();
})();
</script>
</body>
</html>
"""
