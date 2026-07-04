"""Configuration loading/saving. Everything lives in config.json next to the app."""

import copy
import json
import logging
import logging.handlers
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DICTIONARY_PATH = ROOT / "dictionary.txt"
LEARNED_PATH = ROOT / "learned_words.json"
LOG_PATH = ROOT / "speakr.log"

IS_MAC = sys.platform == "darwin"

DEFAULTS = {
    # Push-to-talk key. Single key names use hold-to-record; combos with '+'
    # (Windows only, e.g. "ctrl+shift+space") force toggle mode. On macOS,
    # modifier-style keys are supported: fn (default), right cmd, right
    # option, right ctrl, caps lock, ...
    "hotkey": "fn" if IS_MAC else "right ctrl",
    "toggle_mode": False,
    # faster-whisper model. "auto" = large-v3-turbo on GPU, small on CPU.
    # Or pin one: tiny, base, small, medium, large-v3-turbo, large-v3, ...
    "model": "auto",
    # "auto" tries CUDA and falls back to CPU. Or "cpu" / "cuda".
    "device": "auto",
    # "auto" -> float16 on GPU, int8 on CPU
    "compute_type": "auto",
    # null = auto-detect language; or a code like "en"
    "language": None,
    "beam_size": 1,
    # "paste" (clipboard + Ctrl+V, most compatible) or "type" (simulated keystrokes)
    "injection": "paste",
    "restore_clipboard": True,
    # Keep the mic stream open between dictations (lower latency, mic indicator
    # stays on). False opens the mic only while the hotkey is held.
    "keep_mic_stream_open": True,
    "min_duration_seconds": 0.3,
    "max_duration_seconds": 120,
    # Seconds of mic audio kept in a rolling RAM buffer and prepended to each
    # recording, so words started just before the keypress aren't clipped.
    "preroll_seconds": 0.4,
    # Voice-activity threshold (0-1). Lower hears quiet speech better;
    # higher rejects more background noise.
    "vad_threshold": 0.35,
    # Long dictations: transcribe committed chunks at natural pauses while
    # you're still speaking, so release-to-text stays fast at any length.
    "streaming": {
        "enabled": True,
        "chunk_seconds": 10,
        "min_silence_seconds": 0.45,
    },
    # Read the focused control's text once per dictation (UI Automation) to
    # bias transcription toward on-screen names/jargon. Local-only, held in
    # memory for that one dictation. Windows only for now.
    "screen_context": {
        "enabled": True,
        "max_chars": 1200,
        "timeout_seconds": 1.0,
    },
    "sample_rate": 16000,
    # null = system default input device; or a sounddevice index/name
    "input_device": None,
    # Write dictated text into speakr.log (off by default for privacy)
    "log_transcripts": False,
    # Spoken layout commands: "new line", "new paragraph", "bullet point"
    "voice_commands": True,
    # Learn recurring uncommon words from your dictations (stored locally in
    # learned_words.json) and bias transcription toward them.
    "learning": {
        "enabled": True,
        "min_occurrences": 3,
        "max_hints": 40,
    },
    "formatting": {
        "enabled": True,
        "use_ollama": True,
        # Start a local `ollama serve` automatically if it isn't running
        "autostart_ollama": True,
        # Feed the last few dictations to the LLM as context (in memory only)
        "include_recent_context": True,
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "llama3.2",
        "timeout_seconds": 10,
    },
    # Tone per foreground app: casual | formal | neutral | literal.
    # "literal" skips the LLM pass entirely (good for code/terminals).
    # Keys are the process name on Windows ("slack.exe") and the lowercase
    # app name on macOS ("slack").
    "app_tones": {
        # Windows
        "slack.exe": "casual",
        "discord.exe": "casual",
        "teams.exe": "casual",
        "ms-teams.exe": "casual",
        "outlook.exe": "formal",
        "olk.exe": "formal",
        "thunderbird.exe": "formal",
        "code.exe": "literal",
        "cursor.exe": "literal",
        "windowsterminal.exe": "literal",
        "wt.exe": "literal",
        "cmd.exe": "literal",
        "powershell.exe": "literal",
        "conhost.exe": "literal",
        # macOS
        "slack": "casual",
        "discord": "casual",
        "messages": "casual",
        "microsoft teams": "casual",
        "mail": "formal",
        "microsoft outlook": "formal",
        "visual studio code": "literal",
        "cursor": "literal",
        "terminal": "literal",
        "iterm2": "literal",
        "warp": "literal",
        "ghostty": "literal",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        if self.path.exists():
            try:
                # utf-8-sig: tolerate the BOM Notepad/PowerShell like to add
                user = json.loads(self.path.read_text(encoding="utf-8-sig"))
                self.data = _merge(DEFAULTS, user)
            except (json.JSONDecodeError, OSError) as exc:
                logging.getLogger("speakr").error("Failed to read %s: %s", self.path, exc)
        else:
            self.save()

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def get(self, *keys, default=None):
        node = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def set(self, *keys, value):
        node = self.data
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
        self.save()


def setup_logging():
    logger = logging.getLogger("speakr")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    if sys.stderr is not None:  # absent under pythonw.exe
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)
    return logger
