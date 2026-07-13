from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from speakr import app as app_module
from speakr import qt_ui
from speakr.hotkey import resolve_hotkey_mode
from speakr.interface_state import InterfaceState

if sys.platform == "win32":
    from speakr import win_input
else:  # The Windows keyboard-hook dependency is intentionally not on macOS.
    win_input = None


class HotkeyPresentationTests(unittest.TestCase):
    def test_resolver_matches_platform_listener_policy(self):
        cases = (
            ("right ctrl", False, "windows", False, False),
            ("right ctrl", True, "windows", True, False),
            ("ctrl+shift", False, "windows", True, True),
            ("ctrl+shift", True, "WINDOWS", True, True),
            ("fn", False, "mac", False, False),
            ("cmd+shift", False, "darwin", False, False),
            (None, 0, "windows", False, False),
        )
        for hotkey, requested, platform, effective, forced in cases:
            with self.subTest(
                hotkey=hotkey, requested=requested, platform=platform
            ):
                self.assertEqual(
                    resolve_hotkey_mode(
                        hotkey, requested, platform=platform
                    ),
                    {
                        "effective_toggle_mode": effective,
                        "toggle_mode_forced": forced,
                    },
                )

    @unittest.skipUnless(sys.platform == "win32", "Windows listener policy")
    def test_windows_listener_uses_the_same_effective_mode(self):
        self.assertIsNotNone(win_input)
        callbacks: list[str] = []

        def listener(hotkey, toggle_mode):
            return win_input.HotkeyListener(
                hotkey,
                toggle_mode,
                lambda: callbacks.append("press"),
                lambda: callbacks.append("release"),
                lambda: callbacks.append("toggle"),
            )

        with (
            mock.patch.object(win_input.keyboard, "add_hotkey") as add_hotkey,
            mock.patch.object(win_input.keyboard, "hook_key") as hook_key,
            mock.patch.object(win_input.keyboard, "unhook_all") as unhook_all,
        ):
            combo = listener("ctrl+shift", False)
            self.assertTrue(combo.toggle_mode)
            self.assertEqual(
                combo.toggle_mode,
                resolve_hotkey_mode(
                    "ctrl+shift", False, platform="windows"
                )["effective_toggle_mode"],
            )
            combo.start()
            add_hotkey.assert_called_once_with("ctrl+shift", combo.on_toggle)
            hook_key.assert_not_called()

            add_hotkey.reset_mock()
            hold = listener("right ctrl", False)
            self.assertFalse(hold.toggle_mode)
            hold.start()
            hook_key.assert_called_once_with("right ctrl", hold._event)
            add_hotkey.assert_not_called()
            hold._event(SimpleNamespace(event_type="down"))
            hold._event(SimpleNamespace(event_type="up"))
            self.assertEqual(callbacks, ["press", "release"])

            requested_toggle = listener("right ctrl", True)
            self.assertTrue(requested_toggle.toggle_mode)
            requested_toggle.start()
            add_hotkey.assert_called_once_with(
                "right ctrl", requested_toggle.on_toggle
            )
            requested_toggle.stop()
            unhook_all.assert_called_once_with()

    def test_presentation_fields_live_in_settings_not_interface_state(self):
        state = InterfaceState(
            {
                "availability": "ready",
                "hotkey": "ctrl+shift",
            }
        )
        snapshot = state.snapshot()
        self.assertNotIn("effective_toggle_mode", snapshot)
        self.assertNotIn("toggle_mode_forced", snapshot)
        for field in ("effective_toggle_mode", "toggle_mode_forced"):
            with self.subTest(field=field):
                with self.assertRaises(KeyError):
                    state.update(**{field: True})

        fake_app = SimpleNamespace(
            config=SimpleNamespace(
                snapshot=lambda: {
                    "hotkey": "ctrl+shift",
                    "toggle_mode": False,
                }
            ),
            _pending_hotkey=None,
            _capturing_hotkey=False,
            recorder=SimpleNamespace(
                stream_open=False,
                input_device=None,
                sample_rate=16_000,
            ),
            transcriber=SimpleNamespace(
                model_in_use=None,
                device_in_use=None,
                compute_type_in_use=None,
            ),
        )
        with mock.patch.object(app_module.sys, "platform", "win32"):
            settings = app_module.SpeakrApp.settings_snapshot(fake_app)
        self.assertTrue(settings["effective_toggle_mode"])
        self.assertTrue(settings["toggle_mode_forced"])
        self.assertNotIn("effective_toggle_mode", state.snapshot())
        self.assertNotIn("toggle_mode_forced", state.snapshot())

    def test_legacy_qt_settings_use_the_pure_resolver(self):
        legacy_app = SimpleNamespace(
            config=SimpleNamespace(
                data={"hotkey": "ctrl+alt", "toggle_mode": False}
            ),
            enabled=True,
        )
        with mock.patch.object(qt_ui.sys, "platform", "win32"):
            settings = qt_ui._legacy_settings_snapshot(legacy_app)
        self.assertEqual(settings["platform"], "windows")
        self.assertTrue(settings["effective_toggle_mode"])
        self.assertTrue(settings["toggle_mode_forced"])


if __name__ == "__main__":
    unittest.main()
