from __future__ import annotations

import queue
import threading
import time
import unittest
from unittest import mock

import numpy as np

from speakr.app import SpeakrApp
from speakr.interface_state import InterfaceState


class _Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, *keys, default=None):
        node = self.values
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _Session:
    job_id = 2

    @staticmethod
    def stop():
        return None

    @staticmethod
    def duration():
        return 1.0


class AppLifecycleTests(unittest.TestCase):
    def test_successful_normal_recording_clears_both_microphone_issues(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app.enabled = True
        app._practice_recording = False
        app._recording = False
        app._shutting_down = False
        app._next_job_id = mock.Mock(return_value=4)
        app._capture_context = mock.Mock()
        app._legacy_state = mock.Mock()
        app.interface_state = InterfaceState({"availability": "ready"})
        app.interface_state.latch_issue(
            "microphone_reconnected",
            "Microphone reconnected. Please try again.",
            "start_practice",
        )
        app.config = _Config({"hotkey_exclude_apps": []})
        app.recorder = mock.Mock()
        app.transcriber = mock.Mock()
        app.log = mock.Mock()

        with mock.patch("speakr.app.DictationSession") as session_type, mock.patch(
            "speakr.app.threading.Thread"
        ):
            app._begin_recording()

        self.assertIsNone(app.interface_state.snapshot()["last_issue"])
        self.assertEqual(app.interface_state.snapshot()["capture"], "listening")
        session_type.return_value.start.assert_called_once()

    def test_success_keeps_an_unapplied_microphone_restart_notice(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app.enabled = True
        app.interface_state = InterfaceState({"availability": "ready"})
        app.interface_state.latch_issue(
            "restart_required",
            "Restart Speakr to use the new microphone setting.",
            "dismiss",
            blocking=False,
        )
        app._schedule_ready = mock.Mock()

        app._finish_success(7, "success")

        self.assertEqual(
            app.interface_state.snapshot()["last_issue"]["code"],
            "restart_required",
        )

    def test_older_job_success_cannot_clear_a_new_microphone_failure(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app.enabled = True
        app.interface_state = InterfaceState(
            {
                "availability": "ready",
                "pipeline": "formatting",
                "pipeline_job_id": 1,
            }
        )
        app.interface_state.latch_issue(
            "microphone_unavailable",
            "Microphone access is needed.",
            "open_system_settings",
        )
        app._schedule_ready = mock.Mock()

        app._finish_success(1, "success")

        snapshot = app.interface_state.snapshot()
        self.assertEqual(snapshot["availability"], "needs_attention")
        self.assertEqual(snapshot["last_issue"]["code"], "microphone_unavailable")

    def test_pipeline_error_retires_hud_state_but_keeps_recovery_issue(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app.enabled = True
        app.interface_state = InterfaceState({"availability": "ready"})
        app._schedule_pipeline_settle = mock.Mock()

        app._finish_error(
            9,
            "pipeline_failed",
            "Text was not inserted.",
            "open_log",
        )

        snapshot = app.interface_state.snapshot()
        self.assertEqual(snapshot["pipeline"], "error")
        self.assertEqual(snapshot["pipeline_job_id"], 9)
        self.assertEqual(snapshot["last_issue"]["code"], "pipeline_failed")
        app._schedule_pipeline_settle.assert_called_once_with(
            9, delay=5.0, expected=("error",)
        )

        app._schedule_pipeline_settle = mock.Mock()
        self.assertTrue(app._retire_pipeline_job(9, {"error"}))
        snapshot = app.interface_state.snapshot()
        self.assertEqual(snapshot["pipeline"], "idle")
        self.assertEqual(snapshot["pipeline_job_id"], 0)
        self.assertEqual(snapshot["last_issue"]["code"], "pipeline_failed")

    def test_model_readiness_does_not_hide_a_microphone_blocker(self):
        class Transcriber:
            model_in_use = "small"
            device_in_use = "cpu"
            compute_type_in_use = "int8"

            @staticmethod
            def load():
                return None

        app = SpeakrApp.__new__(SpeakrApp)
        app.transcriber = Transcriber()
        app.config = _Config({"model": "auto"})
        app.enabled = True
        app._shutting_down = False
        app.interface_state = InterfaceState({"availability": "starting"})
        app.interface_state.latch_issue(
            "microphone_unavailable",
            "Microphone access is needed.",
            "open_system_settings",
        )
        app._legacy_state = mock.Mock()
        app._notify_settings = mock.Mock()

        app._load_model()

        snapshot = app.interface_state.snapshot()
        self.assertEqual(snapshot["availability"], "needs_attention")
        self.assertEqual(snapshot["pipeline"], "idle")
        self.assertEqual(snapshot["last_issue"]["code"], "microphone_unavailable")
        self.assertEqual(snapshot["compute_type"], "int8")

    def test_device_change_reloads_the_local_transcriber(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._recording = False
        app._practice_recording = False
        app._pipeline_busy = mock.Mock(return_value=False)
        app.interface_state = InterfaceState({"availability": "ready", "device": "cpu"})
        app.config = mock.Mock()
        app._notify_settings = mock.Mock()
        app._load_model = mock.Mock()

        with mock.patch("speakr.app.threading.Thread") as thread_type:
            self.assertTrue(app.set_setting("device", "cuda"))

        app.config.set.assert_called_once_with("device", value="cuda")
        thread_type.assert_called_once()
        thread_type.return_value.start.assert_called_once()
        snapshot = app.interface_state.snapshot()
        self.assertEqual(snapshot["pipeline"], "waiting_model")
        self.assertEqual(snapshot["device"], "unknown")

    def test_cleanup_path_requires_enabled_reachable_local_ollama(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app.formatter = mock.Mock()
        app.formatter._ollama_ok = True

        app.config = _Config(
            {"formatting": {"enabled": False, "use_ollama": True}}
        )
        self.assertEqual(app._current_cleanup_path(), "rules")

        app.config = _Config(
            {"formatting": {"enabled": True, "use_ollama": True}}
        )
        self.assertEqual(app._current_cleanup_path(), "ollama")
        app.formatter._ollama_ok = False
        self.assertEqual(app._current_cleanup_path(), "rules")

    def test_hotkey_capture_has_no_timeout_and_escape_cancels(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._capturing_hotkey = False
        app._recording = False
        app._pending_hotkey = "old"
        app._hotkey_cancel = None
        app._pipeline_busy = lambda: False
        app._stop_hotkey_listener = mock.Mock()
        app._register_hotkey = mock.Mock()
        app._notify_settings = mock.Mock()
        app.interface_state = InterfaceState({"availability": "ready"})
        finished = threading.Event()
        captured_timeouts = []

        def capture(timeout, cancel_event=None):
            captured_timeouts.append(timeout)
            return "esc"

        with mock.patch("speakr.app.capture_next_key", side_effect=capture):
            self.assertTrue(app.begin_hotkey_capture(lambda _value: finished.set()))
            self.assertTrue(finished.wait(1.0))

        self.assertEqual(captured_timeouts, [None])
        self.assertIsNone(app.pending_hotkey)
        self.assertFalse(app.capturing_hotkey)
        app._register_hotkey.assert_called_once()

    def test_queued_capture_does_not_overwrite_running_pipeline_job(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._recording = True
        app._session = _Session()
        app._record_started_at = time.monotonic() - 1.0
        app._capture_job_id = 2
        app._queue = queue.Queue()
        app.config = _Config({"min_duration_seconds": 0.3})
        app.interface_state = InterfaceState(
            {
                "availability": "ready",
                "capture": "listening",
                "capture_job_id": 2,
                "pipeline": "formatting",
                "pipeline_job_id": 1,
                "queue_depth": 0,
            }
        )
        app._legacy_state = lambda *_args: None

        app._end_recording()

        snapshot = app.interface_state.snapshot()
        self.assertEqual(snapshot["pipeline"], "formatting")
        self.assertEqual(snapshot["pipeline_job_id"], 1)
        self.assertEqual(snapshot["queue_depth"], 1)

    def test_practice_is_in_memory_only_and_never_enters_global_state(self):
        calls = []

        class Recorder:
            sample_rate = 16_000

            @staticmethod
            def stop_recording():
                return np.ones(8_000, dtype=np.float32)

            @staticmethod
            def current_level():
                return 0.2

        class Transcriber:
            @staticmethod
            def transcribe(audio, sample_rate, **kwargs):
                calls.append((len(audio), sample_rate, kwargs))
                return "hello Speakr"

        class Dictionary:
            @staticmethod
            def apply(text):
                return text

        app = SpeakrApp.__new__(SpeakrApp)
        app._practice_lock = threading.RLock()
        app._practice_generation = 4
        app._practice_recording = True
        app._practice = app._empty_practice()
        app._practice["active"] = True
        app._practice_subscribers = []
        app.recorder = Recorder()
        app.transcriber = Transcriber()
        app.dictionary = Dictionary()
        app.formatter = mock.Mock()
        app.learner = mock.Mock()
        app.config = _Config({"voice_commands": False})
        app.interface_state = InterfaceState({"availability": "ready"})
        app.log = mock.Mock()

        with mock.patch("speakr.app.inject") as injection, mock.patch(
            "speakr.app.read_selection_via_clipboard"
        ) as clipboard_read, mock.patch(
            "speakr.app.get_selected_text"
        ) as selection_read, mock.patch(
            "speakr.app.get_screen_context"
        ) as screen_read:
            self.assertTrue(app.stop_practice())
            deadline = time.monotonic() + 2.0
            while app.practice_snapshot()["processing"] and time.monotonic() < deadline:
                time.sleep(0.01)

        practice = app.practice_snapshot()
        self.assertEqual(practice["heard"], "hello Speakr")
        self.assertEqual(practice["wouldType"], "Hello Speakr")
        self.assertEqual(calls[0][2], {"allow_text_log": False})
        injection.assert_not_called()
        clipboard_read.assert_not_called()
        selection_read.assert_not_called()
        screen_read.assert_not_called()
        app.formatter.note_result.assert_not_called()
        app.formatter.format.assert_not_called()
        app.learner.observe.assert_not_called()
        state = app.interface_state.snapshot()
        self.assertNotIn("heard", state)
        self.assertNotIn("wouldType", state)
        self.assertNotIn("transcript", state)

        app.navigate("home")
        self.assertFalse(app.practice_snapshot()["hasResult"])
        self.assertEqual(app.practice_snapshot()["heard"], "")

    def test_busy_practice_start_explains_why_it_did_not_begin(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._practice_lock = threading.RLock()
        app._practice = app._empty_practice()
        app._practice_recording = False
        app._recording = True
        app._practice_subscribers = []
        app._pipeline_busy = mock.Mock(return_value=False)

        self.assertFalse(app.start_practice())

        practice = app.practice_snapshot()
        self.assertFalse(practice["active"])
        self.assertIn("current local dictation", practice["message"])

    def test_practice_cannot_enter_transcription_until_model_is_ready(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._practice_lock = threading.RLock()
        app._practice = app._empty_practice()
        app._practice_recording = False
        app._recording = False
        app._practice_subscribers = []
        app._pipeline_busy = mock.Mock(return_value=False)
        app.transcriber = mock.Mock()
        app.transcriber.wait_ready.return_value = False
        app.recorder = mock.Mock()

        self.assertFalse(app.start_practice())

        app.recorder.start_recording.assert_not_called()
        self.assertIn("speech model is not ready", app.practice_snapshot()["message"])

    def test_setting_validation_rejects_untyped_values_and_busy_mutations(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._recording = False
        app._practice_recording = False
        app.interface_state = InterfaceState({"availability": "ready"})
        app.config = mock.Mock()
        app._notify_settings = mock.Mock()
        app._pipeline_busy = mock.Mock(return_value=False)

        self.assertFalse(app.set_setting("toggle_mode", "false"))
        self.assertFalse(app.set_setting("sample_rate", True))
        app.config.set.assert_not_called()

        app._recording = True
        self.assertFalse(app.set_setting("toggle_mode", True))
        app.config.set.assert_not_called()
        self.assertEqual(
            app.interface_state.snapshot()["last_issue"]["code"],
            "busy_setting",
        )

    def test_vocabulary_change_is_blocked_with_inline_issue_during_capture(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._practice_lock = threading.RLock()
        app._practice = app._empty_practice()
        app._practice_recording = False
        app._recording = True
        app._pipeline_busy = mock.Mock(return_value=False)
        app.interface_state = InterfaceState({"availability": "ready"})
        app.dictionary = mock.Mock()

        self.assertFalse(app.add_word("ExampleName"))

        app.dictionary.add_hint.assert_not_called()
        issue = app.interface_state.snapshot()["last_issue"]
        self.assertEqual(issue["code"], "busy_setting")
        self.assertFalse(issue["blocking"])

    def test_clearing_processing_practice_zeros_audio_and_discards_late_text(self):
        entered = threading.Event()
        release = threading.Event()

        class Recorder:
            sample_rate = 16_000

            @staticmethod
            def stop_recording():
                return np.ones(8_000, dtype=np.float32)

        class Transcriber:
            @staticmethod
            def transcribe(_audio, _sample_rate, **_kwargs):
                entered.set()
                release.wait(1.0)
                return "private late result"

        app = SpeakrApp.__new__(SpeakrApp)
        app._practice_lock = threading.RLock()
        app._practice_generation = 1
        app._practice_recording = True
        app._practice_audio = None
        app._practice = app._empty_practice()
        app._practice["active"] = True
        app._practice_subscribers = []
        app.recorder = Recorder()
        app.transcriber = Transcriber()
        app.dictionary = mock.Mock(apply=lambda value: value)
        app.config = _Config({"voice_commands": False})
        app.log = mock.Mock()

        self.assertTrue(app.stop_practice())
        self.assertTrue(entered.wait(1.0))
        audio = app._practice_audio
        app.clear_practice()
        self.assertIsNotNone(audio)
        self.assertTrue(np.all(audio == 0))
        release.set()
        time.sleep(0.05)
        self.assertEqual(app.practice_snapshot()["heard"], "")
        self.assertFalse(app.practice_snapshot()["hasResult"])


if __name__ == "__main__":
    unittest.main()
