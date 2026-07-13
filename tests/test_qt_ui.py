from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from speakr.interface_state import InterfaceState
from speakr import qt_ui


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


if __name__ == "__main__":
    unittest.main()
