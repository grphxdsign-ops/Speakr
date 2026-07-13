from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.scan_artifact_privacy import main, scan_artifact
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
        icon = base / "assets" / "icon.png"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"local icon")
        return root / "Speakr.app" if mac_bundle else root / "Speakr"

    def test_accepts_windows_onedir_with_loopback_ui_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            self.assertEqual(scan_artifact(artifact), [])
            with redirect_stdout(StringIO()):
                self.assertEqual(main([str(artifact)]), 0)

    def test_accepts_macos_app_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary), mac_bundle=True)
            self.assertEqual(scan_artifact(artifact), [])

    def test_rejects_browser_engine_and_addons_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            forbidden = (
                artifact / "_internal" / "QtWebEngineProcess.exe",
                artifact / "_internal" / "WebView2Loader.dll",
                artifact / "_internal" / "PySide6" / "QtWebView.pyd",
                artifact / "_internal" / "PySide6" / "QtWebChannel.pyd",
                artifact / "_internal" / "Chromium Resources.pak",
                artifact / "_internal" / "PySide6" / "Addons" / "module.pyd",
                artifact / "_internal" / "PySide6_Addons.dll",
                artifact / "_internal" / "PySide6" / "QtCharts.pyd",
                artifact / "_internal" / "PySide6" / "Qt6Charts.dll",
                artifact / "_internal" / "PySide6" / "libQt6Charts.so.6",
            )
            for path in forbidden:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")

            findings = "\n".join(scan_artifact(artifact)).casefold()
            self.assertIn("qtwebengineprocess", findings)
            self.assertIn("webview2loader", findings)
            self.assertIn("qtwebview", findings)
            self.assertIn("qtwebchannel", findings)
            self.assertIn("chromium resources", findings)
            self.assertIn("addons", findings)
            self.assertIn("qtcharts", findings)
            self.assertIn("qt6charts", findings)

    def test_release_environment_is_essentials_only(self):
        self.assertEqual(boundary_violations(), [])

    def test_rejects_remote_url_in_qml_but_not_localhost(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._write_required(Path(temporary))
            qml = artifact / "_internal" / "speakr" / "ui" / "qml" / "Main.qml"
            qml.write_text(
                'Item { property string local: "http://localhost:11434"; '
                'property string ipv6: "http://[::1]:11434"; '
                'property string remote: "https://example.invalid/asset.svg" }',
                encoding="utf-8",
            )

            findings = "\n".join(scan_artifact(artifact))
            self.assertIn("https://example.invalid/asset.svg", findings)
            self.assertNotIn("http://localhost:11434", findings)
            self.assertNotIn("http://[::1]:11434", findings)

    def test_requires_main_hud_and_icon(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "Speakr"
            artifact.mkdir()
            findings = "\n".join(scan_artifact(artifact)).casefold()
            self.assertIn("main.qml", findings)
            self.assertIn("hud.qml", findings)
            self.assertIn("assets/icon.png", findings)
            with redirect_stderr(StringIO()):
                self.assertEqual(main([str(artifact)]), 1)

    def test_qml_keeps_required_qtnetwork_binding_without_app_api_imports(self):
        repo = Path(__file__).resolve().parents[1]
        workflow = (repo / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        qt_ui = (repo / "speakr" / "qt_ui.py").read_text(encoding="utf-8")

        # PySide6.QtQml itself imports this binding through libshiboken.
        # Excluding it makes the packaged native UI choose browser recovery.
        self.assertNotIn("--exclude-module PySide6.QtNetwork", workflow)
        self.assertNotRegex(qt_ui, r"(?:from|import)\s+PySide6\.QtNetwork")
        self.assertNotRegex(qt_ui, r"from\s+PySide6\s+import[^\n]*QtNetwork")


if __name__ == "__main__":
    unittest.main()
