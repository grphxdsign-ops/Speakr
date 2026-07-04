"""Speakr orchestrator: hotkey -> record -> transcribe -> format -> inject."""

import os
import queue
import subprocess
import sys
import threading
import time

from speakr import config as cfg_mod
from speakr.audio import AudioRecorder
from speakr.config import Config, setup_logging
from speakr.context import get_active_app
from speakr.dictionary import Dictionary
from speakr.formatter import Formatter
from speakr.injector import inject
from speakr.inputs import HotkeyListener
from speakr.learning import VocabLearner
from speakr.transcriber import Transcriber
from speakr.tray import Tray


def _open_path(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        os.startfile(path)


class SpeakrApp:
    def __init__(self):
        self.log = setup_logging()
        self.config = Config()
        self.dictionary = Dictionary(cfg_mod.DICTIONARY_PATH)
        self.recorder = AudioRecorder(
            sample_rate=self.config.get("sample_rate"),
            input_device=self.config.get("input_device"),
            keep_stream_open=self.config.get("keep_mic_stream_open"),
        )
        self.learner = VocabLearner(self.config, cfg_mod.LEARNED_PATH)
        self.transcriber = Transcriber(self.config, self.dictionary, self.learner)
        self.formatter = Formatter(self.config)
        self.tray = Tray(self)
        self.enabled = True
        self._recording = False
        self._record_started_at = 0.0
        self._queue: queue.Queue = queue.Queue()
        self._listener = None

    # ----- lifecycle -------------------------------------------------------

    def start(self):
        self.log.info("Speakr starting (hotkey=%r)", self.config.get("hotkey"))
        self.transcriber.load_async()
        threading.Thread(target=self._announce_ready, daemon=True).start()
        threading.Thread(target=self.formatter.ensure_ollama, daemon=True).start()
        try:
            self.recorder.start()
        except Exception as exc:
            self.log.error("Could not open microphone: %s", exc)
            self.tray.set_state("error", "mic unavailable — check Windows mic permissions")
        self._register_hotkey()
        threading.Thread(target=self._worker, name="pipeline", daemon=True).start()
        self.tray.run()  # blocks until quit

    def _announce_ready(self):
        if self.transcriber.wait_ready(timeout=600) and not self._recording:
            self.tray.set_state("idle", f"model on {self.transcriber.device_in_use}")

    def quit(self):
        self.log.info("Speakr shutting down")
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        self.recorder.shutdown()
        self._queue.put(None)
        self.tray.stop()

    # ----- hotkey ----------------------------------------------------------

    def _register_hotkey(self):
        self._listener = HotkeyListener(
            self.config.get("hotkey"),
            self.config.get("toggle_mode"),
            on_press=self._hotkey_down,
            on_release=self._hotkey_up,
            on_toggle=self._toggle_recording,
        )
        self._listener.start()

    def _hotkey_down(self):
        if not self._recording:  # key auto-repeat sends extra downs
            self._begin_recording()

    def _hotkey_up(self):
        if self._recording:
            self._end_recording()

    def _toggle_recording(self):
        if self._recording:
            self._end_recording()
        else:
            self._begin_recording()

    # ----- record / process ------------------------------------------------

    def _begin_recording(self):
        if not self.enabled:
            return
        try:
            self.recorder.start_recording()
        except Exception as exc:
            self.log.error("Mic error: %s", exc)
            self.tray.set_state("error", "mic unavailable")
            return
        self._recording = True
        self._record_started_at = time.monotonic()
        self.tray.set_state("recording")

    def _end_recording(self):
        self._recording = False
        audio = self.recorder.stop_recording()
        duration = len(audio) / self.config.get("sample_rate")
        if duration < self.config.get("min_duration_seconds"):
            self.log.info("Ignoring %.2fs tap", duration)
            self.tray.set_state("idle")
            return
        max_dur = self.config.get("max_duration_seconds")
        if duration > max_dur:
            audio = audio[: int(max_dur * self.config.get("sample_rate"))]
        # Capture the target app now, while its window still has focus.
        app_context = get_active_app()
        self._queue.put((audio, app_context))
        self.tray.set_state("processing")

    def _worker(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            audio, app_context = item
            started = time.monotonic()
            try:
                if not self.transcriber.wait_ready(timeout=0):
                    self.tray.set_state("processing", "waiting for model")
                text = self.transcriber.transcribe(audio, self.config.get("sample_rate"))
                if text:
                    text = self.formatter.format(text, app_context)
                    text = self.dictionary.apply(text)
                    inject(
                        text,
                        method=self.config.get("injection"),
                        restore_clipboard=self.config.get("restore_clipboard"),
                    )
                    self.formatter.note_result(text)
                    self.learner.observe(text)
                    self.log.info(
                        "Inserted %d chars into %s in %.2fs",
                        len(text), app_context.get("exe") or "unknown app",
                        time.monotonic() - started,
                    )
            except Exception as exc:
                self.log.exception("Pipeline error: %s", exc)
            finally:
                if not self._recording:
                    self.tray.set_state("recording" if self._recording else "idle")

    # ----- tray actions ----------------------------------------------------

    def toggle_enabled(self):
        self.enabled = not self.enabled
        self.tray.set_state("idle" if self.enabled else "disabled")

    def toggle_formatting(self):
        current = self.config.get("formatting", "enabled")
        self.config.set("formatting", "enabled", value=not current)

    def toggle_learning(self):
        current = self.config.get("learning", "enabled")
        self.config.set("learning", "enabled", value=not current)

    def change_model(self, name):
        self.tray.set_state("loading", f"switching to {name}")
        self.transcriber.change_model(name)
        threading.Thread(target=self._announce_ready, daemon=True).start()

    def reload_config(self):
        self.config.load()
        self.dictionary.load()
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._register_hotkey()
        self.log.info("Config and dictionary reloaded")

    def open_config(self):
        _open_path(cfg_mod.CONFIG_PATH)

    def open_dictionary(self):
        _open_path(cfg_mod.DICTIONARY_PATH)

    def open_log(self):
        _open_path(cfg_mod.LOG_PATH)


_instance_lock = None  # must outlive the process for the lock to hold


def _acquire_single_instance() -> bool:
    """Two instances would mean two hotkey hooks and doubled text injection."""
    global _instance_lock
    if sys.platform == "win32":
        import ctypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        _instance_lock = kernel32.CreateMutexW(None, False, "SpeakrSingleInstance")
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    import fcntl

    _instance_lock = open(cfg_mod.ROOT / ".speakr.lock", "w")
    try:
        fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main():
    if not _acquire_single_instance():
        setup_logging().warning("Speakr is already running — exiting duplicate instance")
        return
    SpeakrApp().start()


if __name__ == "__main__":
    main()
