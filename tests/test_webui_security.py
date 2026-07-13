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
        self.retry_model_calls = 0
        self.retry_setup_calls = 0

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

    def retry_model(self):
        self.retry_model_calls += 1
        return True

    def retry_setup(self):
        self.retry_setup_calls += 1
        return True

    @staticmethod
    def open_local(_kind):
        return True

    @staticmethod
    def set_setting(_path, _value):
        return True


class WebUISecurityTests(unittest.TestCase):
    @staticmethod
    def _luminance(hex_color):
        channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    @classmethod
    def _contrast(cls, first, second):
        left, right = cls._luminance(first), cls._luminance(second)
        return (max(left, right) + 0.05) / (min(left, right) + 0.05)

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

    def test_recovery_page_uses_local_luminous_orbit_fallbacks(self):
        status, _headers, body = self.request("GET", f"/?token={self.ui.token}")

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        for token in (
            "--canvas:#EDF1FA",
            "--surface:#F8FAFF",
            "--ink:#17182A",
            "--muted:#55596D",
            "--line:#747A92",
            "--accent:#6657D8",
            "--canvas:#090B18",
            "--surface:#20243A",
            "--ink:#F2F3FC",
            "--muted:#B4B7C9",
            "--line:#737A99",
            "--accent:#A89AFB",
        ):
            self.assertIn(token, page)
        self.assertIn("radial-gradient", page)
        self.assertIn("min-height:44px", page)
        self.assertIn("border-radius:28px", page)
        self.assertIn("@media(prefers-color-scheme:dark)", page)
        self.assertIn("@media(prefers-contrast:more)", page)
        self.assertIn("@media(prefers-reduced-motion:reduce)", page)
        self.assertIn("@media(forced-colors:active)", page)
        self.assertIn('tabindex="-1"', page)
        self.assertIn(".textContent", page)
        self.assertIn('api("/api/wait?after="+after)', page)
        self.assertIn("setTimeout(wait,1200)", page)
        self.assertNotIn("@keyframes", page)
        self.assertNotIn(".innerHTML", page)
        self.assertNotIn("url(", page)
        self.assertNotIn("<link", page)
        self.assertNotIn("<img", page)
        self.assertNotIn("backdrop-filter", page)
        self.assertIn("button{min-height:44px;border:1px solid var(--line)", page)
        self.assertIn(".navbtn[aria-current=page]{background:var(--well);border-color:var(--line)", page)
        self.assertGreaterEqual(self._contrast("#747A92", "#F8FAFF"), 3.0)
        self.assertGreaterEqual(self._contrast("#737A99", "#282C45"), 3.0)
        self.assertIn('label:"Retry speech model"', page)
        self.assertIn('label:"Recheck setup"', page)
        self.assertIn('$("recheckIssue").onclick=function(){action("retry_setup");}', page)

    def test_recovery_switches_have_native_names_and_truthful_on_off_copy(self):
        status, _headers, body = self.request(
            "GET", f"/?token={self.ui.token}"
        )

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        switches = (
            ("keepMic", "keepMicLabel", "prerollText", "keepMicState"),
            (
                "screenContext",
                "screenContextLabel",
                "screenContextHelp",
                "screenContextState",
            ),
            ("editMode", "editModeLabel", "editModeHelp", "editModeState"),
            (
                "recentContext",
                "recentContextLabel",
                "recentContextHelp",
                "recentContextState",
            ),
            (
                "logTranscripts",
                "logTranscriptsLabel",
                "logWarning",
                "logTranscriptsState",
            ),
        )
        for input_id, label_id, description_id, state_id in switches:
            with self.subTest(input_id=input_id):
                self.assertIn(f'for="{input_id}"', page)
                self.assertIn(f'id="{input_id}"', page)
                self.assertIn(f'aria-labelledby="{label_id}"', page)
                self.assertIn(f'aria-describedby="{description_id}"', page)
                self.assertIn(
                    f'<span id="{state_id}" aria-hidden="true">Off</span>',
                    page,
                )
                self.assertIn(
                    f'renderSwitch("{input_id}","{state_id}",', page
                )
        self.assertEqual(page.count('aria-hidden="true">Off</span>'), 5)
        self.assertNotIn(">Enabled</span>", page)
        self.assertIn('textContent=checked?"On":"Off"', page)

    def test_recovery_hotkey_copy_uses_effective_mode_and_capture_truth(self):
        class ComboConfig(_Config):
            def get(self, *keys, default=None):
                if keys == ("hotkey",):
                    return "ctrl+shift"
                if keys == ("toggle_mode",):
                    return False
                return super().get(*keys, default=default)

        self.ui.app.config = ComboConfig()
        with mock.patch.object(webui.sys, "platform", "win32"):
            settings = self.ui.settings()
            status, _headers, body = self.request(
                "GET",
                "/api/settings",
                headers={"X-Speakr-Token": self.ui.token},
            )

        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertEqual(response["platform"], "windows")
        self.assertTrue(response["effective_toggle_mode"])
        self.assertTrue(response["toggle_mode_forced"])
        self.assertEqual(response, settings)

        status, _headers, body = self.request(
            "GET", f"/?token={self.ui.token}"
        )
        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        self.assertIn(
            'function toggleInstruction(listening){if(settings.effective_toggle_mode)',
            page,
        )
        self.assertIn(
            'return listening?"Press "+hotkeyName()+" again to stop.":',
            page,
        )
        self.assertIn(
            'return listening?"Release "+hotkeyName()+" when you are finished.":',
            page,
        )
        self.assertIn(
            '$("secondary").textContent=capture==="listening"?toggleInstruction(true):',
            page,
        )
        self.assertIn(
            'if(settings.toggle_mode_forced)captureDisclosure+=', page
        )
        self.assertIn(
            "This Windows key combination always uses press-to-start and press-to-stop.",
            page,
        )

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

    def test_setup_retries_are_allowlisted_and_token_authenticated(self):
        for action, counter in (
            ("retry_model", "retry_model_calls"),
            ("retry_setup", "retry_setup_calls"),
        ):
            with self.subTest(action=action):
                before = getattr(self.ui.app, counter)
                status, _headers, _body = self.request(
                    "POST", "/api/action", body={"action": action}
                )
                self.assertEqual(status, 403)
                self.assertEqual(getattr(self.ui.app, counter), before)

                status, headers, body = self.request(
                    "POST",
                    "/api/action",
                    headers={"X-Speakr-Token": self.ui.token},
                    body={"action": action},
                )
                self.assertEqual(status, 200)
                self.assertIn("no-store", headers["Cache-Control"])
                self.assertTrue(json.loads(body)["ok"])
                self.assertEqual(getattr(self.ui.app, counter), before + 1)

        status, _headers, _body = self.request(
            "POST",
            "/api/action",
            headers={"X-Speakr-Token": self.ui.token},
            body={"action": "retry_arbitrary"},
        )
        self.assertEqual(status, 404)

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
