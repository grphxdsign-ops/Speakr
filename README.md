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
  them. To update: `git pull && bash package_mac.sh` and replace the app.
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
| `injection` | `"paste"` | `"paste"` = clipboard + Ctrl+V (most compatible). `"type"` = simulated keystrokes. |
| `keep_mic_stream_open` | `true` | Lower latency, but the mic indicator stays on. Set `false` to open the mic only while the hotkey is held. |
| `formatting.use_ollama` | `true` | Used only if Ollama is running at `ollama_url`. Otherwise rule-based cleanup applies. |
| `formatting.autostart_ollama` | `true` | If Ollama is installed but not running, Speakr starts `ollama serve` itself at launch. |
| `formatting.ollama_model` | `"llama3.2"` | Any local model you've pulled. `llama3.1:8b` is also on this machine if you want a bigger formatter. |
| `formatting.include_recent_context` | `true` | Give the LLM your last few dictations (memory only) for continuity. |
| `voice_commands` | `true` | "new line" / "new paragraph" / "bullet point" spoken commands. |
| `streaming` | on, 10s chunks | Mid-speech chunked transcription for long dictations. |
| `screen_context` | on, 1200 chars | Focused-field text capture for spelling context (Windows). Note: the first query can switch a Chromium-based app (Chrome, Slack, Discord) into accessibility mode, a small ongoing cost in that app — disable here if you notice it. |
| `learning.enabled` | `true` | Vocabulary learning; `min_occurrences` (3) and `max_hints` (40) tune it. |
| `app_tones` | see file | Per-app tone: `casual` / `formal` / `neutral` / `literal`. `literal` (code editors, terminals) skips the LLM pass so nothing rewrites your commands. |
| `log_transcripts` | `false` | Keep dictated text out of `speakr.log` unless you opt in. |

Privacy note: `learned_words.json` contains single words you've dictated
repeatedly (never sentences). Delete the file anytime to reset learning.

After editing, use tray → **Reload config**.

## Personal dictionary (`dictionary.txt`)

One entry per line:

```
Kubernetes            # bias transcription toward this spelling
jira => Jira          # hard replacement after transcription
```

## AI formatting

The LLM polish (self-corrections, lists, per-app tone) uses Ollama with
`llama3.2` (already pulled). Speakr starts Ollama automatically if it isn't
running, and re-detects it once a minute if it comes up later. Without it,
rule-based cleanup still strips fillers, fixes spacing/capitalization, and
honors the spoken layout commands.

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
