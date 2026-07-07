# Speakr

Private, fully-local voice dictation for Windows and macOS — a Wispr Flow
replacement where **no audio or text ever leaves your machine**.

Hold a key (Right Ctrl on Windows, **fn** on Mac), speak, release. Cleaned-up
text appears at your cursor in whatever app has focus.

## How it works

```
hold hotkey ──► mic capture ──► faster-whisper (local ASR)
                                      │
              focused-app detection ──┤
                                      ▼
                    formatting: rule-based cleanup, then optional
                    local LLM polish via Ollama (if running)
                                      │
                                      ▼
                    personal dictionary replacements
                                      │
                                      ▼
                    text injected at your cursor (Ctrl+V or typed)
```

Everything runs on this machine. The only network access, ever:
- **One-time model download** from Hugging Face on first run (whisper weights).
- **Ollama on 127.0.0.1** — a local process; nothing goes to the internet.

## Dictation features

- **Filler removal** — "um", "uh", "erm", "hmm" are stripped even without the
  LLM; the LLM pass also catches "you know" / "I mean" style filler.
- **Self-corrections** — "let's meet at 2... actually 3" comes out as
  *"Let's meet at 3."* (LLM pass).
- **Lists** — dictate "first..., second..., third..." and it's formatted as
  one item per line (LLM pass).
- **Spoken commands** — say "new line", "new paragraph", or "bullet point"
  for explicit layout; these work even without the LLM. Disable with
  `"voice_commands": false`.
- **Context awareness** — the foreground app and window title steer tone and
  formatting, and your last few dictations are given to the LLM as context
  (kept in memory only) so follow-on dictations read naturally.
- **On-screen text context** (Windows) — when you press the hotkey, Speakr
  reads the focused text field once via UI Automation and uses names/jargon
  found there to spell your words right (dictate a reply mentioning
  "Kowalczyk" and it's spelled like the message on screen). One capped query
  per dictation on a background thread — no polling, no screenshots, nothing
  stored or logged. Toggle: tray → "Screen context".
- **Streaming transcription** — long dictations are transcribed in chunks at
  natural pauses *while you speak*, so text appears fast on release no matter
  how long you talked. Chunks only split at real silences and carry context
  across boundaries; short dictations use a single pass, unchanged.
- **Vocabulary learning** — recurring uncommon words (names, jargon,
  CamelCase terms) from your dictations are counted in `learned_words.json`;
  once a word shows up 3 times it's fed to the transcriber as a hint, so
  recognition of *your* vocabulary improves the more you dictate. Toggle via
  tray → "Learn vocabulary".
- **Edit Mode** (Windows) — select existing text anywhere, hold the hotkey,
  and speak an instruction instead of dictation: "make this shorter", "turn
  this into bullets", "make it more formal". The selection is replaced with
  the transformed text; if the edit can't run, your selection is left
  untouched. Uses UI Automation to read the selection, with a
  clipboard-based fallback for apps that don't expose it (your clipboard is
  always restored). Disabled automatically in terminals/code editors.
  Toggle via tray → "Edit selected text".
- **Mic self-healing** — if Windows switches audio devices while Speakr is
  running (headset on/off, a game grabbing the mic), the stale stream is
  detected and reopened automatically; if a recording comes back mostly
  empty, the tray tells you to dictate again instead of silently failing.

## Quick start — Windows

1. Double-click **`run.bat`** (first run creates the environment and downloads
   the model — give it a couple of minutes).
2. Look for the round mic icon in the system tray.
3. Focus any text field, **hold Right Ctrl**, speak, release.

Tray icon colors: blue = idle, red = recording, orange = processing,
gray = loading/disabled.

Use `run_debug.bat` to run with a console and live logs.

## Quick start — macOS (as a real app)

```
git clone https://github.com/grphxdsign-ops/Speakr.git
cd Speakr
bash package_mac.sh
mv dist/Speakr.app /Applications/
open /Applications/Speakr.app
```

- First launch sets up its Python environment and downloads the model — give
  it a few minutes; the mic icon appears in the menu bar when ready.
  Progress logs: `~/Library/Application Support/Speakr/setup.log`.
- Grant the permissions macOS prompts for — they're attributed to **Speakr**
  itself now (Microphone, Input Monitoring, Accessibility under System
  Settings → Privacy & Security). Quit and reopen Speakr after granting.
- Your config, dictionary, learned words, and logs live in
  `~/Library/Application Support/Speakr/` — updating the app never touches
  them, and the venv there is reused (no re-download unless requirements.txt
  changed). To update:
  ```
  # Quit Speakr first (menu bar icon -> Quit)
  cd Speakr && git pull && bash package_mac.sh
  rm -rf /Applications/Speakr.app && mv dist/Speakr.app /Applications/
  open /Applications/Speakr.app
  ```
  (`Speakr.app` already exists in `/Applications` after the first install, so
  it must be removed before the `mv`, not overwritten in place.)
- Start at login: System Settings → General → Login Items → add Speakr.
- No Dock icon by design — it's a menu-bar app.

## Quick start — macOS (from Terminal instead)

1. Clone it (the repo excludes machine-specific files by design, so a fresh
   clone is exactly what you want):
   ```
   git clone https://github.com/grphxdsign-ops/Speakr.git
   cd Speakr
   ```
   Your personal `dictionary.txt` and `learned_words.json` aren't in the repo
   (they're private). They regenerate empty on first run — copy them over from
   another machine by hand if you want that vocabulary to follow you.
2. In Terminal: `bash run.sh` (first run sets up the environment and
   downloads the model).
3. Grant the permissions macOS prompts for, all under System Settings →
   Privacy & Security, to the app you launched from (e.g. Terminal):
   **Microphone**, **Input Monitoring** (to see the fn key), and
   **Accessibility** (to paste). Restart Speakr after granting
   (`bash run_debug.sh` shows logs if something's off).
4. So the fn key doesn't ALSO pop the emoji picker: System Settings →
   Keyboard → "Press 🌐 key to" → **Do Nothing** (and turn off Apple's own
   double-tap-fn dictation shortcut if enabled).
5. Focus any text field, **hold fn**, speak, release.

On the Mac the hotkey supports modifier-style keys: `fn` (default),
`right cmd`, `right option`, `right ctrl`, `caps lock`, etc. Transcription
runs on the CPU there (no CUDA) — `base`/`small` are comfortably fast on
Apple Silicon. Ollama for the LLM polish: [ollama.com/download](https://ollama.com/download),
then `ollama pull llama3.2` — Speakr auto-starts and auto-detects it.

## Control panel

Tray → **Open Speakr** (or double-click the tray icon on Windows) opens a
small control panel in your browser — same look as
[speakr.cloud](https://speakr.cloud) — with an on/off switch and a
Settings area where clicking the key button rebinds the push-to-talk key:
press the key you want (any key on Windows; a modifier-style key like fn,
right ⌘, right ⌥, or caps lock on macOS) and it's saved to `config.json`
and applied immediately. The panel is served from `127.0.0.1` only, and
state-changing requests require a per-run token — nothing is exposed to
the network.

## Configuration (`config.json`)

Created next to the app on first run. Highlights:

| Setting | Default | Notes |
|---|---|---|
| `hotkey` | `"right ctrl"` | Single key = hold-to-talk. A combo like `"ctrl+shift+space"` becomes toggle (press to start, press to stop). |
| `model` | `"auto"` | Picks `large-v3-turbo` on GPU (near-flagship accuracy, ~0.2s) and `small` on CPU. Or pin `tiny`/`base`/`small`/`medium`/`large-v3-turbo`/`large-v3` from the tray menu — smaller = faster, bigger = more accurate. |
| `preroll_seconds` | `0.4` | Rolling mic buffer prepended to each dictation so words started just before the keypress aren't clipped. |
| `vad_threshold` | `0.35` | Lower hears quiet speech better; raise toward `0.5` in noisy rooms. |
| `device` | `"auto"` | Tries the GPU, verifies it actually works, falls back to CPU. |
| `language` | `null` | Auto-detect. Set e.g. `"en"` to pin it and save a little latency. |
| `beam_size` | `"auto"` | Beam-search width for transcription: 5 on GPU (noticeably better word accuracy), 1 on CPU (speed). |
| `edit_mode` | on | Selected text + spoken instruction = transformation (see features). `clipboard_fallback` controls the Ctrl+C-based capture for non-UIA apps. |
| `injection` | `"paste"` | `"paste"` = clipboard + Ctrl+V (most compatible). `"type"` = simulated keystrokes. |
| `keep_mic_stream_open` | `true` | Lower latency, but the mic indicator stays on. Set `false` to open the mic only while the hotkey is held. |
| `formatting.use_ollama` | `true` | Used only if Ollama is running at `ollama_url`. Otherwise rule-based cleanup applies. |
| `formatting.autostart_ollama` | `true` | If Ollama is installed but not running, Speakr starts `ollama serve` itself at launch. |
| `formatting.ollama_model` | `"llama3.1:8b"` | Any local model you've pulled. Benchmarked 12/12 on hard cases vs 11/12 for `llama3.2` (see "AI formatting" below). |
| `formatting.include_recent_context` | `true` | Give the LLM your last few dictations (memory only) for continuity. |
| `formatting.keep_alive` | `"10m"` | How long Ollama keeps the model resident in VRAM after your last dictation before unloading it. Shorter frees VRAM back for other apps/games during idle stretches, at the cost of a few-second reload on the next dictation after that gap. Set to `"2h"` (or higher) for always-instant response at the cost of permanently holding the ~5GB. |
| `voice_commands` | `true` | "new line" / "new paragraph" / "bullet point" spoken commands. |
| `streaming` | on, 10s chunks | Mid-speech chunked transcription for long dictations. |
| `screen_context` | on, 1200 chars | Focused-field text capture for spelling context (Windows). Note: the first query can switch a Chromium-based app (Chrome, Slack, Discord) into accessibility mode, a small ongoing cost in that app — disable here if you notice it. |
| `learning.enabled` | `true` | Vocabulary learning; `min_occurrences` (3) and `max_hints` (40) tune it. |
| `app_tones` | see file | Per-app tone: `casual` / `formal` / `neutral` / `literal`. `literal` (code editors, terminals) skips the LLM pass so nothing rewrites your commands. |
| `hotkey_exclude_apps` | `[]` | Apps where the hotkey is ignored entirely — see "Using the hotkey for other things" below. |
| `log_transcripts` | `false` | Keep dictated text out of `speakr.log` unless you opt in. |

Privacy note: `learned_words.json` contains single words you've dictated
repeatedly (never sentences). Delete the file anytime to reset learning.

After editing, use tray → **Reload config**.

## Using the hotkey for other things (games, other apps)

Speakr's hotkey (fn on Mac, Right Ctrl on Windows) never blocks the
physical key from anything else — both hotkey backends only *listen*, they
never suppress or consume the keypress, so it reaches every other app and
OS feature completely normally whether or not Speakr is also watching it.

What it doesn't do on its own: stop *Speakr itself* from reacting when
you're holding that key for an unrelated reason — a game keybind on the
same key as push-to-talk, for instance, would also start a recording, and
releasing it would paste whatever got transcribed into the game.
`hotkey_exclude_apps` fixes that:

```json
"hotkey_exclude_apps": ["leagueoflegends.exe", "csgo.exe"]
```

While one of those is focused, Speakr ignores the hotkey completely — no
recording, no paste — while the key still does whatever it normally does
in that app. Windows: exe name (check Task Manager → Details). macOS: the
app's display name.

## Personal dictionary (`dictionary.txt`)

One entry per line:

```
Kubernetes            # bias transcription toward this spelling
jira => Jira          # hard replacement after transcription
```

## AI formatting

The LLM polish (self-corrections, lists, per-app tone, instruction-injection
resistance) uses Ollama with **`llama3.1:8b`** — benchmarked against smaller
and larger local models on a deliberately hard test set (chained
corrections, nested list items, prompt-injection attempts) and won cleanly:
12/12 vs 9/12 for the earlier `llama3.2` default, at 0.4–1.2s per dictation
once warm — still well under Wispr Flow's published 2–4s cloud round trip.
Pull it once: `ollama pull llama3.1:8b`.

Speakr starts Ollama automatically if it isn't running, pre-warms the model
at launch so the first real dictation isn't slow, and re-detects Ollama once
a minute if it comes up later. Without Ollama, rule-based cleanup still
strips fillers, fixes spacing/capitalization, and honors spoken layout
commands.

On a memory-constrained machine (e.g. an 8GB Mac), set
`formatting.ollama_model` back to `"llama3.2"` (2GB, ~0.3-0.7s) — it's
still solid on the everyday majority of dictation, just weaker on chained
corrections.

If VRAM is tight but you're on a GPU that could fit llama3.1:8b (like this
machine's 12GB card), don't reach for a smaller quantization of the same
model — tested `q4_0` and `q3_K_M` against the hard-case suite and both
were worse (real regressions, one outright flaky, for barely any size
saved). The actual free lever is `formatting.keep_alive` (see the config
table above): shortening it frees the ~5GB back automatically whenever
Speakr's been idle, without touching model quality at all.

List formatting uses Ollama's structured-output mode (a JSON schema, not
free-form prose) — the model only classifies list-intent and extracts
items; a deterministic formatter in code does the actual numbering and
typesetting. This avoids small models echoing prompt examples into your
text, a failure mode hit and fixed during development.

## GPU

`pip install -r requirements-gpu.txt` (into `.venv`) enables CUDA
transcription on NVIDIA cards — already done during setup on this machine.
If the CUDA runtime is broken or absent, Speakr detects that during a
warm-up inference and silently falls back to CPU.

## Start with Windows (optional)

Press `Win+R`, run `shell:startup`, and drop a shortcut to `run.bat` there.

## Troubleshooting

- **No text appears**: some elevated (admin) windows ignore input from
  non-elevated processes — run Speakr as admin if you dictate into those.
- **Mic not recording**: Windows Settings → Privacy → Microphone → allow
  desktop apps.
- **Slow first transcription**: the model warms up on first use; subsequent
  dictations are fast.
- **Logs**: tray → View log, or `speakr.log` in this folder.

## Testing

```
.venv\Scripts\python.exe scripts\smoke_test.py path\to\16k-mono.wav
```

Runs unit checks plus an end-to-end transcription of the given wav.
