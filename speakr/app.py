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
from speakr.context import get_active_app, get_screen_context
from speakr.dictionary import Dictionary
from speakr.formatter import Formatter
from speakr.injector import inject
from speakr.inputs import HotkeyListener
from speakr.learning import VocabLearner, extract_notable_tokens
from speakr.streaming import DictationSession
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
            preroll_seconds=self.config.get("preroll_seconds", default=0.4),
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
        self._session = None

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
            self.tray.set_state(
                "idle", f"{self.transcriber.model_in_use} on {self.transcriber.device_in_use}"
            )

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
        session = DictationSession(self.transcriber, self.recorder, self.config)
        self._session = session
        # Capture the target app and on-screen text in the background while
        # the user is speaking — costs the dictation nothing.
        threading.Thread(target=self._capture_context, args=(session,), daemon=True).start()
        session.start()
        self._recording = True
        self._record_started_at = time.monotonic()
        self.tray.set_state("recording")

    def _capture_context(self, session):
        context = get_active_app()
        sc = self.config.get("screen_context", default={})
        if sc.get("enabled", True):
            screen_text = get_screen_context(
                max_chars=sc.get("max_chars", 1200),
                timeout=sc.get("timeout_seconds", 1.0),
            )
            if screen_text:
                context["screen_text"] = screen_text
                session.extra_hints = extract_notable_tokens(screen_text)
        session.app_context = context

    def _end_recording(self):
        self._recording = False
        session, self._session = self._session, None
        if session is None:
            return
        session.stop()
        duration = session.duration()
        if duration < self.config.get("min_duration_seconds"):
            self.log.info("Ignoring %.2fs tap", duration)
            self.tray.set_state("idle")
            return
        self._queue.put(session)
        self.tray.set_state("processing")

    def _worker(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            session = item
            app_context = session.app_context or {}
            started = time.monotonic()
            try:
                if not self.transcriber.wait_ready(timeout=0):
                    self.tray.set_state("processing", "waiting for model")
                text = session.finalize()
                t_asr = time.monotonic()
                if text:
                    text = self.formatter.format(text, app_context)
                    text = self.dictionary.apply(text)
                    t_fmt = time.monotonic()
                    inject(
                        text,
                        method=self.config.get("injection"),
                        restore_clipboard=self.config.get("restore_clipboard"),
                    )
                    t_inj = time.monotonic()
                    self.formatter.note_result(text)
                    self.learner.observe(text)
                    self.log.info(
                        "Inserted %d chars into %s in %.2fs (asr %.2f, format %.2f, inject %.2f)",
                        len(text), app_context.get("exe") or "unknown app",
                        t_inj - started, t_asr - started, t_fmt - t_asr, t_inj - t_fmt,
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

    def toggle_screen_context(self):
        current = self.config.get("screen_context", "enabled")
        self.config.set("screen_context", "enabled", value=not current)

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
