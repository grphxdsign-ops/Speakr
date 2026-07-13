from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, Property, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge


class _App:
    def __init__(self, text_scale: int):
        self.interface_state = InterfaceState(
            {
                "availability": "ready",
                "enabled": True,
                "hotkey": "right ctrl",
                "model": "auto",
                "device": "cpu",
                "cleanup_path": "rules",
            }
        )
        self.enabled = True
        self._text_scale = text_scale

    def settings_snapshot(self):
        return {
            "ui": {
                "onboarding_complete": True,
                "open_window_on_start": False,
                "theme": "dark",
                "density": "comfortable",
                "text_scale": self._text_scale,
                "reduced_motion": "reduce",
                "visual_effects": "system",
                "hud_visibility": "while_dictating",
                "hud_size": "standard",
                "hud_edge": "bottom",
                "hud_scale": 100,
                "background_announcements": False,
            },
            "hotkey": "right ctrl",
            "toggle_mode": False,
            "sample_rate": 16000,
            "active_sample_rate": 16000,
            "app_tones": {},
            "hotkey_exclude_apps": [],
        }

    @staticmethod
    def practice_snapshot():
        return {
            "active": False,
            "processing": False,
            "hasResult": False,
            "heard": "",
            "wouldType": "",
            "level": "silent",
            "message": "",
        }

    @staticmethod
    def list_manual_words():
        return []

    @staticmethod
    def list_learned_words():
        return []

    @staticmethod
    def subscribe_settings(_callback):
        return lambda: None

    @staticmethod
    def subscribe_practice(_callback):
        return lambda: None

    @staticmethod
    def navigate(_page):
        return True

    @staticmethod
    def clear_practice():
        return True

    @staticmethod
    def stop_practice():
        return True


class _NativeWindow(QObject):
    @Property(str, constant=True)
    def material(self):
        return "mica"

    @Property(str, constant=True)
    def effectTier(self):
        return "full"


class SettingsHelpQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]
        cls.qml = cls.root / "speakr" / "ui" / "qml"

    def _load_main(self, text_scale: int):
        app = _App(text_scale)
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        native_window = _NativeWindow(engine)
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.rootContext().setContextProperty("nativeWindow", native_window)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        engine.load(QUrl.fromLocalFile(str(self.qml / "Main.qml")))
        self.assertEqual(len(engine.rootObjects()), 1, warnings)
        main = engine.rootObjects()[0]
        main.setWidth(640)
        main.setHeight(520)
        main.show()
        self.qapp.processEvents()
        self.qapp.processEvents()
        return app, bridge, native_window, engine, main, warnings

    def test_visual_effects_search_and_effective_material_are_truthful(self):
        app, bridge, native, engine, main, warnings = self._load_main(100)
        self.assertIsNotNone(app)
        self.assertIsNotNone(native)
        try:
            main.setProperty("currentPage", "settings")
            self.qapp.processEvents()
            settings = main.findChild(QObject, "settingsPage")
            search = main.findChild(QObject, "settingsSearchField")
            summary = main.findChild(QObject, "settingsResultSummary")
            appearance = main.findChild(QObject, "effectiveAppearanceStatus")
            self.assertIsNotNone(settings)
            self.assertIsNotNone(search)
            self.assertIsNotNone(summary)
            self.assertIsNotNone(appearance)

            settings.setProperty("selectedCategory", "Accessibility")
            search.setProperty("text", "visual effects")
            self.qapp.processEvents()
            self.assertEqual(settings.property("visibleResultCount"), 1)
            self.assertIn("Accessibility", summary.property("text"))
            self.assertIn("Full effects", appearance.property("label"))
            self.assertIn("Windows Mica", appearance.property("label"))

            search.setProperty("text", "no setting has this phrase")
            self.qapp.processEvents()
            self.assertEqual(settings.property("visibleResultCount"), 0)
            empty = main.findChild(QObject, "settingsEmptyState")
            self.assertTrue(empty.property("visible"))
            self.assertEqual(warnings, [])
        finally:
            bridge.close()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_settings_and_help_reflow_at_640_by_520_and_scaled_text(self):
        for scale in (100, 150, 200):
            with self.subTest(scale=scale):
                app, bridge, native, engine, main, warnings = self._load_main(scale)
                self.assertIsNotNone(app)
                self.assertIsNotNone(native)
                try:
                    for page_name, page_object, surface_names in (
                        (
                            "settings",
                            "settingsPage",
                            ("settingsSearchSurface", "settingsCategorySurface", "settingsRowsSurface"),
                        ),
                        (
                            "help",
                            "helpPage",
                            ("helpHeroSurface", "repairSetupSurface", "localSetupSurface", "localFilesSurface"),
                        ),
                    ):
                        main.setProperty("currentPage", page_name)
                        self.qapp.processEvents()
                        page = main.findChild(QObject, page_object)
                        self.assertIsNotNone(page)
                        self.assertGreater(page.width(), 0)
                        for name in surface_names:
                            surface = main.findChild(QObject, name)
                            self.assertIsNotNone(surface, name)
                            self.assertGreater(surface.width(), 0, (scale, name))
                            self.assertGreaterEqual(surface.x(), 0, (scale, name))
                            self.assertLessEqual(
                                surface.x() + surface.width(),
                                page.width() + 1,
                                (scale, name),
                            )

                    search = main.findChild(QObject, "settingsSearchField")
                    self.assertGreaterEqual(search.height(), 44)
                    self.assertLessEqual(search.width(), main.width())
                    self.assertEqual(warnings, [])
                finally:
                    bridge.close()
                    engine.deleteLater()
                    self.qapp.processEvents()

    def test_help_reset_actions_are_guarded(self):
        source = (self.qml / "HelpPage.qml").read_text(encoding="utf-8")
        self.assertIn('onClicked: root.requestReset("interface")', source)
        self.assertIn('onClicked: root.requestReset("privacy")', source)
        self.assertIn("onClicked: root.confirmReset()", source)
        self.assertIn('objectName: "resetConfirmation"', source)

    def test_page_contracts_use_shared_tokens_and_keep_local_boundaries(self):
        settings = (self.qml / "SettingsPage.qml").read_text(encoding="utf-8")
        help_page = (self.qml / "HelpPage.qml").read_text(encoding="utf-8")
        combined = settings + "\n" + help_page

        self.assertIn('path: "ui.visual_effects"', settings)
        for choice in ('"system"', '"full"', '"reduced"', '"off"'):
            self.assertIn(choice, settings)
        for privacy_path in (
            "keep_mic_stream_open",
            "preroll_seconds",
            "screen_context.enabled",
            "formatting.include_recent_context",
            "log_transcripts",
            "restore_clipboard",
        ):
            self.assertRegex(
                settings,
                rf'category: qsTr\("Privacy"\).*?path: "{re.escape(privacy_path)}"',
            )
        for advanced_path in (
            "device",
            "compute_type",
            "streaming.enabled",
            "streaming.chunk_seconds",
            "min_duration_seconds",
            "max_duration_seconds",
            "injection",
            "formatting.ollama_url",
            "formatting.timeout_seconds",
            "formatting.keep_alive",
        ):
            self.assertIn(f'path: "{advanced_path}"', settings)

        self.assertGreaterEqual(settings.count("GlassSurface {"), 5)
        self.assertGreaterEqual(help_page.count("GlassSurface {"), 5)
        self.assertNotIn("Timer {", combined)
        self.assertNotRegex(combined, r"#[0-9A-Fa-f]{3,8}")
        self.assertNotIn("https://", combined)
        self.assertNotIn("ShaderEffect", combined)
        self.assertNotIn("Animation.Infinite", combined)
        self.assertNotRegex(combined, r"\bText\s*\{")
        self.assertNotRegex(combined, r"\bTextArea\s*\{")


if __name__ == "__main__":
    unittest.main()
