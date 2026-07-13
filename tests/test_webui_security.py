from __future__ import annotations

import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from speakr import config as cfg_mod
from speakr.interface_state import InterfaceState
from speakr import webui


class _Config:
    def get(self, *keys, default=None):
        values = {
            "hotkey": "right ctrl",
            "toggle_mode": False,
            "keep_mic_stream_open": True,
            "preroll_seconds": 0.4,
            "screen_context": {"enabled": True},
            "edit_mode": {"enabled": True},
            "formatting": {"include_recent_context": True},
            "log_transcripts": False,
        }
        node = values
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _App:
    def __init__(self):
        self.config = _Config()
        self.interface_state = InterfaceState({"availability": "ready"})
        self.enabled = True
        self.capturing_hotkey = False
        self.pending_hotkey = None

    def toggle_enabled(self):
        self.enabled = not self.enabled
        self.interface_state.update(enabled=self.enabled)
        return True

    @staticmethod
    def begin_hotkey_capture():
        return True

    @staticmethod
    def cancel_hotkey_capture():
        return True

    @staticmethod
    def confirm_hotkey():
        return True

    def dismiss_issue(self):
        self.interface_state.dismiss_issue()
        return True

    @staticmethod
    def open_system_settings():
        return True

    @staticmethod
    def open_local(_kind):
        return True

    @staticmethod
    def set_setting(_path, _value):
        return True


class WebUISecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.panel_path = Path(self.temp.name) / "panel.url"
        self.patches = [
            mock.patch.object(cfg_mod, "PANEL_URL_PATH", self.panel_path),
            mock.patch.object(webui, "PREFERRED_PORT", 0),
        ]
        for patcher in self.patches:
            patcher.start()
        self.ui = webui.WebUI(_App())
        self.ui.start()

    def tearDown(self):
        server = self.ui._server
        self.ui.stop()
        if server is not None:
            server.server_close()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def request(self, method, path, *, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.ui.port, timeout=2)
        default_headers = {"Host": f"127.0.0.1:{self.ui.port}"}
        default_headers.update(headers or {})
        payload = None if body is None else json.dumps(body)
        connection.request(method, path, body=payload, headers=default_headers)
        response = connection.getresponse()
        data = response.read()
        headers_out = dict(response.getheaders())
        connection.close()
        return response.status, headers_out, data

    def test_initial_page_is_token_gated_local_and_no_store(self):
        status, _headers, _body = self.request("GET", "/")
        self.assertEqual(status, 403)

        status, headers, body = self.request("GET", f"/?token={self.ui.token}")
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("microphone=()", headers["Permissions-Policy"])
        self.assertIn("clipboard-read=()", headers["Permissions-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn(b"speakr.cloud", body)
        self.assertNotIn(b"https://", body)

    def test_every_api_read_and_mutation_requires_header_token(self):
        status, _headers, _body = self.request("GET", "/api/state")
        self.assertEqual(status, 403)

        token = {"X-Speakr-Token": self.ui.token}
        status, _headers, body = self.request("GET", "/api/state", headers=token)
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertNotIn("transcript", state)
        self.assertNotIn("practice", state)

        status, _headers, _body = self.request(
            "POST", "/api/action", body={"action": "toggle_dictation"}
        )
        self.assertEqual(status, 403)
        status, _headers, body = self.request(
            "POST",
            "/api/action",
            headers=token,
            body={"action": "toggle_dictation"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_unexpected_host_and_origin_are_rejected(self):
        token = {"X-Speakr-Token": self.ui.token, "Host": "attacker.invalid"}
        status, _headers, _body = self.request("GET", "/api/state", headers=token)
        self.assertEqual(status, 403)

        token = {
            "X-Speakr-Token": self.ui.token,
            "Origin": "https://attacker.invalid",
        }
        status, _headers, _body = self.request("GET", "/api/state", headers=token)
        self.assertEqual(status, 403)

    def test_versioned_wait_reconnects_with_sanitized_state_only(self):
        token = {"X-Speakr-Token": self.ui.token}
        before = self.ui.app.interface_state.snapshot()["version"]
        self.ui.app.interface_state.update(capture="listening", capture_job_id=9)

        status, headers, body = self.request(
            "GET", f"/api/wait?after={before}", headers=token
        )

        self.assertEqual(status, 200)
        self.assertIn("no-store", headers["Cache-Control"])
        state = json.loads(body)
        self.assertGreater(state["version"], before)
        self.assertEqual(state["capture"], "listening")
        self.assertNotIn("practice", state)
        self.assertNotIn("transcript", state)

    def test_idle_wait_timeout_returns_current_state_instead_of_null(self):
        current = self.ui.app.interface_state.snapshot()
        result = self.ui.wait_state(current["version"], timeout=0)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["version"], current["version"])
        self.assertNotIn("practice", result)
        self.assertNotIn("transcript", result)


if __name__ == "__main__":
    unittest.main()
