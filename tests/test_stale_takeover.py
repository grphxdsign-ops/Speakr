"""Regression tests for 2026-07-15: an updated Speakr install kept
deferring to a still-running older instance, so the new build's window
(and its renderer fixes) never appeared. A new launch must replace a
primary from a different build and never touch a same-build primary or
an unverifiable process."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from speakr import app as app_module
from speakr import config as cfg_mod
from speakr import qt_ui
from speakr.app import SpeakrApp


class PrimaryIdentityTests(unittest.TestCase):
    def _patched_paths(self, temporary):
        root = Path(temporary)
        return mock.patch.multiple(
            cfg_mod,
            PRIMARY_INFO_PATH=root / "primary.json",
            QUIT_REQUEST_PATH=root / "quit.request",
        )

    def test_identity_roundtrip_matches_current_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                app_module._write_primary_info()
                info = app_module._read_primary_info()
                self.assertTrue(app_module._primary_is_current_build(info))
                app_module._clear_primary_info()
                self.assertIsNone(app_module._read_primary_info())

    def test_missing_malformed_or_foreign_identity_is_not_current(self):
        self.assertFalse(app_module._primary_is_current_build(None))
        self.assertFalse(app_module._primary_is_current_build([1, 2]))
        self.assertFalse(app_module._primary_is_current_build({"protocol": 2}))
        ours = app_module._executable_identity()
        stale = {
            "protocol": 1,
            "pid": 12345,
            "executable": ours["executable"],
            "executable_mtime_ns": ours["executable_mtime_ns"] + 1,
        }
        self.assertFalse(app_module._primary_is_current_build(stale))
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                cfg_mod.PRIMARY_INFO_PATH.write_text("{oops", encoding="utf-8")
                self.assertIsNone(app_module._read_primary_info())


class ReplaceStalePrimaryTests(unittest.TestCase):
    def _patched_paths(self, temporary):
        root = Path(temporary)
        return mock.patch.multiple(
            cfg_mod,
            PRIMARY_INFO_PATH=root / "primary.json",
            QUIT_REQUEST_PATH=root / "quit.request",
        )

    def test_same_build_primary_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                app_module._write_primary_info()
                with mock.patch.object(
                    app_module, "_acquire_single_instance"
                ) as acquire, mock.patch.object(
                    app_module, "_terminate_stale_speakr"
                ) as terminate:
                    self.assertFalse(
                        app_module._replace_stale_primary(mock.Mock())
                    )
                acquire.assert_not_called()
                terminate.assert_not_called()
                self.assertFalse(cfg_mod.QUIT_REQUEST_PATH.exists())

    def test_protocol_aware_stale_build_gets_graceful_quit_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                ours = app_module._executable_identity()
                cfg_mod.PRIMARY_INFO_PATH.write_text(
                    '{"protocol": 1, "pid": 4242, '
                    f'"executable": "{ours["executable"].replace(chr(92), "/")}", '
                    '"executable_mtime_ns": 1}',
                    encoding="utf-8",
                )
                with mock.patch.object(
                    app_module, "_acquire_single_instance", return_value=True
                ), mock.patch.object(
                    app_module, "_terminate_stale_speakr"
                ) as terminate:
                    self.assertTrue(
                        app_module._replace_stale_primary(mock.Mock())
                    )
                terminate.assert_not_called()
                self.assertTrue(cfg_mod.QUIT_REQUEST_PATH.exists())

    def test_unresponsive_stale_build_is_terminated_then_lock_reacquired(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                cfg_mod.PRIMARY_INFO_PATH.write_text(
                    '{"protocol": 1, "pid": 4242, "executable": "elsewhere",'
                    ' "executable_mtime_ns": 1}',
                    encoding="utf-8",
                )
                with mock.patch.object(
                    app_module,
                    "_acquire_single_instance",
                    side_effect=[False, True],
                ), mock.patch.object(
                    app_module, "_terminate_stale_speakr"
                ) as terminate:
                    self.assertTrue(
                        app_module._replace_stale_primary(mock.Mock())
                    )
                terminate.assert_called_once_with(4242, mock.ANY)

    def test_pre_protocol_primary_without_candidates_defers(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                with mock.patch.object(
                    app_module, "_discover_stale_speakr_pids", return_value=[]
                ), mock.patch.object(
                    app_module, "_acquire_single_instance"
                ) as acquire:
                    self.assertFalse(
                        app_module._replace_stale_primary(mock.Mock())
                    )
                acquire.assert_not_called()

    def test_pre_protocol_named_zombie_is_terminated(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self._patched_paths(temporary):
                with mock.patch.object(
                    app_module,
                    "_discover_stale_speakr_pids",
                    return_value=[777],
                ), mock.patch.object(
                    app_module, "_terminate_stale_speakr"
                ) as terminate, mock.patch.object(
                    app_module, "_acquire_single_instance", return_value=True
                ):
                    self.assertTrue(
                        app_module._replace_stale_primary(mock.Mock())
                    )
                terminate.assert_called_once_with(777, mock.ANY)

    def test_termination_refuses_unverifiable_process_names(self):
        logger = mock.Mock()
        with mock.patch.object(
            app_module, "_pid_process_name", return_value="python"
        ), mock.patch.object(app_module.subprocess, "run") as run, mock.patch.object(
            app_module.os, "kill"
        ) as kill:
            app_module._terminate_stale_speakr(4242, logger)
        run.assert_not_called()
        kill.assert_not_called()


class QuitRequestWatcherTests(unittest.TestCase):
    def test_primary_watcher_honors_takeover_quit_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            quit_calls = []
            application = object.__new__(SpeakrApp)
            application._shutting_down = False
            application.log = mock.Mock()
            application.show_main_window = mock.Mock()

            def fake_quit():
                quit_calls.append(True)
                application._shutting_down = True

            application.quit = fake_quit
            with mock.patch.multiple(
                cfg_mod,
                SHOW_REQUEST_PATH=root / "show.request",
                QUIT_REQUEST_PATH=root / "quit.request",
            ):
                cfg_mod.QUIT_REQUEST_PATH.write_text("1", encoding="utf-8")
                watcher = threading.Thread(
                    target=application._watch_show_requests, daemon=True
                )
                watcher.start()
                watcher.join(timeout=5)
                self.assertFalse(watcher.is_alive())
                self.assertEqual(quit_calls, [True])
                self.assertFalse(cfg_mod.QUIT_REQUEST_PATH.exists())


class DarwinRendererDefaultTests(unittest.TestCase):
    def _clean_environment(self, **overrides):
        import os

        removed = {
            "SPEAKR_QT_SOFTWARE", "SPEAKR_QT_HARDWARE", "QT_QUICK_BACKEND",
            "QSG_RHI_BACKEND", "SESSIONNAME", "SSH_CONNECTION",
        }
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in removed
        }
        environment.update(overrides)
        return environment

    def test_macos_defaults_to_software_with_hardware_escape_hatch(self):
        import os

        with mock.patch.object(qt_ui.sys, "platform", "darwin"):
            with mock.patch.dict(
                os.environ, self._clean_environment(), clear=True
            ):
                self.assertTrue(qt_ui._prefer_software_renderer())
            with mock.patch.dict(
                os.environ,
                self._clean_environment(SPEAKR_QT_HARDWARE="1"),
                clear=True,
            ):
                self.assertFalse(qt_ui._prefer_software_renderer())


if __name__ == "__main__":
    unittest.main()
