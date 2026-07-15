from __future__ import annotations

import os
import re
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import (
    QObject,
    QPointF,
    Property,
    QMetaObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAccessible, QColor
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.qml_lifecycle import dispose_qml_fixture, qml_test_application


class _Bridge(QObject):
    capturingHotkeyChanged = Signal()

    def __init__(self):
        super().__init__()
        self._capturing_hotkey = False
        self.calls: list[tuple[str, object]] = []

    @Property(bool, notify=capturingHotkeyChanged)
    def capturingHotkey(self):
        return self._capturing_hotkey

    def set_capturing_hotkey(self, value):
        if self._capturing_hotkey == value:
            return
        self._capturing_hotkey = value
        self.capturingHotkeyChanged.emit()

    def _called(self, name, value=None):
        self.calls.append((name, value))
        return True

    @Slot(result=bool)
    def startPractice(self):
        return self._called("startPractice")

    @Slot(result=bool)
    def stopPractice(self):
        return self._called("stopPractice")

    @Slot(result=bool)
    def clearPractice(self):
        return self._called("clearPractice")

    @Slot(result=bool)
    def retrySetup(self):
        return self._called("retrySetup")

    @Slot(result=bool)
    def openSystemSettings(self):
        return self._called("openSystemSettings")

    @Slot(str, result=bool)
    def openLocal(self, target):
        return self._called("openLocal", target)

    @Slot(result=bool)
    def reloadLocalState(self):
        return self._called("reloadLocalState")

    @Slot(result=bool)
    def dismissIssue(self):
        return self._called("dismissIssue")

    @Slot(result=bool)
    def beginHotkeyCapture(self):
        self.set_capturing_hotkey(True)
        return self._called("beginHotkeyCapture")

    @Slot(result=bool)
    def cancelHotkeyCapture(self):
        self.set_capturing_hotkey(False)
        return self._called("cancelHotkeyCapture")

    @Slot(result=bool)
    def confirmHotkey(self):
        self.set_capturing_hotkey(False)
        return self._called("confirmHotkey")

    @Slot(str, "QVariant", result=bool)
    def setSetting(self, path, value):
        return self._called("setSetting", (path, value))

    @Slot(result=bool)
    def completeOnboarding(self):
        return self._called("completeOnboarding")

    @Slot(str, result=bool)
    def addWord(self, word):
        return self._called("addWord", word)

    @Slot(str, str, result=bool)
    def addReplacement(self, heard, intended):
        return self._called("addReplacement", (heard, intended))


class SetupPracticeQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = qml_test_application()
        cls.qml = (
            Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        )

    def _component(self, engine, name):
        return QQmlComponent(engine, QUrl.fromLocalFile(str(self.qml / name)))

    def _fixture(self, page_name, *, text_scale=1.0, mode="dark"):
        engine = QQmlApplicationEngine()
        bridge = _Bridge()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )

        theme_component = self._component(engine, "Theme.qml")
        theme = theme_component.create()
        self.assertIsNotNone(
            theme, [error.toString() for error in theme_component.errors()]
        )
        theme.setParent(engine)
        theme.setProperty("mode", mode)
        theme.setProperty("textScale", text_scale)

        page_component = self._component(engine, page_name)
        page = page_component.createWithInitialProperties({"tokens": theme})
        self.assertIsNotNone(
            page, [error.toString() for error in page_component.errors()]
        )

        window = QQuickWindow()
        window.setWidth(640)
        window.setHeight(520)
        QQmlEngine.setObjectOwnership(page, QQmlEngine.CppOwnership)
        page.setParent(window.contentItem())
        page.setParentItem(window.contentItem())
        page.setWidth(640)
        page.setHeight(520)
        window.show()
        for _ in range(4):
            self.qapp.processEvents()
            page.ensurePolished()
        return engine, bridge, theme, page, window, warnings

    def _dispose(self, engine, bridge, theme, page, window, warnings):
        dispose_qml_fixture(
            self.qapp,
            engine,
            roots=(page, theme),
            windows=(window,),
            context_objects=(bridge,),
        )
        self.assertEqual(warnings, [])

    def _settle(self, page):
        for _ in range(4):
            self.qapp.processEvents()
            page.ensurePolished()

    def _wait_until(self, page, predicate, timeout_ms=4000):
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            if predicate():
                return True
            QTest.qWait(25)
            page.ensurePolished()
        return bool(predicate())

    @staticmethod
    def _find_by_property(root, name, expected):
        for item in [root, *root.findChildren(QObject)]:
            if item.property(name) == expected:
                return item
        return None

    @staticmethod
    def _accessible_description(item):
        accessible = QAccessible.queryAccessibleInterface(item)
        if accessible is None:
            return ""
        return accessible.text(QAccessible.Text.Description)

    @staticmethod
    def _accessible_name(item):
        accessible = QAccessible.queryAccessibleInterface(item)
        if accessible is None:
            return ""
        return accessible.text(QAccessible.Text.Name)

    @staticmethod
    def _accessible_descendants(interface):
        result = []
        for index in range(interface.childCount()):
            child = interface.child(index)
            result.append(child)
            result.extend(SetupPracticeQmlTests._accessible_descendants(child))
        return result

    @staticmethod
    def _find_by_property(root, name, expected):
        for item in [root, *root.findChildren(QObject)]:
            if item.property(name) == expected:
                return item
        return None

    @staticmethod
    def _accessible_description(item):
        accessible = QAccessible.queryAccessibleInterface(item)
        if accessible is None:
            return ""
        return accessible.text(QAccessible.Text.Description)

    @staticmethod
    def _accessible_name(item):
        accessible = QAccessible.queryAccessibleInterface(item)
        if accessible is None:
            return ""
        return accessible.text(QAccessible.Text.Name)

    @staticmethod
    def _accessible_descendants(interface):
        result = []
        for index in range(interface.childCount()):
            child = interface.child(index)
            result.append(child)
            result.extend(SetupPracticeQmlTests._accessible_descendants(child))
        return result

    @staticmethod
    def _visual_items(item):
        result = []
        pending = list(item.childItems())
        while pending:
            child = pending.pop()
            result.append(child)
            pending.extend(child.childItems())
        return result

    def test_divergent_system_palette_meters_use_filled_and_hollow_text_shapes(self):
        divergent = {
            "window": "#000000",
            "windowText": "#FFFFFF",
            "base": "#FFFFFF",
            "text": "#000000",
            "button": "#000000",
            "buttonText": "#FFFFFF",
            "highlight": "#FFD400",
            "highlightedText": "#000000",
        }
        for page_name, segment_name in (
            ("OnboardingPage.qml", "onboardingPracticeMeterSegment"),
            ("PracticePage.qml", "practiceMeterSegment"),
        ):
            for scale in (1.0, 2.0):
                with self.subTest(page=page_name, scale=scale):
                    engine, bridge, theme, page, window, warnings = self._fixture(
                        page_name, text_scale=scale
                    )
                    try:
                        theme.setProperty("reduceMotion", True)
                        theme.setProperty("systemPaletteOverride", divergent)
                        theme.setProperty("systemHighContrast", True)
                        window.setWidth(960)
                        window.setHeight(1600)
                        page.setWidth(960)
                        page.setHeight(1600)
                        if page_name == "OnboardingPage.qml":
                            page.setProperty("currentStep", 4)
                        page.setProperty(
                            "practice",
                            {"active": True, "mic_level_band": "good"},
                        )
                        self._settle(page)

                        segments = sorted(
                            (
                                item
                                for item in self._visual_items(page)
                                if item.objectName() == segment_name
                            ),
                            key=lambda item: int(item.property("index")),
                        )
                        self.assertEqual(len(segments), 5)
                        self.assertEqual(
                            [bool(item.property("filled")) for item in segments],
                            [True, True, True, True, False],
                        )
                        for segment in segments:
                            expected_fill = theme.property(
                                "text" if segment.property("filled") else "surface"
                            )
                            self.assertEqual(
                                QColor(segment.property("color")),
                                QColor(expected_fill),
                            )
                            self.assertEqual(
                                QColor(segment.property("edgeColor")),
                                QColor(theme.property("text")),
                            )

                        image = window.grabWindow()
                        self.assertFalse(image.isNull())
                        ratio = image.devicePixelRatio()
                        for segment in segments:
                            center = segment.mapToScene(
                                QPointF(segment.width() / 2, segment.height() / 2)
                            )
                            self.assertGreaterEqual(center.x(), 0)
                            self.assertGreaterEqual(center.y(), 0)
                            self.assertLess(center.x(), window.width())
                            self.assertLess(center.y(), window.height())
                            rendered = image.pixelColor(
                                round(center.x() * ratio),
                                round(center.y() * ratio),
                            )
                            expected = theme.property(
                                "text" if segment.property("filled") else "surface"
                            )
                            self.assertEqual(QColor(rendered), QColor(expected))
                    finally:
                        self._dispose(
                            engine, bridge, theme, page, window, warnings
                        )

    def test_onboarding_covers_all_steps_and_recovery_states(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            heading = page.findChild(QObject, "onboardingStepHeading")
            permission = page.findChild(QObject, "onboardingPermissionNotice")
            model = page.findChild(QObject, "onboardingModelNotice")
            capture = page.findChild(QObject, "onboardingHotkeyCaptureNotice")
            skip = page.findChild(QObject, "skipPracticeButton")
            self.assertIsNotNone(heading)
            self.assertIsNotNone(permission)
            self.assertIsNotNone(model)
            self.assertIsNotNone(capture)
            self.assertIsNotNone(skip)

            expected = ["Privacy", "Permissions", "Speech model", "Shortcut", "Practice"]
            for index, title in enumerate(expected):
                page.setProperty("currentStep", index)
                self._settle(page)
                self.assertEqual(heading.property("title"), title)

            page.setProperty("currentStep", 1)
            page.setProperty(
                "appState",
                {
                    "availability": "needs_attention",
                    "last_issue": {
                        "code": "permission_missing",
                        "message": "Microphone access is needed.",
                        "action": "open_system_settings",
                    },
                },
            )
            self._settle(page)
            self.assertTrue(permission.property("visible"))
            self.assertEqual(permission.property("kind"), "danger")
            self.assertEqual(permission.property("actionText"), "Open system settings")

            page.setProperty("currentStep", 2)
            page.setProperty("appState", {"availability": "ready", "pipeline": "waiting_model"})
            self._settle(page)
            self.assertTrue(model.property("visible"))
            self.assertEqual(model.property("kind"), "info")

            page.setProperty(
                "appState",
                {
                    "availability": "needs_attention",
                    "pipeline": "idle",
                    "last_issue": {
                        "code": "model_load_failed",
                        "message": "The speech model could not be prepared.",
                        "action": "retry_model",
                    },
                },
            )
            self._settle(page)
            self.assertEqual(model.property("kind"), "danger")
            self.assertEqual(model.property("actionText"), "Retry")

            page.setProperty("currentStep", 3)
            page.setProperty(
                "appState",
                {"hotkey": "right ctrl", "pending_hotkey": "right ctrl"},
            )
            bridge.set_capturing_hotkey(True)
            self._settle(page)
            self.assertEqual(capture.property("title"), "Press one key")
            self.assertIn("Captured", capture.property("message"))

            page.setProperty("currentStep", 4)
            page.setProperty("practice", {"active": True, "mic_level_band": "good"})
            self._settle(page)
            self.assertTrue(skip.property("visible"))
            segments = page.findChild(QObject, "onboardingPracticeMeterSegments")
            self.assertIsNotNone(segments)
            self.assertEqual(segments.property("count"), 5)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)

    def test_shortcut_capture_is_one_key_untimed_and_cancelable(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            page.setProperty("currentStep", 3)
            page.setProperty(
                "appState", {"hotkey": "right ctrl", "pending_hotkey": ""}
            )
            self._settle(page)

            capture = page.findChild(QObject, "onboardingHotkeyCaptureNotice")
            capture_button = page.findChild(QObject, "onboardingCaptureButton")
            self.assertIsNotNone(capture)
            self.assertIsNotNone(capture_button)
            self.assertEqual(capture_button.property("text"), "Change shortcut")

            self.assertTrue(QMetaObject.invokeMethod(capture_button, "click"))
            self._settle(page)
            self.assertTrue(bridge.capturingHotkey)
            self.assertEqual(capture.property("title"), "Press one key")
            self.assertEqual(capture.property("message"), "Press one key.")
            self.assertIn("There is no time limit", capture.property("detail"))
            self.assertIn("Cancel", capture.property("detail"))
            self.assertIn("Escape", capture.property("detail"))
            self.assertEqual(capture_button.property("text"), "Cancel")
            self.assertEqual(
                capture_button.property("accessibleDescription"),
                "Cancel shortcut capture",
            )

            capture_status = self._find_by_property(
                page, "label", "Waiting for a shortcut"
            )
            self.assertIsNotNone(capture_status)
            self.assertEqual(
                capture_status.property("description"), "Capture never times out"
            )

            capture_button.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            QTest.keyClick(window, Qt.Key.Key_Escape)
            self._settle(page)
            self.assertFalse(bridge.capturingHotkey)
            self.assertIn(("cancelHotkeyCapture", None), bridge.calls)

            bridge.calls.clear()
            self.assertTrue(QMetaObject.invokeMethod(capture_button, "click"))
            self._settle(page)
            self.assertTrue(QMetaObject.invokeMethod(capture_button, "click"))
            self._settle(page)
            self.assertFalse(bridge.capturingHotkey)
            self.assertEqual(bridge.calls[-1], ("cancelHotkeyCapture", None))
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)

    def test_windows_combo_forces_press_without_changing_raw_hold_preference(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            settings = {
                "platform": "windows",
                "hotkey": "ctrl+space",
                "toggle_mode": False,
                "effective_toggle_mode": True,
                "toggle_mode_forced": True,
            }
            page.setProperty("settings", settings)
            page.setProperty("currentStep", 3)
            self._settle(page)

            behavior = self._find_by_property(
                page, "accessibleName", "Shortcut behavior"
            )
            continue_button = page.findChild(QObject, "onboardingContinueButton")
            self.assertIsNotNone(behavior)
            self.assertIsNotNone(continue_button)
            self.assertFalse(behavior.property("enabled"))
            self.assertEqual(behavior.property("currentIndex"), 1)
            self.assertEqual(behavior.property("displayText"), "Press to start and stop")
            self.assertFalse(page.property("selectedToggleMode"))
            self.assertIn(
                "always uses Press to start and stop",
                behavior.property("accessibleDescription"),
            )

            self.assertTrue(QMetaObject.invokeMethod(continue_button, "click"))
            self._settle(page)
            self.assertEqual(page.property("currentStep"), 4)
            self.assertFalse(settings["toggle_mode"])
            self.assertFalse(page.property("selectedToggleMode"))
            self.assertNotIn(
                ("setSetting", ("toggle_mode", False)), bridge.calls
            )
            self.assertFalse(
                any(
                    name == "setSetting" and value[0] == "toggle_mode"
                    for name, value in bridge.calls
                )
            )
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)

    def test_onboarding_step_accessibility_describes_completed_current_and_upcoming(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            page.setProperty("currentStep", 2)
            self._settle(page)
            visual_items = self._visual_items(page)
            buttons = [
                next(
                    (
                        item
                        for item in visual_items
                        if item.objectName() == f"onboardingStepButton{index}"
                    ),
                    None,
                )
                for index in range(5)
            ]
            self.assertTrue(all(button is not None for button in buttons))

            expected = (
                "Completed setup step 1 of 5. Activate to return.",
                "Completed setup step 2 of 5. Activate to return.",
                "Current setup step 3 of 5.",
                "Upcoming setup step 4 of 5. Complete the current step first.",
                "Upcoming setup step 5 of 5. Complete the current step first.",
            )
            self.assertEqual(
                [self._accessible_description(button) for button in buttons],
                list(expected),
            )
            self.assertEqual(
                [bool(button.property("enabled")) for button in buttons],
                [True, True, True, False, False],
            )
            self.assertNotIn("return", expected[3].casefold())
            self.assertNotIn("return", expected[4].casefold())
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)
    def test_required_onboarding_copy_stays_plain_and_local(self):
        source = (self.qml / "OnboardingPage.qml").read_text(encoding="utf-8")

        self.assertIn("Your voice and dictated text stay on this computer.", source)
        self.assertIn(
            "When Speakr is ready, it may keep a brief moment of microphone audio in memory",
            source,
        )
        self.assertIn("That audio is continuously replaced", source)
        self.assertIn("is not saved by Speakr", source)
        self.assertIn(
            "The first time you use Speakr, it may download a speech model.",
            source,
        )
        self.assertIn("After that, dictation works locally.", source)
        for jargon in (
            "telemetry",
            "analytics",
            "non-loopback",
            "127.0.0.1",
            "ollama",
            "diagnostics",
            "falls back to cpu",
        ):
            self.assertNotIn(jargon, source.casefold())

    def test_onboarding_practice_action_meter_and_finish_state_table(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            page.setProperty("currentStep", 4)
            start = page.findChild(QObject, "onboardingPracticeStartButton")
            clear = page.findChild(QObject, "onboardingPracticeClearButton")
            continue_button = page.findChild(QObject, "onboardingContinueButton")
            skip = page.findChild(QObject, "skipPracticeButton")
            meter = page.findChild(QObject, "onboardingPracticeMeter")
            self.assertTrue(
                all(
                    item is not None
                    for item in (start, clear, continue_button, skip, meter)
                )
            )

            def primary_count():
                return sum(
                    bool(button.property("visible"))
                    and bool(button.property("enabled"))
                    and button.property("kind") == "primary"
                    for button in (start, clear, continue_button, skip)
                )

            cases = (
                (
                    "initial",
                    {"mic_level_band": "high"},
                    ("Start Practice", True, "primary"),
                    (False, "Finish setup"),
                    (True, True, "Skip Practice and finish setup"),
                    False,
                    "Starts when you choose Start Practice",
                    1,
                ),
                (
                    "active",
                    {"active": True, "mic_level_band": "silent"},
                    ("Stop Practice", True, "primary"),
                    (False, "Finish setup"),
                    (True, False, "Skip Practice and finish setup"),
                    False,
                    "Waiting for sound",
                    1,
                ),
                (
                    "busy",
                    {"processing": True, "mic_level_band": "high"},
                    ("Processing…", False, "secondary"),
                    (False, "Finish setup"),
                    (True, False, "Skip Practice and finish setup"),
                    False,
                    "Processing locally",
                    0,
                ),
                (
                    "outcome",
                    {"text": "Hello Speakr", "mic_level_band": "high"},
                    ("Try again", True, "secondary"),
                    (True, "Finish setup"),
                    (False, None, "Skip Practice and finish setup"),
                    True,
                    "Starts when you choose Try again",
                    1,
                ),
            )
            for (
                name,
                practice,
                start_state,
                continue_state,
                skip_state,
                clear_enabled,
                meter_label,
                expected_primaries,
            ) in cases:
                with self.subTest(state=name):
                    page.setProperty("practice", practice)
                    self._settle(page)
                    if name == "outcome":
                        # Result contract: the action row holds its
                        # processing presentation for the 1.2 s reading
                        # window before Try again + Finish appear.
                        self.assertEqual(start.property("text"), "Processing…")
                        self.assertFalse(start.property("enabled"))
                        self.assertFalse(continue_button.property("visible"))
                        self.assertTrue(skip.property("visible"))
                        self.assertFalse(skip.property("enabled"))
                        self.assertFalse(clear.property("enabled"))
                        self.assertEqual(primary_count(), 0)
                        self.assertTrue(
                            bool(page.property("practiceResultPending"))
                        )
                        self.assertTrue(
                            self._wait_until(
                                page,
                                lambda: bool(
                                    page.property("practiceResultActionsReady")
                                ),
                            )
                        )
                        self._settle(page)
                    self.assertTrue(start.property("visible"))
                    self.assertEqual(start.property("text"), start_state[0])
                    self.assertEqual(bool(start.property("enabled")), start_state[1])
                    self.assertEqual(start.property("kind"), start_state[2])
                    if name == "busy":
                        self.assertEqual(
                            start.property("accessibleDescription"),
                            "Temporary practice is processing locally",
                        )
                        busy_status = self._find_by_property(
                            page, "label", "Transcribing locally"
                        )
                        self.assertIsNotNone(busy_status)
                        self.assertEqual(busy_status.property("symbol"), "\u2022")
                    self.assertEqual(
                        bool(continue_button.property("visible")), continue_state[0]
                    )
                    self.assertEqual(continue_button.property("text"), continue_state[1])
                    self.assertEqual(bool(skip.property("visible")), skip_state[0])
                    if skip_state[0]:
                        self.assertEqual(
                            bool(skip.property("enabled")), skip_state[1]
                        )
                    self.assertEqual(skip.property("text"), skip_state[2])
                    self.assertEqual(bool(clear.property("enabled")), clear_enabled)
                    self.assertEqual(bool(meter.property("visible")), name == "active")
                    if name == "active":
                        self.assertIn(meter_label, self._accessible_name(meter))
                    accessible_window = QAccessible.queryAccessibleInterface(window)
                    progress_bars = [
                        interface
                        for interface in self._accessible_descendants(
                            accessible_window
                        )
                        if interface.role() == QAccessible.Role.ProgressBar
                        and "Microphone input level"
                        in interface.text(QAccessible.Text.Name)
                    ]
                    self.assertEqual(len(progress_bars), 1 if name == "active" else 0)
                    self.assertEqual(primary_count(), expected_primaries)

            for band, expected_count, expected_label in (
                ("silent", 0, "Waiting for sound"),
                ("low", 2, "Low"),
                ("good", 4, "Good"),
                ("high", 5, "High"),
            ):
                with self.subTest(active_level=band):
                    page.setProperty(
                        "practice", {"active": True, "mic_level_band": band}
                    )
                    self._settle(page)
                    self.assertTrue(meter.property("visible"))
                    segments = [
                        item
                        for item in self._visual_items(page)
                        if item.objectName()
                        == "onboardingPracticeMeterSegment"
                    ]
                    self.assertEqual(
                        sum(bool(segment.property("filled")) for segment in segments),
                        expected_count,
                    )
                    self.assertIn(expected_label, self._accessible_name(meter))

            page.setProperty("practice", {"message": "No speech was detected."})
            self._settle(page)
            self.assertFalse(skip.property("visible"))
            self.assertTrue(continue_button.property("visible"))
            self.assertEqual(continue_button.property("text"), "Finish setup")
            self.assertEqual(start.property("text"), "Try again")
            self.assertEqual(start.property("kind"), "secondary")
            self.assertEqual(primary_count(), 1)

            self.assertTrue(QMetaObject.invokeMethod(continue_button, "click"))
            self._settle(page)
            self.assertEqual(
                bridge.calls[-3:],
                [
                    ("stopPractice", None),
                    ("clearPractice", None),
                    ("completeOnboarding", None),
                ],
            )
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)
    def test_practice_states_actions_and_temporary_results(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "PracticePage.qml"
        )
        try:
            status = page.findChild(QObject, "practiceStatus")
            start_stop = page.findChild(QObject, "practiceStartStopButton")
            retry = page.findChild(QObject, "practiceRetryButton")
            clear = page.findChild(QObject, "practiceClearButton")
            heard = page.findChild(QObject, "practiceHeardTranscript")
            would_type = page.findChild(QObject, "practiceWouldTypeTranscript")
            self.assertIsNotNone(status)
            self.assertIsNotNone(start_stop)
            self.assertIsNotNone(retry)
            self.assertIsNotNone(clear)
            segments = page.findChild(QObject, "practiceMeterSegments")
            self.assertIsNotNone(segments)
            self.assertEqual(segments.property("count"), 5)

            meter = page.findChild(QObject, "practiceMicrophoneMeter")
            self.assertIsNotNone(meter)

            page.setProperty("practice", {"mic_level_band": "high"})
            self._settle(page)
            self.assertEqual(status.property("label"), "Ready to practice")
            self.assertIn("Nothing is timed", status.property("description"))
            self.assertTrue(start_stop.property("visible"))
            self.assertEqual(start_stop.property("text"), "Start")
            self.assertEqual(start_stop.property("kind"), "primary")
            self.assertTrue(start_stop.property("enabled"))
            self.assertFalse(retry.property("visible"))
            self.assertFalse(clear.property("enabled"))
            self.assertFalse(meter.property("visible"))
            accessible_window = QAccessible.queryAccessibleInterface(window)
            self.assertFalse(
                any(
                    interface.role() == QAccessible.Role.ProgressBar
                    and "Microphone input level"
                    in interface.text(QAccessible.Text.Name)
                    for interface in self._accessible_descendants(
                        accessible_window
                    )
                )
            )

            page.setProperty("practice", {"active": True, "mic_level_band": "silent"})
            self._settle(page)
            self.assertEqual(status.property("label"), "Listening")
            self.assertEqual(status.property("description"), "Waiting for sound")
            self.assertTrue(meter.property("visible"))
            self.assertTrue(
                any(
                    interface.role() == QAccessible.Role.ProgressBar
                    and "Microphone input level"
                    in interface.text(QAccessible.Text.Name)
                    for interface in self._accessible_descendants(
                        QAccessible.queryAccessibleInterface(window)
                    )
                )
            )
            self.assertIn("Waiting for sound", self._accessible_name(meter))
            self.assertEqual(start_stop.property("text"), "Stop")
            self.assertEqual(start_stop.property("kind"), "primary")
            self.assertFalse(retry.property("visible"))

            page.setProperty("practice", {"active": True, "mic_level_band": "good"})
            self._settle(page)
            self.assertIn("Sound detected", status.property("description"))
            self.assertIn("Good", self._accessible_name(meter))
            self.assertTrue(QMetaObject.invokeMethod(start_stop, "click"))
            self.assertIn(("stopPractice", None), bridge.calls)

            page.setProperty("practice", {"processing": True, "level": "silent"})
            self._settle(page)
            self.assertEqual(status.property("label"), "Transcribing locally")
            self.assertTrue(start_stop.property("visible"))
            self.assertEqual(start_stop.property("text"), "Processing…")
            self.assertEqual(start_stop.property("kind"), "secondary")
            self.assertFalse(start_stop.property("enabled"))
            self.assertEqual(
                start_stop.property("accessibleDescription"),
                "Temporary practice is processing locally",
            )
            self.assertFalse(retry.property("visible"))
            self.assertFalse(retry.property("enabled"))
            self.assertFalse(meter.property("visible"))

            page.setProperty(
                "practice",
                {
                    "hasResult": True,
                    "heard": "hello speakr",
                    "wouldType": "Hello Speakr",
                    "level": "silent",
                },
            )
            self._settle(page)
            # Result contract: one check draw plus a 1.2 s reading window
            # before the action row changes to Retry.
            self.assertTrue(bool(page.property("resultPending")))
            self.assertTrue(start_stop.property("visible"))
            self.assertEqual(start_stop.property("text"), "Processing…")
            self.assertFalse(start_stop.property("enabled"))
            self.assertFalse(retry.property("visible"))
            self.assertFalse(clear.property("enabled"))
            check = page.findChild(QObject, "practiceResultCheckDraw")
            self.assertIsNotNone(check)
            self.assertTrue(check.property("drawn"))
            self.assertTrue(
                self._wait_until(
                    page, lambda: bool(page.property("resultActionsReady"))
                )
            )
            self._settle(page)
            self.assertEqual(status.property("label"), "Ready to review")
            self.assertFalse(start_stop.property("visible"))
            self.assertTrue(retry.property("visible"))
            self.assertTrue(retry.property("enabled"))
            self.assertFalse(meter.property("visible"))
            self.assertEqual(heard.property("text"), "hello speakr")
            self.assertEqual(would_type.property("text"), "Hello Speakr")
            self.assertTrue(clear.property("enabled"))
            self.assertTrue(QMetaObject.invokeMethod(clear, "click"))
            self.assertIn(("clearPractice", None), bridge.calls)

            page.setProperty(
                "practice",
                {"message": "Speakr didn’t catch speech. Try again when you’re ready."},
            )
            self._settle(page)
            notice = page.findChild(QObject, "practiceResultNotice")
            self.assertTrue(notice.property("visible"))
            self.assertEqual(notice.property("kind"), "info")
            self.assertFalse(start_stop.property("visible"))
            self.assertTrue(retry.property("visible"))
            self.assertFalse(meter.property("visible"))
            self.assertTrue(retry.property("enabled"))
            self.assertTrue(QMetaObject.invokeMethod(retry, "click"))
            self.assertIn(("startPractice", None), bridge.calls)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)

    def test_leaving_shortcut_step_cancels_capture_before_ui_moves(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            page.setProperty("currentStep", 3)
            page.setProperty(
                "appState", {"hotkey": "right ctrl", "pending_hotkey": "ctrl+space"}
            )
            bridge.set_capturing_hotkey(True)
            self._settle(page)

            capture_notice = page.findChild(
                QObject, "onboardingHotkeyCaptureNotice"
            )
            back = page.findChild(QObject, "onboardingBackButton")
            heading = page.findChild(QObject, "onboardingStepHeading")
            self.assertIsNotNone(capture_notice)
            self.assertIsNotNone(back)
            self.assertTrue(bridge.capturingHotkey)
            self.assertTrue(capture_notice.property("visible"))

            self.assertTrue(QMetaObject.invokeMethod(back, "click"))
            self._settle(page)

            self.assertIn(("cancelHotkeyCapture", None), bridge.calls)
            self.assertFalse(bridge.capturingHotkey)
            self.assertEqual(page.property("currentStep"), 2)
            self.assertEqual(heading.property("title"), "Speech model")
            self.assertFalse(capture_notice.property("visible"))
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)

    def test_narrow_200_percent_high_contrast_reflows_without_horizontal_scroll(self):
        fixtures = []
        try:
            for name, scroll_name, surface_name in (
                ("OnboardingPage.qml", "onboardingScroll", "onboardingSetupCard"),
                ("PracticePage.qml", "practiceScroll", "practiceCaptureSurface"),
            ):
                fixture = self._fixture(name, text_scale=2.0, mode="high_contrast")
                fixtures.append(fixture)
                engine, bridge, theme, page, window, warnings = fixture
                theme.setProperty("reduceMotion", True)
                self._settle(page)
                scroll = page.findChild(QObject, scroll_name)
                surface = page.findChild(QObject, surface_name)
                self.assertIsNotNone(scroll)
                self.assertIsNotNone(surface)
                self.assertEqual(theme.property("effectTier"), "off")
                self.assertEqual(theme.property("motionOnboarding"), 0)
                self.assertAlmostEqual(QColor(surface.property("fillColor")).alphaF(), 1.0)
                self.assertGreaterEqual(surface.x(), 0)
                self.assertLessEqual(surface.x() + surface.width(), page.width() + 0.5)
                self.assertLessEqual(scroll.property("contentWidth"), scroll.width() + 0.5)
                self.assertEqual(warnings, [])
        finally:
            for engine, bridge, theme, page, window, warnings in fixtures:
                self._dispose(engine, bridge, theme, page, window, warnings)

    def test_pages_use_shared_visual_tokens_and_no_remote_or_idle_effects(self):
        onboarding = (self.qml / "OnboardingPage.qml").read_text(encoding="utf-8")
        practice = (self.qml / "PracticePage.qml").read_text(encoding="utf-8")
        rail = (self.qml / "OnboardingStepRail.qml").read_text(encoding="utf-8")
        check = (self.qml / "CheckDraw.qml").read_text(encoding="utf-8")
        combined = onboarding + practice + rail + check

        self.assertEqual(
            combined.count("Not stored by Speakr; clears when you leave Practice."),
            2,
        )
        for component in (
            "GlassSurface {",
            "SectionHeading {",
            "InlineNotice {",
            "StatusOrb {",
            "FocusRing {",
        ):
            self.assertIn(component, combined)
        for forbidden in (
            "http://",
            "https://",
            "XMLHttpRequest",
            "ShaderEffect",
            "Timer {",
            "Animation.Infinite",
            "ParticleSystem",
            "bridge.inject",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3,8}", combined))
        self.assertNotIn("duration: 180", combined)
        self.assertNotIn("duration: 1200", combined)
        self.assertIn("duration: root.tokens.motionOnboarding", onboarding)
        self.assertIn("Keys.onEscapePressed", onboarding)
        self.assertIn("bridge.cancelHotkeyCapture()", onboarding)
        # The rail owns the step nodes; activating one still routes through
        # goTo so leaving-step side effects stay in one place.
        self.assertIn("onStepActivated: function(index) { root.goTo(index) }",
                      onboarding)
        self.assertIn("onClicked: rail.stepActivated(index)", rail)
        # Storyboard motion stays token-driven: 220 ms check draw, 160 ms
        # connector fill, 100 ms press scale, 1.2 s reading window.
        self.assertIn("duration: Math.round(root.tokens.motionEmphasis * 0.4)",
                      check)
        self.assertIn("duration: Math.round(root.tokens.motionEmphasis * 0.6)",
                      check)
        self.assertIn("duration: rail.tokens.motionStage", rail)
        self.assertEqual(onboarding.count("scale: down && enabled ? 0.99 : 1"), 1)
        self.assertEqual(practice.count("scale: down && enabled ? 0.99 : 1"), 1)
        for source in (onboarding, practice):
            self.assertIn(
                "PauseAnimation { duration: root.tokens.motionReading }", source
            )

    def test_step_rail_check_draw_connector_fill_and_return_navigation(self):
        engine, bridge, theme, page, window, warnings = self._fixture(
            "OnboardingPage.qml"
        )
        try:
            page.setProperty("currentStep", 2)
            self._settle(page)

            def by_name(name):
                return next(
                    (
                        item
                        for item in self._visual_items(page)
                        if item.objectName() == name
                    ),
                    None,
                )

            checks = [by_name(f"onboardingStepCheck{index}") for index in range(5)]
            fills = [
                by_name(f"onboardingStepConnectorFill{index}") for index in range(4)
            ]
            states = [by_name(f"onboardingStepState{index}") for index in range(5)]
            self.assertTrue(all(item is not None for item in checks))
            self.assertTrue(all(item is not None for item in fills))
            self.assertTrue(all(item is not None for item in states))

            self.assertEqual(
                [bool(item.property("drawn")) for item in checks],
                [True, True, False, False, False],
            )
            self.assertEqual(
                [bool(item.property("visible")) for item in checks],
                [True, True, False, False, False],
            )
            self.assertEqual(
                [bool(item.property("filled")) for item in fills],
                [True, True, False, False],
            )
            self.assertEqual(
                [item.property("text") for item in states],
                ["Completed", "Completed", "Current", "Upcoming", "Upcoming"],
            )

            # Completing another step draws its check and fills its connector.
            page.setProperty("currentStep", 3)
            self._settle(page)
            self.assertTrue(bool(checks[2].property("drawn")))
            self.assertTrue(bool(fills[2].property("filled")))

            # A completed step stays keyboard-activatable and returns.
            first = by_name("onboardingStepButton0")
            self.assertIsNotNone(first)
            self.assertTrue(QMetaObject.invokeMethod(first, "click"))
            self._settle(page)
            self.assertEqual(page.property("currentStep"), 0)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, bridge, theme, page, window, warnings)

    def test_practice_result_reading_window_holds_actions_even_reduced_motion(self):
        for reduce_motion in (False, True):
            with self.subTest(reduce_motion=reduce_motion):
                engine, bridge, theme, page, window, warnings = self._fixture(
                    "OnboardingPage.qml"
                )
                try:
                    theme.setProperty("reduceMotion", reduce_motion)
                    # Reduced Motion collapses transformations but must
                    # preserve the 1.2 s reading window.
                    self.assertEqual(theme.property("motionReading"), 1200)
                    page.setProperty("currentStep", 4)
                    page.setProperty(
                        "practice",
                        {"processing": True, "mic_level_band": "silent"},
                    )
                    self._settle(page)

                    start = page.findChild(
                        QObject, "onboardingPracticeStartButton"
                    )
                    continue_button = page.findChild(
                        QObject, "onboardingContinueButton"
                    )
                    skip = page.findChild(QObject, "skipPracticeButton")
                    meter = page.findChild(QObject, "onboardingPracticeMeter")
                    self.assertIsNotNone(start)
                    self.assertIsNotNone(continue_button)
                    self.assertIsNotNone(skip)
                    self.assertIsNotNone(meter)

                    # Processing: the meter left with capture and no primary
                    # action is enabled.
                    self.assertFalse(meter.property("visible"))
                    self.assertFalse(start.property("enabled"))
                    self.assertFalse(continue_button.property("visible"))
                    self.assertFalse(skip.property("enabled"))

                    page.setProperty(
                        "practice",
                        {"text": "Hello Speakr", "mic_level_band": "silent"},
                    )
                    self._settle(page)

                    # Result: check drawn, action row still held.
                    check = page.findChild(
                        QObject, "onboardingPracticeResultCheckDraw"
                    )
                    self.assertIsNotNone(check)
                    self.assertTrue(check.property("drawn"))
                    self.assertTrue(bool(page.property("practiceResultPending")))
                    self.assertEqual(start.property("text"), "Processing…")
                    self.assertFalse(start.property("enabled"))
                    self.assertFalse(continue_button.property("visible"))
                    self.assertTrue(skip.property("visible"))
                    self.assertFalse(skip.property("enabled"))

                    started = time.monotonic()
                    self.assertTrue(
                        self._wait_until(
                            page,
                            lambda: bool(
                                page.property("practiceResultActionsReady")
                            ),
                        )
                    )
                    elapsed_ms = (time.monotonic() - started) * 1000.0
                    self.assertGreaterEqual(elapsed_ms, 600.0)
                    self._settle(page)

                    self.assertEqual(start.property("text"), "Try again")
                    self.assertEqual(start.property("kind"), "secondary")
                    self.assertTrue(start.property("enabled"))
                    self.assertTrue(continue_button.property("visible"))
                    self.assertEqual(
                        continue_button.property("text"), "Finish setup"
                    )
                    self.assertEqual(continue_button.property("kind"), "primary")
                    self.assertFalse(skip.property("visible"))
                    self.assertEqual(warnings, [])
                finally:
                    self._dispose(engine, bridge, theme, page, window, warnings)


if __name__ == "__main__":
    unittest.main()
