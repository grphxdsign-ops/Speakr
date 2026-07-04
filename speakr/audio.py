"""Microphone capture. Audio only ever lives in process memory."""

import logging
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd

log = logging.getLogger("speakr.audio")


class AudioRecorder:
    def __init__(self, sample_rate=16000, input_device=None, keep_stream_open=True,
                 preroll_seconds=0.4):
        self.sample_rate = sample_rate
        self.input_device = input_device
        self.keep_stream_open = keep_stream_open
        # Rolling pre-roll (RAM only, continuously discarded): people start
        # talking a beat before the key lands; without this the first
        # syllable is clipped. Needs the stream to be open to exist.
        self.preroll_samples = int(preroll_seconds * sample_rate)
        self._preroll: deque = deque()
        self._preroll_total = 0
        self._stream = None
        self._frames = []
        self._recorded_total = 0
        self._recording = False
        self._last_frame_at = 0.0  # monotonic time of the last mic callback
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        self._last_frame_at = time.monotonic()
        if status:
            log.warning("Audio stream status: %s", status)
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())
                self._recorded_total += len(indata)
            elif self.preroll_samples > 0:
                self._preroll.append(indata.copy())
                self._preroll_total += len(indata)
                while self._preroll_total - len(self._preroll[0]) >= self.preroll_samples:
                    self._preroll_total -= len(self._preroll.popleft())

    def _open_stream(self):
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.input_device,
            callback=self._callback,
        )
        self._stream.start()
        self._last_frame_at = time.monotonic()
        log.info("Mic stream opened (device=%s)", self.input_device or "default")

    def _close_stream(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def start(self):
        """Called once at app startup when keep_stream_open is on."""
        if self.keep_stream_open:
            self._open_stream()

    def _stream_is_stale(self) -> bool:
        """A long-open stream can die silently when the Windows default audio
        device changes (headset plugged in, a game grabbing the device) — the
        callback just stops firing, so recordings capture only stale pre-roll.
        Observed in the wild: multi-second dictations arriving as 0.7-1.0s of
        nothing. Detect it by checking whether frames are still flowing."""
        return (
            self._stream is not None
            and time.monotonic() - self._last_frame_at > 1.0
        )

    def reset_stream(self):
        """Force-close so the next open re-binds to the CURRENT default device."""
        log.warning("Resetting mic stream (stale or unhealthy)")
        with self._lock:
            self._preroll.clear()
            self._preroll_total = 0
        self._close_stream()
        if self.keep_stream_open:
            try:
                self._open_stream()
            except Exception as exc:
                log.error("Mic stream reopen failed: %s", exc)

    def start_recording(self):
        if self._stream_is_stale():
            log.warning(
                "Mic stream stale (no frames for %.1fs) — reopening to pick up "
                "the current default device",
                time.monotonic() - self._last_frame_at,
            )
            self._close_stream()  # _open_stream below re-binds to current default
        with self._lock:
            self._frames = list(self._preroll)
            self._recorded_total = self._preroll_total
            self._preroll.clear()
            self._preroll_total = 0
        self._open_stream()
        self._recording = True

    def recorded_samples(self) -> int:
        """Cheap poll of how much audio the current recording holds."""
        with self._lock:
            return self._recorded_total

    def snapshot(self) -> np.ndarray:
        """Copy of everything recorded so far, without stopping."""
        with self._lock:
            frames = list(self._frames)
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames).flatten()

    def stop_recording(self) -> np.ndarray:
        self._recording = False
        if not self.keep_stream_open:
            self._close_stream()
        with self._lock:
            frames, self._frames = self._frames, []
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames).flatten()

    def shutdown(self):
        self._recording = False
        self._close_stream()
