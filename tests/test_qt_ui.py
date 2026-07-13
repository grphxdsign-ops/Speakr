from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from speakr.interface_state import InterfaceState
from speakr import qt_ui


class FontNormalizationTests(unittest.TestCase):
    class Font:
        default_family = "Native UI"

        def __init__(self, source=None):
            self._family = source.family() if isinstance(source, self.__class__) else ""

        def family(self):
            return self._family

        def setFamily(self, value):
            self._family = value

        def defaultFamily(self):
            return self.default_family

    class FontDatabase:
        class SystemFont:
            GeneralFont = 0

        @classmethod
        def systemFont(cls, _role):
            font = FontNormalizationTests.Font()
            font.setFamily("Sans Serif")
            return font

    class Application:
        def __init__(self):
            self._font = FontNormalizationTests.Font()

        def font(self):
            return self._font

        def setFont(self, value):
            self._font = value

    def test_generic_general_font_uses_concrete_qt_default(self):
        application = self.Application()
        qt = SimpleNamespace(QFont=self.Font, QFontDatabase=self.FontDatabase)

        self.assertTrue(qt_ui._normalize_system_ui_font(application, qt))
        self.assertEqual(application.font().family(), "Native UI")

    def test_font_discovery_failure_never_blocks_startup(self):
        class BrokenDatabase(self.FontDatabase):
            @classmethod
            def systemFont(cls, _role):
                raise RuntimeError("font database unavailable")

        application = self.Application()
        qt = SimpleNamespace(QFont=self.Font, QFontDatabase=BrokenDatabase)

        self.assertFalse(qt_ui._normalize_system_ui_font(application, qt))

    def test_generic_font_without_concrete_default_preserves_original(self):
        class NoDefaultFont(self.Font):
            default_family = ""

        application = self.Application()
        application.font().setFamily("Original")
        qt = SimpleNamespace(QFont=NoDefaultFont, QFontDatabase=self.FontDatabase)

        self.assertFalse(qt_ui._normalize_system_ui_font(application, qt))
        self.assertEqual(application.font().family(), "Original")


@unittest.skipUnless(qt_ui.qt_available(), "PySide6-Essentials is optional")
class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.qapp = QApplication.instance() or QApplication([])

    def test_worker_state_is_queued_into_qobject(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState({"availability": "ready"})
                self.enabled = True
                self.confirmed_hotkey = ""

            @staticmethod
            def settings_snapshot():
                return {"ui": {"theme": "system"}}

            @staticmethod
            def practice_snapshot():
                return {
                    "active": False,
                    "processing": False,
                    "heard": "",
                    "wouldType": "",
                    "level": "silent",
                    "message": "",
                }

            @staticmethod
            def list_manual_words():
                return []

            @staticmethod
            def list_learned_words():
                return []

            @staticmethod
            def begin_hotkey_capture(callback):
                callback("caps lock")
                return True

            def confirm_hotkey(self, candidate):
                self.confirmed_hotkey = candidate
                return True

        app = App()
        bridge = qt_ui.Bridge(app)
        try:
            app.interface_state.update(capture="listening", capture_job_id=7)
            self.qapp.processEvents()
            self.assertEqual(bridge.state["primary_text"], "Listening")
            self.assertIn("mic_level_band", bridge.practice)
            self.assertEqual(bridge.practice["text"], "")

            bridge.beginHotkeyCapture()
            self.qapp.processEvents()
            self.assertTrue(bridge.capturingHotkey)
            self.assertEqual(bridge.state["pending_hotkey"], "caps lock")
            bridge.confirmHotkey()
            self.qapp.processEvents()
            self.assertFalse(bridge.capturingHotkey)
            self.assertEqual(app.confirmed_hotkey, "caps lock")
        finally:
            bridge.close()

    def test_failed_confirm_and_onboarding_save_remain_recoverable(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState({"availability": "ready"})
                self.enabled = True
                self.confirm_attempts = 0
                self.onboarding_attempts = 0

            @staticmethod
            def settings_snapshot():
                return {"ui": {"theme": "system"}}

            @staticmethod
            def practice_snapshot():
                return {}

            @staticmethod
            def begin_hotkey_capture(callback):
                callback("caps lock")
                return True

            def confirm_hotkey(self, _candidate):
                self.confirm_attempts += 1
                return False

            def complete_onboarding(self):
                self.onboarding_attempts += 1
                return False

        app = App()
        bridge = qt_ui.Bridge(app)
        try:
            bridge.beginHotkeyCapture()
            self.qapp.processEvents()
            bridge.confirmHotkey()
            self.qapp.processEvents()

            self.assertEqual(app.confirm_attempts, 1)
            self.assertTrue(bridge.capturingHotkey)
            self.assertEqual(bridge.state["pending_hotkey"], "caps lock")
            self.assertFalse(bridge.completeOnboarding())
            self.assertEqual(app.onboarding_attempts, 1)
        finally:
            bridge.close()

    def test_vocabulary_slots_return_backend_result(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState({"availability": "ready"})
                self.enabled = True
                self.succeed = False

            @staticmethod
            def settings_snapshot():
                return {"ui": {"theme": "system"}}

            @staticmethod
            def practice_snapshot():
                return {}

            def add_word(self, _word):
                return self.succeed

            def add_replacement(self, _heard, _intended):
                return self.succeed

        app = App()
        bridge = qt_ui.Bridge(app)
        try:
            self.assertFalse(bridge.addWord("Preserve Me"))
            self.assertFalse(bridge.addReplacement("heard", "intended"))
            app.succeed = True
            self.assertTrue(bridge.addWord("Preserve Me"))
            self.assertTrue(bridge.addReplacement("heard", "intended"))
        finally:
            bridge.close()

    def test_subscription_snapshots_retain_current_system_accessibility(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState({"availability": "ready"})
                self.enabled = True
                self.settings_callback = None

            @staticmethod
            def settings_snapshot():
                return {"ui": {"theme": "system"}}

            @staticmethod
            def practice_snapshot():
                return {}

            def subscribe_settings(self, callback):
                self.settings_callback = callback
                return lambda: None

        accessibility = {
            "system_high_contrast": True,
            "system_reduced_motion": False,
            "system_reduce_transparency": True,
        }
        app = App()
        with mock.patch.object(
            qt_ui, "_system_accessibility_preferences", return_value=accessibility
        ):
            bridge = qt_ui.Bridge(app)
            try:
                self.assertTrue(bridge.settings["system_high_contrast"])
                self.assertTrue(bridge.settings["system_reduce_transparency"])

                app.settings_callback(
                    {
                        "ui": {"theme": "dark"},
                        "system_high_contrast": False,
                        "system_reduce_transparency": False,
                    }
                )
                self.qapp.processEvents()

                self.assertEqual(bridge.settings["ui"]["theme"], "dark")
                self.assertTrue(bridge.settings["system_high_contrast"])
                self.assertTrue(bridge.settings["system_reduce_transparency"])

                bridge.refresh()
                self.qapp.processEvents()
                self.assertTrue(bridge.settings["system_high_contrast"])
                self.assertTrue(bridge.settings["system_reduce_transparency"])
            finally:
                bridge.close()

    def test_background_announcements_are_job_keyed_and_capture_wins(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState(
                    {"availability": "ready"}
                )
                self.enabled = True

            @staticmethod
            def settings_snapshot():
                return {"ui": {"background_announcements": True}}

            @staticmethod
            def practice_snapshot():
                return {}

        bridge = qt_ui.Bridge(App())
        announcements = []
        bridge._announce = lambda message, **options: announcements.append(
            (message, options)
        )
        try:
            def announce(snapshot):
                bridge._announce_state({}, snapshot)

            bridge._settings["ui"]["background_announcements"] = False
            announce(
                {
                    "capture": "listening",
                    "capture_job_id": 19,
                    "pipeline": "idle",
                    "pipeline_job_id": 0,
                }
            )
            self.assertEqual(announcements, [])
            bridge._settings["ui"]["background_announcements"] = True

            # Capture B owns the foreground. Processing job A remains visual
            # secondary state but must not speak into the active microphone.
            announce(
                {
                    "capture": "listening",
                    "capture_job_id": 20,
                    "pipeline": "transcribing",
                    "pipeline_job_id": 10,
                }
            )
            announce(
                {
                    "capture": "listening",
                    "capture_job_id": 20,
                    "pipeline": "formatting",
                    "pipeline_job_id": 10,
                }
            )
            self.assertEqual(
                announcements, [("Listening", {"assertive": True})]
            )

            # Once capture is idle, job A gets one processing announcement,
            # regardless of how many local pipeline stages it visits.
            announce(
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "formatting",
                    "pipeline_job_id": 10,
                }
            )
            announce(
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "injecting",
                    "pipeline_job_id": 10,
                }
            )
            announce(
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "success",
                    "pipeline_job_id": 10,
                    "pipeline_mode": "dictation",
                    "status_code": "success",
                }
            )
            announce(
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "success",
                    "pipeline_job_id": 10,
                    "pipeline_mode": "dictation",
                    "status_code": "success",
                }
            )

            # A later edit job has its own processing and truthful final copy.
            announce(
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "transcribing",
                    "pipeline_job_id": 11,
                }
            )
            announce(
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "success",
                    "pipeline_job_id": 11,
                    "pipeline_mode": "edit",
                    "status_code": "edit_success",
                }
            )

            self.assertEqual(
                announcements,
                [
                    ("Listening", {"assertive": True}),
                    ("Processing locally", {}),
                    ("Inserted", {}),
                    ("Processing locally", {}),
                    ("Selection updated", {}),
                ],
            )
        finally:
            bridge.close()

    def test_attempt_final_is_not_reannounced_when_attempt_id_retires(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState(
                    {"availability": "ready"}
                )
                self.enabled = True

            @staticmethod
            def settings_snapshot():
                return {"ui": {"background_announcements": True}}

            @staticmethod
            def practice_snapshot():
                return {}

        bridge = qt_ui.Bridge(App())
        announcements = []
        bridge._announce = lambda message, **_options: announcements.append(
            message
        )
        try:
            final = {
                "capture": "idle",
                "capture_job_id": 31,
                "pipeline": "idle",
                "pipeline_job_id": 0,
                "status_code": "mic_recovery",
            }
            bridge._announce_state({}, final)
            bridge._announce_state(
                final,
                {**final, "capture_job_id": 0},
            )
            bridge._announce_state(
                {},
                {
                    "capture": "idle",
                    "capture_job_id": 0,
                    "pipeline": "idle",
                    "pipeline_job_id": 0,
                    "status_code": "no_speech",
                },
            )
            self.assertEqual(
                announcements,
                ["Microphone reconnected. Please try again."],
            )
        finally:
            bridge.close()

    def test_final_announcement_coalesces_one_edit_job_and_covers_mic_failure(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState(
                    {"availability": "ready"}
                )
                self.enabled = True

            @staticmethod
            def settings_snapshot():
                return {"ui": {"background_announcements": True}}

            @staticmethod
            def practice_snapshot():
                return {}

        bridge = qt_ui.Bridge(App())
        announcements = []
        bridge._announce = lambda message, **_options: announcements.append(
            message
        )
        try:
            processing = {
                "capture": "idle",
                "capture_job_id": 0,
                "pipeline": "formatting",
                "pipeline_job_id": 42,
                "pipeline_mode": "edit",
                "status_code": "edit_formatting",
            }
            bridge._announce_state({}, processing)
            first_final = {
                **processing,
                "pipeline": "error",
                "status_code": "pipeline_error",
            }
            bridge._announce_state(processing, first_final)
            bridge._announce_state(
                first_final,
                {
                    **first_final,
                    "pipeline": "idle",
                    "status_code": "edit_failure",
                    "last_issue": {
                        "code": "edit_failed",
                        "message": "The original selection was not changed.",
                    },
                },
            )

            mic_failure = {
                "capture": "idle",
                "capture_job_id": 77,
                "pipeline": "idle",
                "pipeline_job_id": 0,
                "status_code": "needs_attention",
                "last_issue": {
                    "code": "microphone_unavailable",
                    "message": "Microphone access is needed.",
                },
            }
            bridge._announce_state({}, mic_failure)
            bridge._announce_state(
                mic_failure,
                {**mic_failure, "capture_job_id": 0},
            )

            self.assertEqual(
                announcements,
                [
                    "Processing locally",
                    "The original selection was not changed.",
                    "Microphone access is needed.",
                ],
            )
        finally:
            bridge.close()


if __name__ == "__main__":
    unittest.main()
