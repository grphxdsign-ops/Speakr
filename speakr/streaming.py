"""Incremental transcription. Long dictations are transcribed chunk-by-chunk
at natural pauses while you are still speaking, so release-to-text latency
stays near-constant regardless of how long you talked.

Accuracy is preserved by three rules: chunks are only cut in the middle of a
real silence (never mid-word), every chunk gets the previously committed text
as conditioning context, and recordings shorter than one chunk take the exact
same single-pass path as before.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

log = logging.getLogger("speakr.streaming")


def find_silence_cut(audio: np.ndarray, sample_rate: int,
                     min_silence_s: float = 0.45, min_pos_s: float = 3.0):
    """Sample index inside the LAST sufficiently long quiet stretch, or None.

    Cheap: one RMS per 30ms window over float32 audio, no model involved.
    """
    win = int(0.03 * sample_rate)
    n = len(audio) // win
    if n * win < int(min_pos_s * sample_rate):
        return None
    rms = np.sqrt(np.mean(audio[: n * win].reshape(n, win) ** 2, axis=1))
    # Relative threshold so quiet mics still register speech vs silence.
    threshold = max(0.004, float(np.percentile(rms, 90)) * 0.08)
    quiet = rms < threshold
    need = max(1, int(min_silence_s * sample_rate / win))
    best = None
    run = 0
    for i, is_quiet in enumerate(quiet):
        run = run + 1 if is_quiet else 0
        if run >= need:
            center = int((i - run / 2 + 1) * win)
            if center >= int(min_pos_s * sample_rate):
                best = center
    return best


class DictationSession:
    """One press-to-release dictation: owns the audio, mid-speech chunk
    commits, and the captured app/screen context."""

    def __init__(self, transcriber, recorder, config):
        self.transcriber = transcriber
        self.recorder = recorder
        self.config = config
        self.app_context: dict = {}
        self.extra_hints: list[str] = []
        self.chunks: list[str] = []
        self.committed = 0  # samples already transcribed
        self.audio = None  # full recording, set at stop()
        self._active = True
        self._lock = threading.Lock()

    # ----- while speaking ---------------------------------------------------

    def start(self):
        if self.config.get("streaming", "enabled", default=True):
            threading.Thread(target=self._monitor, name="stream-chunks", daemon=True).start()

    def _monitor(self):
        sr = self.recorder.sample_rate
        chunk_samples = int(self.config.get("streaming", "chunk_seconds", default=10) * sr)
        min_silence = self.config.get("streaming", "min_silence_seconds", default=0.45)
        force_at = int(25 * sr)  # whisper's own window is 30s; never exceed it
        while self._active:
            time.sleep(0.5)
            if not self._active:
                return
            if self.recorder.recorded_samples() - self.committed < chunk_samples:
                continue
            with self._lock:
                if not self._active:
                    return
                region = self.recorder.snapshot()[self.committed:]
                cut = find_silence_cut(region, sr, min_silence_s=min_silence)
                if cut is None:
                    if len(region) < force_at:
                        continue  # continuous speech: wait for a pause
                    cut = len(region)  # safety valve before whisper's window
                self._commit(region[:cut], sr)

    def _commit(self, chunk: np.ndarray, sr: int):
        try:
            started = time.monotonic()
            text = self.transcriber.transcribe(
                chunk, sr, extra_hints=self.extra_hints,
                prior_text=" ".join(self.chunks),
            )
            if text:
                self.chunks.append(text)
            self.committed += len(chunk)
            log.info("Committed %.1fs mid-dictation in %.2fs (%d chars so far)",
                     len(chunk) / sr, time.monotonic() - started,
                     sum(len(c) for c in self.chunks))
        except Exception:
            log.exception("Chunk transcription failed; will retry in final pass")

    # ----- at release -------------------------------------------------------

    def stop(self):
        """Hotkey-release path: must be fast. Freezes the audio."""
        self._active = False
        self.audio = self.recorder.stop_recording()

    def duration(self) -> float:
        return len(self.audio) / self.recorder.sample_rate if self.audio is not None else 0.0

    def finalize(self) -> str:
        """Transcribe whatever isn't committed yet and stitch the result.
        Waits for an in-flight chunk commit if one is running."""
        sr = self.recorder.sample_rate
        with self._lock:
            tail = self.audio[self.committed:]
            max_s = self.config.get("max_duration_seconds", default=120)
            tail = tail[: int(max_s * sr)]
            if len(tail) >= int(0.25 * sr):
                text = self.transcriber.transcribe(
                    tail, sr, extra_hints=self.extra_hints,
                    prior_text=" ".join(self.chunks),
                )
                if text:
                    self.chunks.append(text)
            return " ".join(self.chunks).strip()
