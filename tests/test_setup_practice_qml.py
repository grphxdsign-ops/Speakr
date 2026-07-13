from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, Property, QMetaObject, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication


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
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])
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

    def _dispose(self, engine, theme, page, window):
        page.setParentItem(None)
        page.deleteLater()
        window.close()
        theme.deleteLater()
        engine.deleteLater()
        self.qapp.processEvents()

    def _settle(self, page):
        for _ in range(4):
            self.qapp.processEvents()
            page.ensurePolished()

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
            page.setProperty("appState", {"hotkey": "right ctrl", "pending_hotkey": "ctrl+space"})
            bridge.set_capturing_hotkey(True)
            self._settle(page)
            self.assertEqual(capture.property("title"), "Press your new shortcut")
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
            self._dispose(engine, theme, page, window)

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

            page.setProperty("practice", {"active": True, "mic_level_band": "good"})
            self._settle(page)
            self.assertEqual(status.property("label"), "Listening")
            self.assertIn("Sound detected", status.property("description"))
            self.assertEqual(start_stop.property("text"), "Stop")
            self.assertTrue(QMetaObject.invokeMethod(start_stop, "click"))
            self.assertIn(("stopPractice", None), bridge.calls)

            page.setProperty("practice", {"processing": True, "level": "silent"})
            self._settle(page)
            self.assertEqual(status.property("label"), "Transcribing locally")
            self.assertFalse(retry.property("enabled"))

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
            self.assertEqual(status.property("label"), "Ready to review")
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
            self.assertTrue(retry.property("enabled"))
            self.assertTrue(QMetaObject.invokeMethod(retry, "click"))
            self.assertIn(("startPractice", None), bridge.calls)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(engine, theme, page, window)

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
            self._dispose(engine, theme, page, window)

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
                self._dispose(engine, theme, page, window)

    def test_pages_use_shared_visual_tokens_and_no_remote_or_idle_effects(self):
        onboarding = (self.qml / "OnboardingPage.qml").read_text(encoding="utf-8")
        practice = (self.qml / "PracticePage.qml").read_text(encoding="utf-8")
        combined = onboarding + practice

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
        self.assertIn("duration: root.tokens.motionOnboarding", onboarding)
        self.assertIn("Keys.onEscapePressed", onboarding)
        self.assertIn("bridge.cancelHotkeyCapture()", onboarding)
        self.assertIn("onClicked: root.goTo(index)", onboarding)


if __name__ == "__main__":
    unittest.main()
