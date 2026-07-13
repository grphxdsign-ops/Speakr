from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from speakr import app as app_module
from speakr.app import SpeakrApp


class SingleInstanceWakeTests(unittest.TestCase):
    def test_primary_clears_stale_request_before_constructing_ui(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "show.request"
            request.write_text("stale", encoding="utf-8")
            fake_app = mock.Mock()

            def construct():
                self.assertFalse(request.exists())
                # Model a duplicate launch while the native UI is starting.
                request.write_text("fresh", encoding="utf-8")
                return fake_app

            with mock.patch.object(
                app_module, "_acquire_single_instance", return_value=True
            ), mock.patch.object(
                app_module.cfg_mod, "SHOW_REQUEST_PATH", request
            ), mock.patch.object(
                app_module, "SpeakrApp", side_effect=construct
            ):
                app_module.main()

            fake_app.start.assert_called_once_with()
            self.assertEqual(request.read_text(encoding="utf-8"), "fresh")

    def test_duplicate_publishes_show_request_without_constructing_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "show.request"
            logger = mock.Mock()

            with mock.patch.object(
                app_module, "_acquire_single_instance", return_value=False
            ), mock.patch.object(
                app_module.cfg_mod, "SHOW_REQUEST_PATH", request
            ), mock.patch.object(
                app_module, "setup_logging", return_value=logger
            ), mock.patch.object(app_module, "SpeakrApp") as app_type:
                app_module.main()

            app_type.assert_not_called()
            logger.warning.assert_called_once()
            self.assertTrue(request.read_text(encoding="utf-8").isdigit())

    def test_watcher_observes_request_created_during_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "show.request"
            request.write_text("fresh", encoding="utf-8")
            app = SpeakrApp.__new__(SpeakrApp)
            app._shutting_down = False

            def shown():
                app._shutting_down = True

            app.show_main_window = mock.Mock(side_effect=shown)
            with mock.patch.object(app_module.cfg_mod, "SHOW_REQUEST_PATH", request):
                app._watch_show_requests()

            app.show_main_window.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
