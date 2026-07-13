from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_release
from scripts.validate_release_receipt import EXPECTED_KEYS, validate_receipt


ROOT = Path(__file__).resolve().parents[1]


class ReleaseBuilderTests(unittest.TestCase):
    def test_release_dependencies_and_pyinstaller_contract_are_pinned(self):
        requirements = (ROOT / "requirements-release.txt").read_text(encoding="utf-8")
        dependency_lines = {
            line.strip()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("PyInstaller==6.21.0", dependency_lines)
        self.assertIn("PySide6-Essentials==6.11.1", dependency_lines)
        self.assertFalse(any(">=" in line or "~=" in line for line in dependency_lines))

        arguments = build_release.pyinstaller_arguments()
        self.assertIn("--clean", arguments)
        self.assertIn("--noconfirm", arguments)
        self.assertNotIn("PySide6.QtNetwork", arguments)
        for forbidden in build_release.FORBIDDEN_QT_MODULES:
            self.assertIn(forbidden, arguments)

        data_arguments = [
            arguments[index + 1]
            for index, value in enumerate(arguments[:-1])
            if value == "--add-data"
        ]
        normalized = [value.replace("\\", "/") for value in data_arguments]
        self.assertTrue(
            any(
                "speakr/ui/native_interface_capabilities.json" in value
                and value.endswith("speakr/ui")
                for value in normalized
            )
        )
        self.assertTrue(
            any("speakr/ui/qml" in value and value.endswith("speakr/ui/qml")
                for value in normalized)
        )

    def test_platform_specific_builder_paths_do_not_drift(self):
        with mock.patch.object(build_release.sys, "platform", "darwin"):
            mac = build_release.pyinstaller_arguments()
        with mock.patch.object(build_release.sys, "platform", "win32"):
            windows = build_release.pyinstaller_arguments()

        self.assertIn("pystray._darwin", mac)
        self.assertIn("--osx-bundle-identifier", mac)
        self.assertIn("pystray._win32", windows)
        self.assertIn("comtypes.stream", windows)
        self.assertNotIn("--osx-bundle-identifier", windows)


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        cls.mac_script = (ROOT / "package_mac.sh").read_text(encoding="utf-8")
        cls.installer = (ROOT / "scripts" / "installer.iss").read_text(
            encoding="utf-8"
        )

    def test_manual_dispatch_cannot_publish_and_publisher_waits_for_both(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertEqual(self.workflow.count('publish="true"'), 1)
        publish_assignment = self.workflow.index('publish="true"')
        push_gate = self.workflow.rfind(
            'if [ "$GITHUB_EVENT_NAME" = "push" ]; then', 0, publish_assignment
        )
        manual_branch = self.workflow.rfind("elif", 0, publish_assignment)
        self.assertGreater(push_gate, manual_branch)
        self.assertIn(
            "needs: [release_context, mac_dmg, windows_installer]", self.workflow
        )
        self.assertIn(
            "if: needs.release_context.outputs.publish == 'true'", self.workflow
        )
        self.assertEqual(self.workflow.count("softprops/action-gh-release"), 1)
        self.assertIn("v[0-9]+\\.[0-9]+\\.[0-9]+", self.workflow)
        self.assertIn("cancel-in-progress:", self.workflow)
        self.assertEqual(self.workflow.count("git merge-base --is-ancestor"), 2)
        self.assertIsNone(
            re.search(r"(?m)^\s*-?\s*uses:\s+[^\s]+@v[0-9]+\s*(?:#.*)?$", self.workflow)
        )

    def test_exact_artifacts_are_signed_or_clearly_non_distributable(self):
        self.assertIn("MACOS_CERTIFICATE_P12", self.workflow)
        self.assertIn("xcrun notarytool submit Speakr-notarization.zip", self.workflow)
        self.assertIn("xcrun stapler staple dist/Speakr.app", self.workflow)
        self.assertIn("xcrun notarytool submit Speakr.dmg", self.workflow)
        self.assertIn("DMG creation attempt $attempt was busy; retrying", self.workflow)
        self.assertIn("ditto \"$mounted_app\" \"$installroot/Speakr.app\"", self.workflow)
        self.assertIn("lipo -archs", self.workflow)
        self.assertIn("WINDOWS_CERTIFICATE_PFX", self.workflow)
        self.assertIn("WINDOWS_SIGNTOOL sign", self.workflow)
        self.assertIn("dist\\Speakr\\Speakr.exe", self.workflow)
        self.assertIn("Speakr-Setup.exe", self.workflow)
        self.assertIn("NON-DISTRIBUTABLE", self.workflow)
        self.assertNotIn("codesign --force --deep", self.workflow)
        self.assertNotIn("codesign --force --deep", self.mac_script)

    def test_pinned_build_tools_and_runtime_receipt_are_release_gates(self):
        self.assertIn("runs-on: macos-15", self.workflow)
        self.assertIn("runs-on: windows-2025", self.workflow)
        self.assertIn("innosetup --version=6.7.1", self.workflow)
        self.assertIn('innosetup|6.7.1', self.workflow)
        self.assertIn("requirements-release.txt", self.workflow)
        self.assertIn("scripts/build_release.py", self.workflow)
        self.assertIn("scripts/scan_artifact_privacy.py", self.workflow)
        self.assertIn("SPEAKR_RELEASE_PROOF_PATH", self.workflow)
        self.assertIn("scripts/validate_release_receipt.py", self.workflow)
        self.assertIn("SPEAKR_RELEASE_CORE_PROOF_PATH", self.workflow)
        self.assertIn("scripts/validate_release_core_receipt.py", self.workflow)
        self.assertIn("scripts/release_manifest.py create", self.workflow)
        self.assertIn("scripts/release_manifest.py verify", self.workflow)
        self.assertIn("Speakr-macOS-manifest.json", self.workflow)
        self.assertIn("Speakr-Windows-manifest.json", self.workflow)
        self.assertEqual(self.workflow.count('WhisperModel("tiny"'), 2)
        self.assertIn('autostart_ollama = $false', self.workflow)
        self.assertIn('"autostart_ollama": False', self.workflow)
        self.assertIn("$process.ExitCode -ne 0", self.workflow)
        self.assertIn('if [ "$status" -ne 0 ]', self.workflow)
        self.assertNotIn("speakr.cloud", self.installer.casefold())


class ReleaseReceiptValidationTests(unittest.TestCase):
    def _valid_receipt(self):
        return {
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

    def test_validator_accepts_only_the_fixed_sanitized_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            payload = self._valid_receipt()
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(validate_receipt(path), payload)
            self.assertEqual(set(payload), EXPECTED_KEYS)

            payload["window_title"] = "private document"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid release receipt keys"):
                validate_receipt(path)


if __name__ == "__main__":
    unittest.main()
