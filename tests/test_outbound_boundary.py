from __future__ import annotations

import http.client
import ipaddress
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from speakr import config as cfg_mod
from speakr.formatter import Formatter, _local_ollama_url
from speakr.interface_state import InterfaceState
from speakr import webui


class _Config:
    def get(self, *keys, default=None):
        values = {
            "hotkey": "right ctrl",
            "toggle_mode": False,
            "keep_mic_stream_open": False,
            "preroll_seconds": 0.4,
            "screen_context": {"enabled": False},
            "edit_mode": {"enabled": False},
            "log_transcripts": False,
            "app_tones": {},
            "voice_commands": True,
            "formatting": {
                "enabled": True,
                "use_ollama": False,
                "autostart_ollama": False,
                "include_recent_context": False,
                "ollama_url": "http://127.0.0.1:11434",
            },
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


class OutboundBoundaryTests(unittest.TestCase):
    def test_cleanup_reachability_publishes_without_autostart(self):
        class LocalNoAutostart(_Config):
            def get(self, *keys, default=None):
                if keys == ("formatting",):
                    value = dict(super().get(*keys, default=default))
                    value.update(use_ollama=True, autostart_ollama=False)
                    return value
                return super().get(*keys, default=default)

        formatter = Formatter(LocalNoAutostart())
        formatter._probe = mock.Mock(return_value=False)

        formatter.ensure_ollama()

        formatter._probe.assert_called_once_with()

    def test_cleanup_probe_notifies_interface_callback(self):
        class RemoteConfig(_Config):
            def get(self, *keys, default=None):
                if keys == ("formatting", "ollama_url"):
                    return "http://example.invalid:11434"
                return super().get(*keys, default=default)

        seen = []
        formatter = Formatter(RemoteConfig())
        formatter.set_status_callback(seen.append)

        self.assertFalse(formatter._probe())
        self.assertEqual(seen, [False])

    def test_ollama_origin_is_forced_to_numeric_loopback(self):
        self.assertEqual(
            _local_ollama_url("http://localhost:11434"),
            "http://127.0.0.1:11434",
        )
        self.assertEqual(
            _local_ollama_url("http://127.0.0.2:9911"),
            "http://127.0.0.2:9911",
        )
        self.assertEqual(
            _local_ollama_url("http://[::1]:11434"),
            "http://[::1]:11434",
        )
        for value in (
            "https://127.0.0.1:11434",
            "http://example.com:11434",
            "http://10.0.0.8:11434",
            "http://user:pass@127.0.0.1:11434",
            "http://127.0.0.1:11434/remote/path",
        ):
            self.assertIsNone(_local_ollama_url(value))

    def test_remote_ollama_config_cannot_send_dictated_text(self):
        class RemoteConfig(_Config):
            def get(self, *keys, default=None):
                if keys == ("formatting", "ollama_url"):
                    return "http://example.invalid:11434"
                if keys == ("formatting",):
                    value = dict(super().get(*keys, default=default))
                    value["use_ollama"] = True
                    value["ollama_url"] = "http://example.invalid:11434"
                    return value
                return super().get(*keys, default=default)

        with mock.patch("speakr.formatter.requests.sessions.Session.request") as request:
            formatter = Formatter(RemoteConfig())
            self.assertEqual(
                formatter.format("private dictated words", {}),
                "Private dictated words",
            )
            request.assert_not_called()

    def test_offline_interface_path_connects_only_to_loopback(self):
        original_connect = socket.socket.connect
        attempted = []

        def guarded_connect(sock, address):
            host = address[0]
            attempted.append(host)
            try:
                allowed = ipaddress.ip_address(host).is_loopback
            except ValueError:
                allowed = str(host).casefold() == "localhost"
            if not allowed:
                raise AssertionError(f"non-loopback connection attempted: {host}")
            return original_connect(sock, address)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            cfg_mod, "PANEL_URL_PATH", Path(directory) / "panel.url"
        ), mock.patch.object(webui, "PREFERRED_PORT", 0), mock.patch.object(
            socket.socket, "connect", guarded_connect
        ), mock.patch(
            "speakr.formatter.requests.sessions.Session.request"
        ) as remote_request:
            # Ollama is explicitly disabled, so the cleanup path cannot make
            # even a loopback HTTP request.
            formatter = Formatter(_Config())
            formatter.ensure_ollama()
            self.assertEqual(formatter.format("hello there", {}), "Hello there")
            remote_request.assert_not_called()

            ui = webui.WebUI(_App())
            ui.start()
            server = ui._server
            try:
                connection = http.client.HTTPConnection("127.0.0.1", ui.port, timeout=2)
                connection.request(
                    "GET",
                    "/api/state",
                    headers={
                        "Host": f"127.0.0.1:{ui.port}",
                        "X-Speakr-Token": ui.token,
                    },
                )
                response = connection.getresponse()
                response.read()
                connection.close()
                self.assertEqual(response.status, 200)
            finally:
                ui.stop()
                if server is not None:
                    server.server_close()

        self.assertTrue(attempted)
        self.assertTrue(all(ipaddress.ip_address(host).is_loopback for host in attempted))


if __name__ == "__main__":
    unittest.main()
