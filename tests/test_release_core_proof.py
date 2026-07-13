import errno
import json
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.validate_release_core_receipt import EXPECTED_RECEIPT, main as validate_main
from speakr.app import SpeakrApp
from speakr.interface_state import InterfaceState
from speakr.release_core_proof import (
    CORE_PROOF_PATH_ENV,
    CoreReleaseProof,
    LoopbackSocketGuard,
    core_proof_requested,
)


class _Config:
    def __init__(self, values):
        self.values = values

    def get(self, *keys, default=None):
        value = self.values
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class CoreReleaseProofTests(unittest.TestCase):
    def offline_environment(self):
        return mock.patch.dict(
            os.environ,
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
            },
        )

    def proof_app(self, *, use_ollama=False, autostart_ollama=False):
        return SimpleNamespace(
            config=_Config(
                {
                    "formatting": {
                        "enabled": True,
                        "use_ollama": use_ollama,
                        "autostart_ollama": autostart_ollama,
                    }
                }
            ),
            quit=mock.Mock(),
        )

    def test_normal_environment_does_not_request_core_proof(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(core_proof_requested())
        with mock.patch.dict(
            os.environ, {CORE_PROOF_PATH_ENV: "proof.json"}, clear=True
        ):
            self.assertTrue(core_proof_requested())

    def test_socket_guard_allows_loopback_and_blocks_every_ip_egress_shape(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        external = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        datagram = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        guard = LoopbackSocketGuard()
        accepted = None
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            guard.install()

            client.connect(listener.getsockname())
            accepted, _ = listener.accept()
            self.assertEqual(guard.blocked_attempts, 0)

            with self.assertRaises(PermissionError):
                external.connect(("203.0.113.10", 443))
            self.assertEqual(
                external.connect_ex(("example.invalid", 443)), errno.EACCES
            )
            with self.assertRaises(PermissionError):
                datagram.sendto(b"x", ("198.51.100.4", 53))
            self.assertEqual(guard.blocked_attempts, 3)
        finally:
            guard.restore_for_tests()
            for item in (accepted, datagram, external, client, listener):
                if item is not None:
                    item.close()

    def test_socket_guard_blocks_dns_before_resolution_and_allows_localhost(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        original = mock.Mock(return_value=resolved)
        with mock.patch("socket.getaddrinfo", original):
            guard = LoopbackSocketGuard()
            try:
                guard.install()
                self.assertEqual(socket.getaddrinfo("localhost", 80), resolved)
                self.assertEqual(socket.getaddrinfo("127.0.0.1", 80), resolved)
                self.assertEqual(
                    original.call_args_list,
                    [mock.call("localhost", 80), mock.call("127.0.0.1", 80)],
                )

                with self.assertRaises(PermissionError):
                    socket.getaddrinfo("example.invalid", 443)
                self.assertEqual(original.call_count, 2)
                self.assertEqual(guard.blocked_attempts, 1)
            finally:
                guard.restore_for_tests()

    def test_ready_events_write_one_atomic_fixed_schema_receipt_and_quit(self):
        with tempfile.TemporaryDirectory() as temporary, self.offline_environment():
            destination = Path(temporary) / "private" / "core-ready.json"
            guard = SimpleNamespace(active=True, blocked_attempts=0)
            proof = CoreReleaseProof(destination, guard, timeout_seconds=2)
            app = self.proof_app()

            self.assertTrue(proof.attach(app))
            proof.note_formatter_ready("rules")
            self.assertFalse(destination.exists())
            proof.note_model_ready()

            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                EXPECTED_RECEIPT,
            )
            self.assertNotIn(str(destination), destination.read_text(encoding="utf-8"))
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])
            app.quit.assert_called_once_with()

    def test_core_receipt_validator_requires_exact_keys_types_and_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "core-ready.json"
            receipt.write_text(json.dumps(EXPECTED_RECEIPT), encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertEqual(validate_main([str(receipt)]), 0)

            invalid_payloads = (
                {**EXPECTED_RECEIPT, "machine_path": "forbidden"},
                {key: value for key, value in EXPECTED_RECEIPT.items() if key != "ollama"},
                {**EXPECTED_RECEIPT, "blocked_attempts": False},
                {**EXPECTED_RECEIPT, "network_policy": "unrestricted"},
            )
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    receipt.write_text(json.dumps(payload), encoding="utf-8")
                    with redirect_stdout(StringIO()):
                        self.assertEqual(validate_main([str(receipt)]), 1)

    def test_ollama_enabled_is_a_hard_precondition_failure(self):
        with tempfile.TemporaryDirectory() as temporary, self.offline_environment():
            destination = Path(temporary) / "core-ready.json"
            proof = CoreReleaseProof(
                destination,
                SimpleNamespace(active=True, blocked_attempts=0),
                timeout_seconds=2,
            )
            app = self.proof_app(use_ollama=True)

            self.assertFalse(proof.attach(app))
            self.assertFalse(destination.exists())
            app.quit.assert_called_once_with()

    def test_ollama_autostart_is_a_hard_precondition_failure(self):
        with tempfile.TemporaryDirectory() as temporary, self.offline_environment():
            destination = Path(temporary) / "core-ready.json"
            proof = CoreReleaseProof(
                destination,
                SimpleNamespace(active=True, blocked_attempts=0),
                timeout_seconds=2,
            )
            app = self.proof_app(autostart_ollama=True)

            self.assertFalse(proof.attach(app))
            self.assertFalse(destination.exists())
            app.quit.assert_called_once_with()

    def test_blocked_attempt_or_non_rule_formatter_cannot_create_success(self):
        cases = ((1, "rules"), (0, "ollama"))
        for blocked, cleanup_path in cases:
            with self.subTest(blocked=blocked, cleanup_path=cleanup_path):
                with tempfile.TemporaryDirectory() as temporary, self.offline_environment():
                    destination = Path(temporary) / "core-ready.json"
                    proof = CoreReleaseProof(
                        destination,
                        SimpleNamespace(active=True, blocked_attempts=blocked),
                        timeout_seconds=2,
                    )
                    app = self.proof_app()
                    self.assertTrue(proof.attach(app))
                    proof.note_model_ready()
                    proof.note_formatter_ready(cleanup_path)
                    self.assertFalse(destination.exists())
                    app.quit.assert_called_once_with()

    def test_frozen_and_module_entrypoints_install_guard_before_app_import(self):
        root = Path(__file__).resolve().parents[1]
        for entrypoint in (root / "scripts" / "frozen_entry.py", root / "speakr" / "__main__.py"):
            with self.subTest(entrypoint=entrypoint.name):
                source = entrypoint.read_text(encoding="utf-8")
                self.assertLess(
                    source.index("install_core_proof_from_environment()"),
                    source.index("from speakr.app import main"),
                )

    def test_application_lifecycle_publishes_real_model_and_formatter_events(self):
        proof = mock.Mock()
        app = SpeakrApp.__new__(SpeakrApp)
        app._release_core_proof = proof
        app.enabled = True
        app._shutting_down = False
        app.config = _Config(
            {
                "model": "tiny",
                "device": "cpu",
                "formatting": {"enabled": True, "use_ollama": False},
            }
        )
        app.transcriber = SimpleNamespace(
            load=mock.Mock(),
            model_in_use="tiny",
            device_in_use="cpu",
            compute_type_in_use="int8",
        )
        app.formatter = SimpleNamespace(_ollama_ok=None, ensure_ollama=mock.Mock())
        app.interface_state = InterfaceState({"availability": "starting"})
        app._legacy_state = mock.Mock()
        app._notify_settings = mock.Mock()

        app._prepare_formatter()
        app._load_model()

        app.formatter.ensure_ollama.assert_not_called()
        proof.note_formatter_ready.assert_called_once_with("rules")
        proof.note_model_ready.assert_called_once_with()
        self.assertEqual(app.interface_state.snapshot()["cleanup_path"], "rules")
        self.assertEqual(app.interface_state.snapshot()["availability"], "ready")

    def test_core_precondition_failure_prevents_service_threads(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app._core_started = False
        app._shutting_down = False
        app._release_core_proof = mock.Mock()
        app._release_core_proof.attach.return_value = False

        with mock.patch("speakr.app.threading.Thread") as thread_type:
            app._start_core()

        self.assertTrue(app._core_started)
        app._release_core_proof.attach.assert_called_once_with(app)
        thread_type.assert_not_called()


if __name__ == "__main__":
    unittest.main()
