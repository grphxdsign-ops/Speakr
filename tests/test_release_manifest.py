from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.release_manifest import create_manifest, verify_manifest, write_manifest


class ReleaseManifestTests(unittest.TestCase):
    def test_direct_script_entrypoint_resolves_sibling_validators(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/release_manifest.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _fixture(self, root: Path):
        artifact = root / "Speakr-Setup.exe"
        lock = root / "requirements-release.txt"
        native = root / "native.json"
        core = root / "core.json"
        artifact.write_bytes(b"exact signed artifact")
        lock.write_bytes(b"PyInstaller==6.21.0\r\n")
        native.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "frontend": "native",
                    "tray_visible": True,
                    "main_window_required": True,
                    "main_window_visible": True,
                    "main_window_exposed": True,
                    "material": "scene_glass",
                    "effect_tier": "reduced",
                    "native_material_available": False,
                    "chrome": "system_frame",
                    "renderer": "software",
                }
            ),
            encoding="utf-8",
        )
        core.write_text(
            json.dumps(
                {
                    "blocked_attempts": 0,
                    "cleanup_path": "rules",
                    "core_ready": True,
                    "guard_active": True,
                    "model_ready": True,
                    "model_source": "preseeded_local",
                    "network_policy": "loopback_only",
                    "offline_mode": True,
                    "ollama": "disabled",
                    "schema": 1,
                }
            ),
            encoding="utf-8",
        )
        return artifact, lock, native, core

    def test_manifest_binds_source_artifact_lock_signature_and_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, lock, native, core = self._fixture(root)
            payload = create_manifest(
                artifact=artifact,
                dependency_lock=lock,
                native_receipt=native,
                core_receipt=core,
                source_sha="a" * 40,
                tag="v1.2.3",
                version="1.2.3",
                platform="windows",
                architecture="x86_64",
                signed=True,
                notarized=False,
                signature_kind="authenticode",
                signer_identity="CN=Speakr Release",
                signer_team="none",
            )
            manifest = root / "Speakr-Windows-manifest.json"
            write_manifest(manifest, payload)

            # The manifest must survive Git's LF/CRLF checkout policy when the
            # two platform artifacts are verified together on Linux.
            lock.write_bytes(b"PyInstaller==6.21.0\n")

            self.assertEqual(
                verify_manifest(
                    manifest,
                    artifact=artifact,
                    dependency_lock=lock,
                    source_sha="a" * 40,
                    tag="v1.2.3",
                ),
                [],
            )
            self.assertEqual(payload["runtime"]["core"]["blocked_attempts"], 0)
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_tagged_windows_manifest_may_be_explicitly_unsigned(self):
        # A tag without Windows Authenticode credentials publishes an
        # explicitly-unsigned installer; the manifest must verify cleanly.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, lock, native, core = self._fixture(root)
            payload = create_manifest(
                artifact=artifact,
                dependency_lock=lock,
                native_receipt=native,
                core_receipt=core,
                source_sha="c" * 40,
                tag="v1.2.3",
                version="1.2.3",
                platform="windows",
                architecture="x86_64",
                signed=False,
                notarized=False,
                signature_kind="unsigned",
                signer_identity="unsigned",
                signer_team="none",
            )
            manifest = root / "Speakr-Windows-manifest.json"
            write_manifest(manifest, payload)
            self.assertEqual(
                verify_manifest(
                    manifest,
                    artifact=artifact,
                    dependency_lock=lock,
                    source_sha="c" * 40,
                    tag="v1.2.3",
                ),
                [],
            )

    def test_tagged_windows_manifest_rejects_ad_hoc_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, lock, native, core = self._fixture(root)
            payload = create_manifest(
                artifact=artifact,
                dependency_lock=lock,
                native_receipt=native,
                core_receipt=core,
                source_sha="d" * 40,
                tag="v1.2.3",
                version="1.2.3",
                platform="windows",
                architecture="x86_64",
                signed=False,
                notarized=False,
                signature_kind="ad_hoc",
                signer_identity="ad_hoc",
                signer_team="none",
            )
            manifest = root / "Speakr-Windows-manifest.json"
            write_manifest(manifest, payload)
            errors = verify_manifest(
                manifest,
                artifact=artifact,
                dependency_lock=lock,
                source_sha="d" * 40,
                tag="v1.2.3",
            )
            self.assertIn(
                "tagged Windows evidence is neither Authenticode signed"
                " nor explicitly unsigned",
                errors,
            )

    def test_tagged_macos_manifest_still_requires_notarized_developer_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, lock, native, core = self._fixture(root)
            artifact = artifact.rename(artifact.with_name("Speakr.dmg"))
            payload = create_manifest(
                artifact=artifact,
                dependency_lock=lock,
                native_receipt=native,
                core_receipt=core,
                source_sha="e" * 40,
                tag="v1.2.3",
                version="1.2.3",
                platform="macos",
                architecture="arm64",
                signed=False,
                notarized=False,
                signature_kind="unsigned",
                signer_identity="unsigned",
                signer_team="none",
            )
            manifest = root / "Speakr-macOS-manifest.json"
            write_manifest(manifest, payload)
            errors = verify_manifest(
                manifest,
                artifact=artifact,
                dependency_lock=lock,
                source_sha="e" * 40,
                tag="v1.2.3",
            )
            self.assertIn("tagged macOS evidence is not signed and notarized", errors)

    def test_tampering_or_sensitive_receipt_expansion_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, lock, native, core = self._fixture(root)
            payload = create_manifest(
                artifact=artifact,
                dependency_lock=lock,
                native_receipt=native,
                core_receipt=core,
                source_sha="b" * 40,
                tag="",
                version="0.0.0-proof.1",
                platform="windows",
                architecture="x86_64",
                signed=False,
                notarized=False,
                signature_kind="unsigned",
                signer_identity="unsigned",
                signer_team="none",
            )
            manifest = root / "manifest.json"
            write_manifest(manifest, payload)
            artifact.write_bytes(b"tampered")
            errors = verify_manifest(
                manifest,
                artifact=artifact,
                dependency_lock=lock,
                source_sha="b" * 40,
                tag="",
            )
            self.assertIn("artifact hash does not match", errors)

            native_payload = json.loads(native.read_text(encoding="utf-8"))
            native_payload["window_title"] = "private document"
            native.write_text(json.dumps(native_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact schema"):
                create_manifest(
                    artifact=artifact,
                    dependency_lock=lock,
                    native_receipt=native,
                    core_receipt=core,
                    source_sha="b" * 40,
                    tag="",
                    version="0.0.0-proof.1",
                    platform="windows",
                    architecture="x86_64",
                    signed=False,
                    notarized=False,
                    signature_kind="unsigned",
                    signer_identity="unsigned",
                    signer_team="none",
                )


if __name__ == "__main__":
    unittest.main()
