from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import scripts.scan_artifact_privacy as scanner
from scripts.check_qt_build_environment import boundary_violations


class ArtifactPrivacyScanTests(unittest.TestCase):
    def _write_required(self, root: Path, *, mac_bundle: bool = False) -> Path:
        base = (
            root / "Speakr.app" / "Contents" / "Resources"
            if mac_bundle
            else root / "Speakr" / "_internal"
        )
        qml = base / "speakr" / "ui" / "qml"
        qml.mkdir(parents=True)
        (qml / "Main.qml").write_text(
            'import QtQuick\nItem { property string endpoint: '
            '"http://127.0.0.1:11434" }',
            encoding="utf-8",
        )
        (qml / "Hud.qml").write_text("import QtQuick\nItem {}", encoding="utf-8")
        marker = base / "speakr" / "ui" / "native_interface_capabilities.json"
        marker.write_text(
            json.dumps(
                {"controller": "NativeWindowController", "schema": 1},
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        icon = base / "assets" / "icon.png"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"\x89PNG\r\n\x1a\nlocal icon")

        notice = (
            base / "THIRD_PARTY_NOTICES.txt"
            if mac_bundle
            else root / "Speakr" / "THIRD_PARTY_NOTICES.txt"
        )
        notice.write_text(
            "Speakr includes Qt for Python / PySide6-Essentials 6.11.1.\n"
            "Qt is offered under the LGPL-3.0-only license.\n",
            encoding="utf-8",
        )

        if mac_bundle:
            info = root / "Speakr.app" / "Contents" / "Info.plist"
            info.write_text(
                '<?xml version="1.0"?><!DOCTYPE plist PUBLIC "-//Apple//DTD '
                'PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
                "<plist><dict/></plist>",
                encoding="utf-8",
            )
        return root / "Speakr.app" if mac_bundle else root / "Speakr"

    def test_accepts_windows_onedir_loopback_and_hugging_face_model_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            source = artifact / "_internal" / "speakr" / "transcriber.py"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                'FIRST_RUN_MODEL_SOURCE = "https://huggingface.co/Systran/faster-whisper"',
                encoding="utf-8",
            )

            self.assertEqual(scanner.scan_artifact(artifact), [])
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(scanner.main([str(artifact)]), 0)
            self.assertNotIn(str(Path(temporary)), output.getvalue())

    def test_accepts_macos_app_bundle_and_inert_apple_plist_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary), mac_bundle=True)
            self.assertEqual(scanner.scan_artifact(artifact), [])

    def test_rejects_browser_engine_and_addons_names_on_both_platforms(self):
        for mac_bundle in (False, True):
            with self.subTest(mac_bundle=mac_bundle), tempfile.TemporaryDirectory() as temporary:
                artifact = self._write_required(Path(temporary), mac_bundle=mac_bundle)
                base = (
                    artifact / "Contents" / "Frameworks"
                    if mac_bundle
                    else artifact / "_internal"
                )
                forbidden = (
                    base / "QtWebEngineProcess.exe",
                    base / "WebView2Loader.dll",
                    base / "msedgewebview2.dll",
                    base / "libcef.dll",
                    base / "PySide6" / "QtWebView.pyd",
                    base / "PySide6" / "QtWebChannel.pyd",
                    base / "PySide6" / "Addons" / "module.pyd",
                    base / "PySide6_Addons.dll",
                    base / "PySide6" / "QtCharts.pyd",
                    base / "PySide6" / "Qt6Graphs.dll",
                    base / "PySide6" / "libQt6Pdf.so.6",
                    base / "resources.pak",
                )
                for path in forbidden:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"")

                findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
                for needle in (
                    "qtwebengineprocess",
                    "webview2loader",
                    "msedgewebview2",
                    "libcef",
                    "qtwebview",
                    "qtwebchannel",
                    "addons",
                    "qtcharts",
                    "qt6graphs",
                    "libqt6pdf",
                    "resources.pak",
                ):
                    self.assertIn(needle, findings)

    def test_rejects_renamed_browser_and_sdk_binaries_by_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            hidden_browser = artifact / "_internal" / "vendor_runtime.bin"
            hidden_browser.write_bytes(b"safe prefix\0WebView2Loader\0safe suffix")
            hidden_sdk = artifact / "_internal" / "diagnostics.bin"
            hidden_sdk.write_bytes("prefix crashpad_handler suffix".encode("utf-16le"))

            findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
            self.assertIn("embedded-browser engine marker", findings)
            self.assertIn("telemetry/crash-report sdk marker", findings)
            self.assertIn("vendor_runtime.bin", findings)
            self.assertIn("diagnostics.bin", findings)

    def test_rejects_forbidden_archive_members_and_nested_archives(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            nested_bytes = StringIO()
            # zipfile needs bytes, so create the nested archive on disk first.
            nested_path = Path(temporary) / "nested.zip"
            with zipfile.ZipFile(nested_path, "w") as nested:
                nested.writestr("plugins/sentry_sdk/__init__.py", b"")
            archive_path = artifact / "_internal" / "base_library.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("PySide6/QtWebEngineCore.pyd", b"")
                archive.writestr("PySide6/QtMultimedia.pyd", b"")
                archive.writestr("nested.zip", nested_path.read_bytes())
            del nested_bytes

            findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
            self.assertIn("qtwebenginecore", findings)
            self.assertIn("qtmultimedia", findings)
            self.assertIn("sentry_sdk", findings)

    def test_inspects_pyinstaller_carchive_and_embedded_pyz_module_names(self):
        class FakeEmbedded:
            toc = {
                "sentry_sdk.client": object(),
                "PySide6.QtCharts": object(),
                "PySide6.QtNetwork": object(),
            }

        class FakeReader:
            def __init__(self, _filename):
                self.toc = {"frozen_entry": object(), "PYZ.pyz": object()}

            def open_embedded_archive(self, name):
                self.assert_name = name
                return FakeEmbedded()

        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            (artifact / "Speakr.exe").write_bytes(b"harmless executable fixture")
            with mock.patch.object(scanner, "_CArchiveReader", FakeReader):
                findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
            self.assertIn("sentry_sdk", findings)
            self.assertIn("qtcharts", findings)
            self.assertNotIn("qtnetwork", findings)

    def test_fails_closed_when_pyinstaller_reader_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            (artifact / "Speakr.exe").write_bytes(b"harmless executable fixture")
            with mock.patch.object(scanner, "_CArchiveReader", None):
                findings = "\n".join(scanner.scan_artifact(artifact))
            self.assertIn("PyInstaller reader is unavailable", findings)

    def test_rejects_remote_urls_in_ui_config_text_and_archive_but_allows_loopback(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            qml = artifact / "_internal" / "speakr" / "ui" / "qml" / "Main.qml"
            qml.write_text(
                'import QtQuick\nItem { property string local: "http://localhost:11434"; '
                'property string ipv6: "http://[::1]:11434"; '
                'property string remote: '
                '"https://user:secret@example.invalid/asset.svg?token=private" }',
                encoding="utf-8",
            )
            config = artifact / "_internal" / "vendor" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"updates":"https://updates.invalid/feed"}', encoding="utf-8")
            metadata = artifact / "release-notes.txt"
            metadata.write_text("Download: https://download.invalid/Speakr.exe", encoding="utf-8")
            archive_path = artifact / "_internal" / "resources.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "speakr/ui/recovery.html",
                    '<script src="https://cdn.invalid/speakr.js"></script>',
                )

            findings = "\n".join(scanner.scan_artifact(artifact))
            self.assertIn("https://example.invalid/asset.svg", findings)
            self.assertIn("https://updates.invalid/feed", findings)
            self.assertIn("https://download.invalid/Speakr.exe", findings)
            self.assertIn("https://cdn.invalid/speakr.js", findings)
            self.assertNotIn("user:secret", findings)
            self.assertNotIn("token=private", findings)
            self.assertNotIn("http://localhost:11434", findings)
            self.assertNotIn("http://[::1]:11434", findings)

    def test_allows_transitive_qtnetwork_files_but_rejects_app_api_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            binding = artifact / "_internal" / "PySide6" / "QtNetwork.pyd"
            binding.parent.mkdir(parents=True)
            binding.write_bytes(b"QtNetwork QNetworkAccessManager runtime binding")
            native = artifact / "_internal" / "Qt6Network.dll"
            native.write_bytes(b"Qt network transport symbols")
            self.assertEqual(scanner.scan_artifact(artifact), [])

            app_qml = artifact / "_internal" / "speakr" / "ui" / "Network.qml"
            app_qml.write_text(
                "import QtQuick\nimport QtNetwork\nItem { property var manager: "
                "QNetworkAccessManager {} }",
                encoding="utf-8",
            )
            findings = "\n".join(scanner.scan_artifact(artifact))
            self.assertIn("imports/uses QtNetwork", findings)
            self.assertIn("Network.qml", findings)

    def test_rejects_updater_telemetry_and_crash_sdk_names_and_source_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            files = (
                artifact / "_internal" / "sentry_sdk" / "__init__.py",
                artifact / "_internal" / "Sparkle.framework" / "Sparkle",
                artifact / "_internal" / "WinSparkle.dll",
                artifact / "_internal" / "updater.exe",
                artifact / "_internal" / "bugsnag.pyd",
            )
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")
            app_source = artifact / "_internal" / "speakr" / "metrics.py"
            app_source.parent.mkdir(parents=True, exist_ok=True)
            app_source.write_text("import posthog\nposthog.init('local')", encoding="utf-8")

            findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
            for needle in ("sentry_sdk", "sparkle.framework", "winsparkle", "updater.exe", "bugsnag"):
                self.assertIn(needle, findings)
            self.assertIn("telemetry/crash-report sdk use", findings)

    def test_requires_valid_qml_icon_qt_notice_and_exact_native_marker(self):
        mutations = {
            "Main.qml": lambda path: path.write_text("Item {}", encoding="utf-8"),
            "Hud.qml": lambda path: path.write_bytes(b"\xff\xfe"),
            "icon.png": lambda path: path.write_bytes(b"not a png"),
            "THIRD_PARTY_NOTICES.txt": lambda path: path.write_text(
                "Qt for Python, proprietary only", encoding="utf-8"
            ),
            "native_interface_capabilities.json": lambda path: path.write_text(
                '{"controller":"NativeWindowController","schema":1,"host_path":"C:/private"}',
                encoding="utf-8",
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                artifact = self._write_required(Path(temporary))
                matches = list(artifact.rglob(name))
                self.assertEqual(len(matches), 1)
                mutate(matches[0])
                findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
                self.assertIn("required", findings)
                self.assertIn("invalid", findings)

    def test_reports_each_missing_required_resource_without_host_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "Speakr"
            artifact.mkdir()
            findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
            for needle in (
                "main.qml",
                "hud.qml",
                "assets/icon.png",
                "third_party_notices.txt",
                "native_interface_capabilities.json",
            ):
                self.assertIn(needle, findings)
            self.assertNotIn(str(Path(temporary)).casefold(), findings)

    def test_archive_safety_rejects_traversal_oversize_and_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            unsafe = artifact / "_internal" / "unsafe.zip"
            with zipfile.ZipFile(unsafe, "w") as archive:
                archive.writestr("../../private.txt", b"secret")
                archive.writestr("large.bin", b"x" * 128)
            corrupt = artifact / "_internal" / "corrupt.zip"
            corrupt.write_bytes(b"not a zip")

            with mock.patch.object(scanner, "_MAX_ARCHIVE_MEMBER_BYTES", 64):
                findings = "\n".join(scanner.scan_artifact(artifact)).casefold()
            self.assertIn("unsafe member path", findings)
            self.assertIn("exceeds safe inspection limit", findings)
            self.assertIn("archive could not be safely inspected", findings)
            self.assertNotIn("private.txt", findings)

    def test_external_symlink_is_rejected_without_disclosing_target(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            artifact = self._write_required(Path(temporary))
            target = Path(outside) / "private.txt"
            target.write_text("secret", encoding="utf-8")
            link = artifact / "_internal" / "external-link.txt"
            try:
                os.symlink(target, link)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable in this test environment: {type(exc).__name__}")

            findings = "\n".join(scanner.scan_artifact(artifact))
            self.assertIn("symlink escapes the artifact boundary", findings)
            self.assertNotIn(str(target), findings)
            self.assertNotIn(outside, findings)

    def test_cli_errors_do_not_echo_nonexistent_host_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "private" / "Speakr"
            stderr = StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(scanner.main([str(missing)]), 1)
            self.assertNotIn(str(Path(temporary)), stderr.getvalue())
            self.assertIn("artifact does not exist", stderr.getvalue())

    def test_release_environment_is_essentials_only(self):
        self.assertEqual(boundary_violations(), [])


if __name__ == "__main__":
    unittest.main()
