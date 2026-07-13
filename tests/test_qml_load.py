from __future__ import annotations

import os
import re
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge
from tests.qml_lifecycle import dispose_qml_fixture


class _App:
    def __init__(self, text_scale=100):
        self.interface_state = InterfaceState(
            {
                "availability": "ready",
                "enabled": True,
                "hotkey": "right ctrl",
            }
        )
        self.enabled = True
        self.text_scale = text_scale
        self.vocabulary_mutation_succeeds = False

    def settings_snapshot(self):
        return {
            "ui": {
                "onboarding_complete": True,
                "open_window_on_start": False,
                "theme": "system",
                "density": "comfortable",
                "text_scale": self.text_scale,
                "motion": "reduced",
                "hud_visibility": "while_dictating",
                "hud_size": "standard",
                "hud_edge": "bottom",
                "hud_scale": 100,
                "background_announcements": False,
            },
            "hotkey": "right ctrl",
            "toggle_mode": False,
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

    def add_word(self, _word):
        return self.vocabulary_mutation_succeeds

    def add_replacement(self, _heard, _intended):
        return self.vocabulary_mutation_succeeds


class QmlLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])

    def test_main_and_hud_load_without_qml_warnings(self):
        app = _App()
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        qml = Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"

        try:
            for name in ("Main.qml", "Hud.qml"):
                before = len(engine.rootObjects())
                engine.load(QUrl.fromLocalFile(str(qml / name)))
                self.assertEqual(len(engine.rootObjects()), before + 1, name)
            self.qapp.processEvents()

            roots = {root.objectName(): root for root in engine.rootObjects()}
            self.assertEqual(set(roots), {"mainWindow", "hudWindow"})
            main, hud = roots["mainWindow"], roots["hudWindow"]
            self.assertGreaterEqual(main.minimumWidth(), 640)
            self.assertGreaterEqual(main.minimumHeight(), 520)
            self.assertTrue(hud.flags() & Qt.WindowType.WindowTransparentForInput)
            self.assertTrue(hud.flags() & Qt.WindowType.WindowDoesNotAcceptFocus)
            self.assertFalse(main.isVisible())
            self.assertFalse(hud.isVisible())

            app.interface_state.latch_issue(
                "model_unavailable",
                "The local speech model is unavailable.",
                "retry_model",
            )
            self.qapp.processEvents()
            self.qapp.processEvents()
            self.assertFalse(main.isVisible())
            app.interface_state.dismiss_issue()

            app.interface_state.update(capture_job_id=6)
            app.interface_state.latch_issue(
                "microphone_unavailable",
                "Microphone access is needed.",
                "open_system_settings",
            )
            self.qapp.processEvents()
            self.assertFalse(main.isVisible())
            self.assertTrue(bool(hud.property("shouldShow")))
            app.interface_state.update(capture_job_id=0)
            self.qapp.processEvents()
            self.assertFalse(main.isVisible())
            self.assertFalse(bool(hud.property("shouldShow")))
            app.interface_state.dismiss_issue()

            vocabulary = main.findChild(QObject, "vocabularyPage")
            manual_word = main.findChild(QObject, "newManualWordField")
            self.assertIsNotNone(vocabulary)
            self.assertIsNotNone(manual_word)
            manual_word.setProperty("text", "Preserve Me")
            self.assertTrue(QMetaObject.invokeMethod(vocabulary, "submitWord"))
            self.assertEqual(manual_word.property("text"), "Preserve Me")
            app.vocabulary_mutation_succeeds = True
            self.assertTrue(QMetaObject.invokeMethod(vocabulary, "submitWord"))
            self.assertEqual(manual_word.property("text"), "")

            replacement_heard = main.findChild(QObject, "newReplacementHeardField")
            replacement_intended = main.findChild(QObject, "newReplacementIntendedField")
            self.assertIsNotNone(replacement_heard)
            self.assertIsNotNone(replacement_intended)
            app.vocabulary_mutation_succeeds = False
            replacement_heard.setProperty("text", "Speak her")
            replacement_intended.setProperty("text", "Speakr")
            self.assertTrue(QMetaObject.invokeMethod(vocabulary, "submitReplacement"))
            self.assertEqual(replacement_heard.property("text"), "Speak her")
            self.assertEqual(replacement_intended.property("text"), "Speakr")
            app.vocabulary_mutation_succeeds = True
            self.assertTrue(QMetaObject.invokeMethod(vocabulary, "submitReplacement"))
            self.assertEqual(replacement_heard.property("text"), "")
            self.assertEqual(replacement_intended.property("text"), "")

            practice = main.findChild(QObject, "practicePage")
            practice_word = main.findChild(QObject, "practiceWordField")
            self.assertIsNotNone(practice)
            self.assertIsNotNone(practice_word)
            app.vocabulary_mutation_succeeds = False
            practice_word.setProperty("text", "Keep This Too")
            self.assertTrue(QMetaObject.invokeMethod(practice, "submitWord"))
            self.assertEqual(practice_word.property("text"), "Keep This Too")
            app.vocabulary_mutation_succeeds = True
            self.assertTrue(QMetaObject.invokeMethod(practice, "submitWord"))
            self.assertEqual(practice_word.property("text"), "")

            practice_heard = main.findChild(QObject, "practiceReplacementHeardField")
            practice_intended = main.findChild(QObject, "practiceReplacementIntendedField")
            self.assertIsNotNone(practice_heard)
            self.assertIsNotNone(practice_intended)
            app.vocabulary_mutation_succeeds = False
            practice_heard.setProperty("text", "wrong")
            practice_intended.setProperty("text", "right")
            self.assertTrue(QMetaObject.invokeMethod(practice, "submitReplacement"))
            self.assertEqual(practice_heard.property("text"), "wrong")
            self.assertEqual(practice_intended.property("text"), "right")
            app.vocabulary_mutation_succeeds = True
            self.assertTrue(QMetaObject.invokeMethod(practice, "submitReplacement"))
            self.assertEqual(practice_heard.property("text"), "")
            self.assertEqual(practice_intended.property("text"), "")

            app.interface_state.update(capture="listening", capture_job_id=7)
            self.qapp.processEvents()
            self.qapp.processEvents()
            self.assertTrue(bool(hud.property("shouldShow")))
            self.assertEqual(hud.height(), 96)
            app.interface_state.update(
                capture="idle",
                pipeline="idle",
                pipeline_job_id=7,
                status_code="no_speech",
                latest_outcome_code="no_speech",
            )
            self.qapp.processEvents()
            self.assertTrue(bool(hud.property("shouldShow")))
            self.assertIn("catch speech", str(hud.property("appState").get("primary", "")))
            app.interface_state.update(status_code="ready")
            self.qapp.processEvents()
            self.assertFalse(bool(hud.property("shouldShow")))
            self.assertEqual(warnings, [])
        finally:
            dispose_qml_fixture(
                self.qapp,
                engine,
                context_objects=(bridge,),
            )
            self.assertEqual(warnings, [])

    def test_qml_teardown_destroys_roots_and_engine_before_bridge(self):
        app = _App()
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        qml = Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        engine.load(QUrl.fromLocalFile(str(qml / "Main.qml")))
        self.assertEqual(len(engine.rootObjects()), 1, warnings)
        root = engine.rootObjects()[0]
        destroyed = []
        root.destroyed.connect(lambda *_: destroyed.append("root"))
        engine.destroyed.connect(lambda *_: destroyed.append("engine"))
        bridge.destroyed.connect(lambda *_: destroyed.append("bridge"))

        dispose_qml_fixture(
            self.qapp,
            engine,
            context_objects=(bridge,),
        )

        self.assertEqual(destroyed, ["root", "engine", "bridge"])
        self.assertEqual(warnings, [])

    def test_all_qml_text_surfaces_are_plain_text_components(self):
        qml = Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        for path in qml.glob("*.qml"):
            if path.name in {"PlainText.qml", "PlainTextArea.qml"}:
                continue
            source = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\bText\s*\{", source), path.name)
            self.assertIsNone(re.search(r"\bTextArea\s*\{", source), path.name)

    def test_hostile_markup_in_plain_text_never_fetches_an_image(self):
        requested = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requested.set()
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        engine = QQmlApplicationEngine()
        qml = Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml / "PlainText.qml")))
        item = component.create()
        self.assertIsNotNone(item, [error.toString() for error in component.errors()])
        try:
            port = server.server_address[1]
            item.setProperty("text", f'<img src="http://127.0.0.1:{port}/probe.png">')
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline:
                self.qapp.processEvents()
                time.sleep(0.01)
            self.assertFalse(requested.is_set())
        finally:
            dispose_qml_fixture(
                self.qapp,
                engine,
                roots=(item,),
                components=(component,),
            )
            server.shutdown()
            server.server_close()

    @staticmethod
    def _luminance(color):
        values = (color.redF(), color.greenF(), color.blueF())
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in values
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    @classmethod
    def _contrast(cls, first, second):
        left, right = cls._luminance(first), cls._luminance(second)
        return (max(left, right) + 0.05) / (min(left, right) + 0.05)

    def test_light_and_dark_tokens_meet_contrast_contracts(self):
        engine = QQmlApplicationEngine()
        qml = Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml / "Theme.qml")))
        theme = component.create()
        self.assertIsNotNone(theme, [error.toString() for error in component.errors()])
        try:
            for mode in ("light", "dark"):
                theme.setProperty("mode", mode)
                self.qapp.processEvents()
                surface = theme.property("surface")
                self.assertGreaterEqual(
                    self._contrast(theme.property("text"), surface), 7.0, mode
                )
                self.assertGreaterEqual(
                    self._contrast(theme.property("mutedText"), surface), 4.5, mode
                )
                self.assertGreaterEqual(
                    self._contrast(theme.property("border"), surface), 3.0, mode
                )
                self.assertGreaterEqual(
                    self._contrast(
                        theme.property("accent"), theme.property("accentText")
                    ),
                    4.5,
                    mode,
                )
                for foreground, background in (
                    ("success", "successSurface"),
                    ("warning", "warningSurface"),
                    ("danger", "dangerSurface"),
                ):
                    self.assertGreaterEqual(
                        self._contrast(
                            theme.property(foreground), theme.property(background)
                        ),
                        4.5,
                        f"{mode}:{foreground}",
                    )
            theme.setProperty("reduceMotion", True)
            self.assertEqual(theme.property("motionFast"), 0)
            self.assertEqual(theme.property("motionStandard"), 0)
            self.assertEqual(theme.property("motionEmphasis"), 0)
        finally:
            dispose_qml_fixture(
                self.qapp,
                engine,
                roots=(theme,),
                components=(component,),
            )

    def test_narrow_200_percent_navigation_wraps_without_eliding_labels(self):
        app = _App(text_scale=200)
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        qml = Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        try:
            engine.load(QUrl.fromLocalFile(str(qml / "Main.qml")))
            self.assertEqual(len(engine.rootObjects()), 1)
            main = engine.rootObjects()[0]
            main.setWidth(640)
            main.setHeight(520)
            self.qapp.processEvents()
            self.assertEqual(main.property("topNavigationColumns"), 2)
            self.assertEqual(main.property("topNavigationRows"), 3)
        finally:
            dispose_qml_fixture(
                self.qapp,
                engine,
                context_objects=(bridge,),
            )
            self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
