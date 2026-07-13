from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPointF,
    Property,
    QUrl,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge
from tests.qml_lifecycle import qml_test_application


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
        self.setting_rejection = ""
        self.reset_rejection = ""
        self.setting_attempts = []
        self.reset_attempts = []

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
            "app_tones": {
                "Acme.exe": "formal",
                "Writer.exe": "literal",
            },
            "hotkey_exclude_apps": ["Game.exe"],
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

    def set_setting(self, path, value):
        self.setting_attempts.append((path, value))
        if self.setting_rejection == "busy":
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current dictation to finish before changing this setting.",
                "dismiss",
            )
            return False
        if self.setting_rejection == "save":
            self.interface_state.latch_issue(
                "setting_save_failed",
                "That setting could not be saved. Your previous file is unchanged.",
                "open_config",
            )
            return False
        if self.setting_rejection == "error":
            raise OSError("simulated settings write failure")
        return True

    def reset_settings_section(self, section):
        self.reset_attempts.append(section)
        if self.reset_rejection == "busy":
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current dictation to finish before resetting this section.",
                "dismiss",
            )
            return False
        if self.reset_rejection == "save":
            self.interface_state.latch_issue(
                "setting_save_failed",
                "Those defaults could not be saved. Your previous file is unchanged.",
                "open_config",
            )
            return False
        return True


class _NativeWindow(QObject):
    materialChanged = Signal()
    effectTierChanged = Signal()
    customChromeEnabledChanged = Signal()
    nativeMaterialAvailableChanged = Signal()
    systemReduceTransparencyChanged = Signal()
    softwareRendererChanged = Signal()
    maximizedChanged = Signal()
    activeChanged = Signal()

    @Property(str, notify=materialChanged)
    def material(self):
        return "mica"

    @Property(str, notify=effectTierChanged)
    def effectTier(self):
        return "full"

    @Property(bool, notify=customChromeEnabledChanged)
    def customChromeEnabled(self):
        return False

    @Property(bool, notify=nativeMaterialAvailableChanged)
    def nativeMaterialAvailable(self):
        return True

    @Property(bool, notify=systemReduceTransparencyChanged)
    def systemReduceTransparency(self):
        return False

    @Property(bool, notify=softwareRendererChanged)
    def softwareRenderer(self):
        return False

    @Property(bool, notify=maximizedChanged)
    def maximized(self):
        return False

    @Property(bool, notify=activeChanged)
    def active(self):
        return False

    @Slot(result=bool)
    def beginSystemMove(self):
        return False

    @Slot(object, result=bool)
    def beginSystemResize(self, _edge_mask):
        return False

    @Slot()
    def minimize(self):
        pass

    @Slot()
    def toggleMaximize(self):
        pass

    @Slot()
    def closeMain(self):
        pass

    @Slot(float, float, result=bool)
    def showSystemMenu(self, _x, _y):
        return False

    @Slot("QVariant", "QVariant", "QVariant", "QVariant", "QVariant")
    def setHitRegions(
        self,
        _titlebar,
        _minimize,
        _maximize,
        _close,
        _resize_border,
    ):
        pass

    @Slot(str, str)
    def applyVisualPreferences(self, _theme, _visual_effects):
        pass


class SettingsHelpQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = qml_test_application()
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

    def _process_queued_qml(self):
        for _ in range(4):
            self.qapp.processEvents()

    def _render_qml(self, main, cycles=1):
        for _ in range(cycles):
            main.requestUpdate()
            QTest.qWait(25)
            main.grabWindow()
            self.qapp.processEvents()

    def _dispose_main(self, bridge, engine, main, warnings):
        """Destroy QML roots while their context properties are still valid."""

        main.hide()
        main.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.qapp.processEvents()
        self.assertEqual(engine.rootObjects(), [])

        bridge.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.qapp.processEvents()
        self.assertEqual(warnings, [])

    @staticmethod
    def _has_ancestor(item, object_name):
        current = item
        while current is not None:
            if current.objectName() == object_name:
                return True
            current = current.parentItem()
        return False

    @classmethod
    def _find_visual_child(cls, item, object_name):
        for child in item.childItems():
            if child.objectName() == object_name:
                return child
            match = cls._find_visual_child(child, object_name)
            if match is not None:
                return match
        return None

    def _assert_item_inside_scroll_view(
        self,
        item,
        scroll,
        scale,
        target,
        *,
        expect_scrolled=True,
    ):
        viewport = scroll.property("contentItem")
        position = item.mapToItem(viewport, QPointF(0, 0))
        top = position.y()
        bottom = top + item.height()
        self.assertGreaterEqual(top, -1, (scale, target, top, bottom))
        self.assertLessEqual(
            bottom,
            viewport.height() + 1,
            (scale, target, top, bottom, viewport.height()),
        )
        if expect_scrolled:
            self.assertGreater(viewport.property("contentY"), 0, (scale, target))

    @staticmethod
    def _invoke_qml(target, method, *arguments):
        qml_arguments = [Q_ARG("QVariant", argument) for argument in arguments]
        return QMetaObject.invokeMethod(
            target,
            method,
            Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"),
            *qml_arguments,
        )

    def _exercise_focus_visibility(self):
        for scale in (100, 150, 200):
            with self.subTest(scale=scale):
                app, bridge, native, engine, main, warnings = self._load_main(scale)
                self.assertIsNotNone(app)
                self.assertIsNotNone(native)
                try:
                    main.setProperty("currentPage", "settings")
                    settings = main.findChild(QObject, "settingsPage")
                    search = main.findChild(QObject, "settingsSearchField")
                    settings_scroll = main.findChild(QObject, "settingsScroll")
                    self.assertIsNotNone(settings)
                    self.assertIsNotNone(search)
                    self.assertIsNotNone(settings_scroll)
                    settings.setProperty("selectedCategory", "Advanced")
                    self._render_qml(main, 3)
                    search.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                    self._render_qml(main)

                    focused = main.activeFocusItem()
                    for _ in range(48):
                        if self._has_ancestor(focused, "settingRow___raw_config"):
                            break
                        if self._has_ancestor(focused, "settingsPage"):
                            self._assert_item_inside_scroll_view(
                                focused,
                                settings_scroll,
                                scale,
                                "Settings Tab sequence",
                                expect_scrolled=False,
                            )
                        QTest.keyClick(main, Qt.Key.Key_Tab)
                        self._render_qml(main)
                        focused = main.activeFocusItem()
                    self.assertTrue(
                        self._has_ancestor(focused, "settingRow___raw_config"),
                        (scale, focused.objectName() if focused is not None else None),
                    )
                    self._assert_item_inside_scroll_view(
                        focused,
                        settings_scroll,
                        scale,
                        "Settings raw configuration",
                    )

                    main.setProperty("currentPage", "help")
                    self._render_qml(main, 3)
                    help_page = main.findChild(QObject, "helpPage")
                    help_scroll = main.findChild(QObject, "helpScroll")
                    self.assertIsNotNone(help_page)
                    self.assertIsNotNone(help_scroll)
                    QMetaObject.invokeMethod(
                        help_page,
                        "requestReset",
                        Qt.ConnectionType.DirectConnection,
                        Q_ARG("QVariant", "privacy"),
                    )
                    self._render_qml(main, 6)
                    focused = main.activeFocusItem()
                    self.assertEqual(focused.objectName(), "resetCancelButton")
                    self._assert_item_inside_scroll_view(
                        focused,
                        help_scroll,
                        scale,
                        "Help reset Cancel",
                    )
                    self.assertEqual(warnings, [])
                finally:
                    self._dispose_main(bridge, engine, main, warnings)

    def test_focus_targets_remain_visible_at_supported_text_scales(self):
        self._exercise_focus_visibility()

    def test_windows_qpa_keeps_keyboard_and_reset_focus_visible(self):
        child_flag = "SPEAKR_WINDOWS_FOCUS_TEST_CHILD"
        if os.environ.get(child_flag) == "1":
            self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), "windows")
            self.assertEqual(self.qapp.platformName(), "windows")
            self._exercise_focus_visibility()
            return
        if sys.platform != "win32":
            self.skipTest("Windows QPA verification runs on Windows")
        environment = os.environ.copy()
        environment[child_flag] = "1"
        environment["QT_QPA_PLATFORM"] = "windows"
        environment["QT_QUICK_BACKEND"] = "software"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                (
                    "tests.test_settings_help_qml.SettingsHelpQmlTests."
                    "test_windows_qpa_keeps_keyboard_and_reset_focus_visible"
                ),
                "-v",
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            "\n".join((completed.stdout, completed.stderr)),
        )

    def test_settings_load_render_and_teardown_emit_no_qml_warnings(self):
        app, bridge, native, engine, main, warnings = self._load_main(200)
        self.assertIsNotNone(app)
        self.assertIsNotNone(native)
        try:
            main.setProperty("currentPage", "settings")
            settings = main.findChild(QObject, "settingsPage")
            search = main.findChild(QObject, "settingsSearchField")
            rows_host = main.findChild(QObject, "settingsRowsRepeater")
            self.assertIsNotNone(settings)
            self.assertIsNotNone(search)
            self.assertIsNotNone(rows_host)

            for category, query in (
                ("All", ""),
                ("Accessibility", "visual effects"),
                ("Advanced", "Ollama"),
                ("Privacy", "no matching setting"),
            ):
                settings.setProperty("selectedCategory", category)
                search.setProperty("text", query)
                self._render_qml(main, 2)
        finally:
            self._dispose_main(bridge, engine, main, warnings)

        warning_text = "\n".join(warnings)
        self.assertNotIn("Binding loop detected", warning_text)
        self.assertNotIn("capturingHotkey", warning_text)

    def test_windows_combo_shows_forced_press_mode_without_rewriting_hold(self):
        app, bridge, native, engine, main, warnings = self._load_main(100)
        self.assertIsNotNone(native)
        try:
            forced_settings = app.settings_snapshot()
            forced_settings.update(
                {
                    "platform": "windows",
                    "hotkey": "ctrl+space",
                    "toggle_mode": False,
                    "effective_toggle_mode": True,
                    "toggle_mode_forced": True,
                }
            )
            bridge._accept_settings(forced_settings)
            main.setProperty("currentPage", "settings")
            self._process_queued_qml()
            self._render_qml(main, 3)

            rows_host = main.findChild(QObject, "settingsRowsRepeater")
            self.assertIsNotNone(rows_host)
            row = self._find_visual_child(rows_host, "settingRow_toggle_mode")
            self.assertIsNotNone(row)
            self.assertTrue(bool(row.property("currentValue")))
            self.assertFalse(row.property("controlEnabled"))
            self.assertIn(
                "always use Press to start and stop",
                row.property("description"),
            )

            behavior_control = next(
                (
                    child
                    for child in row.findChildren(QObject)
                    if child.property("accessibleName") == "Shortcut behavior"
                    and child.property("currentIndex") is not None
                    and bool(child.property("visible"))
                ),
                None,
            )
            self.assertIsNotNone(behavior_control)
            self.assertFalse(behavior_control.property("enabled"))
            self.assertEqual(behavior_control.property("currentIndex"), 1)
            self.assertEqual(
                behavior_control.property("displayText"),
                "Press to start and stop",
            )
            self.assertFalse(forced_settings["toggle_mode"])
            self.assertEqual(app.setting_attempts, [])
        finally:
            self._dispose_main(bridge, engine, main, warnings)

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
            self._dispose_main(bridge, engine, main, warnings)

    def test_advanced_contains_and_searches_every_expert_setting_once(self):
        app, bridge, native, engine, main, warnings = self._load_main(100)
        self.assertIsNotNone(app)
        self.assertIsNotNone(native)
        try:
            main.setProperty("currentPage", "settings")
            self.qapp.processEvents()
            settings = main.findChild(QObject, "settingsPage")
            search = main.findChild(QObject, "settingsSearchField")
            summary = main.findChild(QObject, "settingsResultSummary")
            self.assertIsNotNone(settings)
            self.assertIsNotNone(search)
            self.assertIsNotNone(summary)

            rows_value = settings.property("rows")
            rows = rows_value.toVariant() if hasattr(rows_value, "toVariant") else rows_value
            settings.setProperty("selectedCategory", "All")
            search.setProperty("text", "")
            self.qapp.processEvents()
            self.assertEqual(settings.property("visibleResultCount"), len(rows))

            required_paths = {
                "sample_rate",
                "model",
                "beam_size",
                "vad_threshold",
                "formatting.use_ollama",
                "formatting.autostart_ollama",
                "formatting.ollama_model",
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
            }
            advanced_rows = [
                row
                for row in rows
                if row.get("category") == "Advanced" or row.get("advanced") is True
            ]
            self.assertTrue(required_paths.issubset({row.get("path") for row in advanced_rows}))
            tone_row = next(
                row for row in advanced_rows if row.get("label") == "Tone for Acme.exe"
            )
            exclusion_row = next(
                row
                for row in advanced_rows
                if row.get("label") == "Shortcut exclusion for Game.exe"
            )
            self.assertIn("formal", tone_row.get("description"))
            self.assertIn("Acme.exe", tone_row.get("description"))
            self.assertIn("Game.exe", exclusion_row.get("description"))
            self.assertEqual(tone_row.get("type"), "readonly")
            self.assertEqual(exclusion_row.get("type"), "readonly")

            settings.setProperty("selectedCategory", "Advanced")
            queries = (
                "Microphone sample rate",
                "Speech model",
                "Beam size",
                "VAD",
                "Use local Ollama when available",
                "Start local Ollama automatically",
                "Local Ollama model",
                "Processing device",
                "Compute type",
                "Streaming transcription",
                "Streaming chunk length",
                "Minimum dictation length",
                "Maximum dictation length",
                "Text insertion",
                "Local Ollama address",
                "Ollama timeout",
                "Ollama keep-alive",
                "Acme.exe",
                "formal",
                "Writer.exe",
                "literal",
                "Game.exe",
            )
            for query in queries:
                with self.subTest(query=query):
                    search.setProperty("text", query)
                    self.qapp.processEvents()
                    self.assertGreater(settings.property("visibleResultCount"), 0)
                    self.assertIn("Advanced", summary.property("text"))

            search.setProperty("text", "Acme.exe")
            self._render_qml(main, 2)
            rows_list = main.findChild(QObject, "settingsRowsRepeater")
            tone_delegate = self._find_visual_child(
                rows_list,
                "settingRow___app_tone_0",
            )
            self.assertIsNotNone(tone_delegate)
            self.assertTrue(tone_delegate.property("visible"))
            self.assertIn("formal", tone_delegate.property("description"))
            search.setProperty("text", "Game.exe")
            self._render_qml(main, 2)
            exclusion_delegate = self._find_visual_child(
                rows_list,
                "settingRow___excluded_app_0",
            )
            self.assertIsNotNone(exclusion_delegate)
            self.assertTrue(exclusion_delegate.property("visible"))
            self.assertIn("Game.exe", exclusion_delegate.property("description"))

            settings.setProperty("selectedCategory", "All")
            for query in ("Speech model", "Acme.exe", "formal", "Game.exe"):
                with self.subTest(unique_query=query):
                    search.setProperty("text", query)
                    self.qapp.processEvents()
                    self.assertEqual(settings.property("visibleResultCount"), 1)
            self.assertEqual(warnings, [])
        finally:
            self._dispose_main(bridge, engine, main, warnings)

    def test_rejected_setting_uses_busy_explanation_and_generic_save_error(self):
        app, bridge, native, engine, main, warnings = self._load_main(100)
        self.assertIsNotNone(native)
        try:
            main.setProperty("currentPage", "settings")
            self.qapp.processEvents()
            settings = main.findChild(QObject, "settingsPage")
            self.assertIsNotNone(settings)

            app.setting_rejection = "busy"
            result = self._invoke_qml(settings, "commitChange", "toggle_mode", True, False)
            self.assertFalse(result)
            self._process_queued_qml()
            self.assertEqual(app.setting_attempts[-1], ("toggle_mode", True))
            self.assertEqual(
                settings.property("saveError"),
                "Wait for the current dictation to finish before changing this setting.",
            )

            first_busy_version = app.interface_state.snapshot()["version"]
            result = self._invoke_qml(settings, "commitChange", "toggle_mode", True, False)
            self.assertFalse(result)
            self._process_queued_qml()
            self.assertGreater(app.interface_state.snapshot()["version"], first_busy_version)
            self.assertEqual(app.setting_attempts[-1], ("toggle_mode", True))
            self.assertEqual(
                settings.property("saveError"),
                "Wait for the current dictation to finish before changing this setting.",
            )

            app.setting_rejection = "save"
            result = self._invoke_qml(
                settings,
                "commitChange",
                "formatting.enabled",
                False,
                True,
            )
            self.assertFalse(result)
            self._process_queued_qml()
            self.assertEqual(app.setting_attempts[-1], ("formatting.enabled", False))
            self.assertEqual(
                settings.property("saveError"),
                "That setting could not be saved. The previous value is still active.",
            )

            app.setting_rejection = "error"
            with self.assertLogs("speakr.qt_ui", level="ERROR"):
                result = self._invoke_qml(
                    settings,
                    "commitChange",
                    "formatting.enabled",
                    True,
                    False,
                )
            self.assertFalse(result)
            self._process_queued_qml()
            self.assertEqual(
                settings.property("saveError"),
                "That setting could not be saved. The previous value is still active.",
            )
            self.assertEqual(warnings, [])
        finally:
            self._dispose_main(bridge, engine, main, warnings)

    def test_rejected_reset_preserves_confirmation_and_shows_busy_reason(self):
        app, bridge, native, engine, main, warnings = self._load_main(100)
        self.assertIsNotNone(native)
        try:
            main.setProperty("currentPage", "help")
            self.qapp.processEvents()
            help_page = main.findChild(QObject, "helpPage")
            confirmation = main.findChild(QObject, "resetConfirmation")
            self.assertIsNotNone(help_page)
            self.assertIsNotNone(confirmation)

            app.reset_rejection = "busy"
            help_page.setProperty("pendingResetSection", "privacy")
            result = self._invoke_qml(help_page, "confirmReset")
            self.assertFalse(result)
            self._process_queued_qml()
            busy_message = (
                "Wait for the current dictation to finish before resetting this section."
            )
            self.assertEqual(app.reset_attempts[-1], "privacy")
            self.assertEqual(help_page.property("pendingResetSection"), "privacy")
            self.assertEqual(help_page.property("resetError"), busy_message)
            self.assertEqual(confirmation.property("detail"), busy_message)
            self.assertTrue(confirmation.property("visible"))

            first_busy_version = app.interface_state.snapshot()["version"]
            result = self._invoke_qml(help_page, "confirmReset")
            self.assertFalse(result)
            self._process_queued_qml()
            self.assertGreater(app.interface_state.snapshot()["version"], first_busy_version)
            self.assertEqual(app.reset_attempts[-1], "privacy")
            self.assertEqual(help_page.property("pendingResetSection"), "privacy")
            self.assertEqual(help_page.property("resetError"), busy_message)
            self.assertEqual(confirmation.property("detail"), busy_message)

            app.reset_rejection = "save"
            result = self._invoke_qml(help_page, "confirmReset")
            self.assertFalse(result)
            self._process_queued_qml()
            generic_message = (
                "Those defaults could not be restored. Your current settings are unchanged."
            )
            self.assertEqual(help_page.property("pendingResetSection"), "privacy")
            self.assertEqual(help_page.property("resetError"), generic_message)
            self.assertEqual(confirmation.property("detail"), generic_message)

            app.reset_rejection = ""
            result = self._invoke_qml(help_page, "confirmReset")
            self.assertTrue(result)
            self._process_queued_qml()
            self.assertEqual(help_page.property("pendingResetSection"), "")
            self.assertEqual(help_page.property("resetError"), "")
            self.assertEqual(warnings, [])
        finally:
            self._dispose_main(bridge, engine, main, warnings)

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
                    self._dispose_main(bridge, engine, main, warnings)

    def test_help_reset_actions_are_guarded(self):
        source = (self.qml / "HelpPage.qml").read_text(encoding="utf-8")
        self.assertIn('onClicked: root.requestReset("interface")', source)
        self.assertIn('onClicked: root.requestReset("privacy")', source)
        self.assertIn("onClicked: root.confirmReset()", source)
        self.assertIn("onClicked: root.cancelReset()", source)
        self.assertIn("detail: root.resetError", source)
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
            "sample_rate",
            "model",
            "beam_size",
            "vad_threshold",
            "formatting.use_ollama",
            "formatting.autostart_ollama",
            "formatting.ollama_model",
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
        self.assertNotIn("Exact per-app values", settings)
        self.assertNotRegex(combined, r"\bText\s*\{")
        self.assertNotRegex(combined, r"\bTextArea\s*\{")


if __name__ == "__main__":
    unittest.main()
