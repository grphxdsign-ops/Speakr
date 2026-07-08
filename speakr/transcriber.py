"""Local ASR via faster-whisper. Model weights download once from Hugging Face;
audio never leaves the machine."""

from __future__ import annotations

import logging
import os
import sys
import sysconfig
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger("speakr.transcriber")

_nvidia_dlls_exposed = False


def _expose_nvidia_dlls():
    """Make pip-installed CUDA runtimes (nvidia-cublas-cu12, nvidia-cudnn-cu12)
    findable by ctranslate2, which loads them with plain LoadLibrary."""
    global _nvidia_dlls_exposed
    if _nvidia_dlls_exposed:
        return
    _nvidia_dlls_exposed = True
    nvidia_dir = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    if not nvidia_dir.is_dir():
        return
    for bin_dir in nvidia_dir.glob("*/bin"):
        try:
            os.add_dll_directory(str(bin_dir))
        except OSError:
            pass
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    log.info("Exposed NVIDIA DLL dirs from %s", nvidia_dir)


def _resolve_model_name(name: str, device: str) -> str:
    """"auto" picks the best model the hardware can run at dictation speed:
    large-v3-turbo needs a GPU; small is the practical ceiling on CPU."""
    if name != "auto":
        return name
    return "large-v3-turbo" if device == "cuda" else "small"


class Transcriber:
    def __init__(self, config, dictionary, learner=None):
        self.config = config
        self.dictionary = dictionary
        self.learner = learner
        self._model = None
        self._ready = threading.Event()
        self._load_lock = threading.Lock()
        # Serializes inference: mid-dictation chunk commits and the final
        # pass may otherwise overlap on the same ctranslate2 model.
        self._infer_lock = threading.Lock()
        self.device_in_use = None
        self.model_in_use = None

    def load_async(self):
        threading.Thread(target=self.load, name="model-loader", daemon=True).start()

    def load(self):
        with self._load_lock:
            self._ready.clear()
            model_name = self.config.get("model")
            device = self.config.get("device")
            compute_type = self.config.get("compute_type")
            self._model = self._create_model(model_name, device, compute_type)
            self._ready.set()

    def _create_model(self, model_name, device, compute_type):
        from faster_whisper import WhisperModel

        cpu_threads = min(8, os.cpu_count() or 4)
        attempts = []
        if device in ("auto", "cuda") and sys.platform != "darwin":  # no CUDA on macOS
            attempts.append(("cuda", "float16" if compute_type == "auto" else compute_type))
        if device in ("auto", "cpu"):
            attempts.append(("cpu", "int8" if compute_type == "auto" else compute_type))

        _expose_nvidia_dlls()
        last_exc = None
        for dev, ctype in attempts:
            resolved = _resolve_model_name(model_name, dev)
            try:
                log.info("Loading model %s on %s (%s)...", resolved, dev, ctype)
                model = WhisperModel(resolved, device=dev, compute_type=ctype, cpu_threads=cpu_threads)
                # Missing CUDA DLLs only surface at inference time, so run a
                # short silent warm-up before committing to this device.
                segments, _ = model.transcribe(np.zeros(8000, dtype=np.float32), beam_size=1)
                list(segments)
                self.device_in_use = dev
                self.model_in_use = resolved
                log.info("Model %s ready on %s", resolved, dev)
                return model
            except Exception as exc:
                last_exc = exc
                log.warning("Could not load %s on %s: %s", resolved, dev, exc)
        raise RuntimeError(f"Failed to load model {model_name}: {last_exc}")

    def wait_ready(self, timeout=None) -> bool:
        return self._ready.wait(timeout)

    def _initial_prompt(self, extra_hints=None, prior_text="") -> str | None:
        """Vocabulary bias: manual dictionary entries first, then on-screen
        vocabulary for this dictation, then learned words. prior_text carries
        continuity across streaming chunk boundaries."""
        manual = list(self.dictionary.hints)
        seen = {w.lower() for w in manual}
        extra = [h for h in (extra_hints or []) if h.lower() not in seen]
        learned = self.learner.hints(exclude=manual + extra) if self.learner else []
        words = (manual + extra + learned)[:100]
        parts = []
        if words:
            parts.append("Glossary: " + ", ".join(words) + ".")
        if prior_text:
            parts.append(prior_text[-200:])
        return " ".join(parts) or None

    def _beam_size(self) -> int:
        """"auto" = beam 5 on GPU (better word accuracy, still ~fast) and
        greedy on CPU (beam search there costs real seconds)."""
        configured = self.config.get("beam_size", default="auto")
        if configured == "auto":
            return 5 if self.device_in_use == "cuda" else 1
        return int(configured)

    def transcribe(self, audio, sample_rate=16000, extra_hints=None, prior_text="") -> str:
        self._ready.wait()
        prompt = self._initial_prompt(extra_hints, prior_text)
        with self._infer_lock:
            return self._transcribe_locked(audio, sample_rate, prompt)

    def _transcribe_locked(self, audio, sample_rate, prompt) -> str:
        segments, info = self._model.transcribe(
            audio,
            language=self.config.get("language"),
            beam_size=self._beam_size(),
            vad_filter=True,
            # Gentler VAD than the defaults: don't drop quiet speech, and pad
            # segment edges so soft starts/ends aren't clipped.
            vad_parameters={
                "threshold": self.config.get("vad_threshold", default=0.35),
                "min_speech_duration_ms": 100,
                "speech_pad_ms": 400,
            },
            initial_prompt=prompt,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        if self.config.get("log_transcripts"):
            log.info("Transcribed %.1fs of audio (lang=%s): %r", len(audio) / sample_rate, info.language, text)
        else:
            log.info("Transcribed %.1fs of audio (lang=%s, %d chars)", len(audio) / sample_rate, info.language, len(text))
        return text

    def change_model(self, model_name):
        self.config.set("model", value=model_name)
        self.load_async()
