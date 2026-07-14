# Speakr — agent notes

Speakr is a private, fully-local voice-dictation app for Windows and macOS (a
Wispr Flow replacement): hold a hotkey (Right Ctrl on Windows, `fn` on Mac),
speak, release, and cleaned-up text is injected at the cursor. Pipeline:
hotkey capture -> `faster-whisper` transcription -> optional local Ollama LLM
polish (else rule-based cleanup) -> personal dictionary replacements
(`dictionary.txt`, `learned_words.json`) -> text injection.

## The core invariant — read this first

**Nothing ever leaves this machine.** No telemetry, no analytics, no crash
reporting, no cloud calls. The only network activity, ever, is:
1. A one-time Hugging Face model download on first run.
2. Local requests to Ollama on `127.0.0.1` (the user's own local process).

Audio is never written to disk beyond in-memory buffers, and transcript text
is never sent anywhere off-device. Treat this as a hard constraint, not a
preference.

## Hard boundaries

- **Never add a network call that sends audio or transcript content off the
  device** — no cloud ASR, no cloud LLM fallback, no remote logging/metrics,
  no "phone home" of any kind. If a feature seems to need one, it's the wrong
  design for this app.
- **Never make Ollama a hard dependency.** `formatting.use_ollama` must be
  able to be false, or Ollama simply not running, and the app still works —
  rule-based cleanup (filler stripping, spacing/capitalization, spoken layout
  commands) is the permanent fallback, not a stopgap. Any new LLM-dependent
  feature needs a non-LLM degrade path.
- Don't add required cloud accounts, API keys, or SaaS dependencies.

## Entry points

- `speakr/__main__.py` -> `speakr.app.main()` — process entry point.
- `speakr/app.py` — `SpeakrApp`, the orchestrator (hotkey -> record ->
  transcribe -> format -> inject).
- `speakr/audio.py` (mic capture + self-healing), `speakr/transcriber.py`
  (faster-whisper), `speakr/streaming.py` (chunked transcription),
  `speakr/formatter.py` (Ollama polish + rule-based fallback),
  `speakr/dictionary.py` / `speakr/learning.py` (vocabulary),
  `speakr/context.py` (foreground app/window + screen-context spelling
  hints, Edit Mode selection capture), `speakr/injector.py` (paste/type
  injection), `speakr/inputs.py` + `win_input.py`/`mac_input.py` (hotkey
  listeners), `speakr/tray.py` (tray/menu-bar UI), `speakr/config.py`
  (loads `config.json`).

## Running it

- Windows: `run.bat` (creates `.venv`, installs `requirements.txt`, launches
  windowless via `pythonw`). `run_debug.bat` runs the same but in a console
  with live logs — use this whenever you need to see what's happening.
- macOS (Terminal): `run.sh` / `run_debug.sh` (same split — debug variant
  keeps the console attached, no `nohup`/backgrounding).
- macOS (packaged app): `package_mac.sh` builds `dist/Speakr.app`.
- GPU/CUDA transcription is optional: `pip install -r requirements-gpu.txt`
  on top of `requirements.txt`. Absence or a broken CUDA runtime silently
  falls back to CPU — don't make GPU support load-bearing.
- Smoke test: `.venv\Scripts\python.exe scripts\smoke_test.py path\to\16k-mono.wav`.
- Runtime config lives in `config.json` (hotkey, model/device selection,
  formatting/Ollama settings, per-app tones, learning thresholds, etc.).

## `training/` — read before touching fine-tuning again

Two completed LoRA fine-tune rounds on Qwen2.5-3B-Instruct, both against the
`llama3.1:8b` baseline used in production formatting — **neither beat the
baseline.** Round 1 had a methodology bug (in-distribution eval split
saturated to near-zero loss alongside training loss, masking overfitting).
Round 2 fixed that (genuinely held-out eval split, early stopping on
`eval_loss`) and still didn't beat `llama3.1:8b` on the hard-case suite /
held-out teacher-agreement metrics in `training/evaluate.py`. Read
`train_lora.py`, `evaluate.py`, and the git history (`562fa9b`, `56d8f61`)
before proposing another fine-tune attempt — don't re-run the same approach
expecting a different result without understanding why it lost.

## Known low-priority TODO

`learned_words.json` (`speakr/learning.py`, `VocabLearner._entries`) grows
without bound — every notable token ever seen gets an entry, and nothing
evicts old/rare ones (`max_hints` only caps how many are *used* as hints, not
how many are *stored*). An LRU-style cap on stored entries would be a
reasonable improvement, but it's not an active bug — don't treat it as
urgent unless asked.
