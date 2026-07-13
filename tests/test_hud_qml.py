from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import Property, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from speakr.app import SpeakrApp
from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge
from tests.test_qml_load import _App


class _HudApp(_App):
    def __init__(self, **ui_overrides):
        super().__init__(text_scale=int(ui_overrides.get("text_scale", 100)))
        self._ui_overrides = ui_overrides

    def settings_snapshot(self):
        settings = super().settings_snapshot()
        settings["ui"].update(self._ui_overrides)
        return settings


class _NativeWindow(QObject):
    def __init__(self, *, software_renderer=False, reduce_transparency=False):
        super().__init__()
        self._software_renderer = bool(software_renderer)
        self._reduce_transparency = bool(reduce_transparency)

    @Property(bool, constant=True)
    def softwareRenderer(self):
        return self._software_renderer

    @Property(bool, constant=True)
    def systemReduceTransparency(self):
        return self._reduce_transparency


class HudQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]
        cls.qml = cls.root / "speakr" / "ui" / "qml"
        cls.hud_source = (cls.qml / "Hud.qml").read_text(encoding="utf-8")

    def _load_hud(self, *, native_window=None, **ui_overrides):
        app = _HudApp(**ui_overrides)
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        if native_window is not None:
            engine.rootContext().setContextProperty("nativeWindow", native_window)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        engine.load(QUrl.fromLocalFile(str(self.qml / "Hud.qml")))
        self._pump()
        self.assertEqual(len(engine.rootObjects()), 1, warnings)
        self.assertEqual(warnings, [])
        return app, bridge, engine, engine.rootObjects()[0]

    @classmethod
    def _pump(cls, count=3):
        for _ in range(count):
            cls.qapp.processEvents()

    def _close(self, bridge, engine):
        bridge.close()
        engine.deleteLater()
        self._pump()

    @staticmethod
    def _visual_items(item):
        result = []
        pending = list(item.childItems())
        while pending:
            child = pending.pop()
            result.append(child)
            pending.extend(child.childItems())
        return result

    @staticmethod
    def _contrast(first, second):
        def luminance(value):
            color = QColor(value)
            channels = (color.redF(), color.greenF(), color.blueF())
            linear = [
                channel / 12.92
                if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        left, right = luminance(first), luminance(second)
        return (max(left, right) + 0.05) / (min(left, right) + 0.05)

    def test_window_flags_content_boundary_and_bounded_rendering(self):
        app, bridge, engine, hud = self._load_hud(reduced_motion="reduce")
        try:
            flags = hud.flags()
            self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
            self.assertTrue(flags & Qt.WindowType.Tool)
            self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
            self.assertTrue(flags & Qt.WindowType.WindowTransparentForInput)
            self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
            self.assertEqual(hud.modality(), Qt.WindowModality.NonModal)
            self.assertEqual(hud.width(), 360)
            self.assertEqual(hud.height(), 96)

            panel = hud.findChild(QObject, "hudPanel")
            theme = hud.findChild(QObject, "hudTheme")
            self.assertIsNotNone(panel)
            self.assertIsNotNone(theme)
            self.assertAlmostEqual(
                QColor(panel.property("fillColor")).alphaF(), 1.0, places=5
            )
            self.assertEqual(theme.property("motionStandard"), 0)
            self.assertEqual(theme.property("motionEmphasis"), 0)

            app.interface_state.update(
                capture="listening", capture_job_id=1, mic_level_band="good"
            )
            self._pump()
            stage = hud.findChild(QObject, "hudSignalPath")
            for item in self._visual_items(stage):
                label = item.property("text")
                content_height = item.property("contentHeight")
                if not label or content_height is None:
                    continue
                top = item.mapToScene(QPointF(0, 0)).y()
                self.assertLessEqual(
                    top + float(content_height),
                    hud.height() + 0.5,
                    f"standard HUD clips stage label {label!r}",
                )

            source = self.hud_source
            for forbidden in (
                "transcript",
                "selected_text",
                "clipboard",
                "screen_text",
                "foreground_window",
                "ShaderEffect",
                "layer.effect",
                "Timer {",
                "loops:",
            ):
                self.assertNotIn(forbidden, source)
            self.assertRegex(source, r"Repeater\s*\{\s*model:\s*5")

            app_source = (self.root / "speakr" / "app.py").read_text(
                encoding="utf-8"
            )
            meter_loop = re.search(
                r"def _meter_loop\(.*?\n\s*def ", app_source, re.DOTALL
            )
            self.assertIsNotNone(meter_loop)
            self.assertIn("time.sleep(0.25)", meter_loop.group(0))
            self.assertIn("self._schedule_ready(job_id, delay=1.2)", app_source)
        finally:
            self._close(bridge, engine)

    def test_truthful_runtime_flow_errors_and_reduced_motion_are_immediate(self):
        app, bridge, engine, hud = self._load_hud(reduced_motion="reduce")
        try:
            signal_path = hud.findChild(QObject, "hudSignalPath")
            primary = hud.findChild(QObject, "hudPrimaryText")
            secondary = hud.findChild(QObject, "hudSecondaryText")
            self.assertIsNotNone(signal_path)
            self.assertIsNotNone(primary)
            self.assertIsNotNone(secondary)

            app.interface_state.update(
                capture="listening",
                capture_job_id=40,
                capture_mode="dictation",
                mic_level_band="good",
            )
            self._pump()
            self.assertEqual(primary.property("text"), "Listening")
            app.interface_state.update(capture="idle", capture_job_id=0)

            states = (
                ("transcribing", "Transcribing locally", 1),
                ("formatting", "Cleaning up locally", 2),
                ("injecting", "Inserting text", 3),
                ("success", "Inserted", 4),
            )
            for pipeline, copy, stage in states:
                app.interface_state.update(
                    pipeline=pipeline,
                    pipeline_job_id=41,
                    pipeline_mode="dictation",
                )
                self._pump()
                self.assertEqual(hud.property("desiredPrimary"), copy)
                self.assertEqual(hud.property("displayedPrimary"), copy)
                self.assertEqual(primary.property("text"), copy)
                self.assertEqual(signal_path.property("activeStage"), stage)
                self.assertTrue(bool(hud.property("shouldShow")))

            app.interface_state.update(
                pipeline="formatting", pipeline_job_id=42, pipeline_mode="edit"
            )
            self._pump()
            self.assertEqual(
                hud.property("displayedPrimary"),
                "Applying your instruction locally",
            )

            app.interface_state.update(
                pipeline="idle",
                pipeline_job_id=43,
                status_code="no_speech",
                latest_outcome_code="no_speech",
            )
            self._pump()
            self.assertEqual(
                hud.property("displayedPrimary"),
                "Speakr didn't catch speech. Nothing was inserted.",
            )
            self.assertEqual(hud.property("displayedKind"), "warning")

            app.interface_state.update(
                pipeline="error", pipeline_job_id=44, status_code="pipeline_error"
            )
            self._pump()
            self.assertEqual(hud.property("displayedKind"), "danger")
            self.assertIn("Nothing was inserted", primary.property("text"))
            self.assertLessEqual(len(str(secondary.property("text"))), 80)

            app.interface_state.update(
                pipeline="idle", pipeline_job_id=0, capture_job_id=45
            )
            app.interface_state.latch_issue(
                "microphone_unavailable",
                "Microphone access is needed.",
                "open_system_settings",
            )
            self._pump()
            self.assertEqual(
                primary.property("text"), "Microphone access is needed."
            )
            self.assertEqual(hud.property("displayedKind"), "danger")

            app.interface_state.dismiss_issue("microphone_unavailable")
            app.interface_state.update(
                capture_job_id=0,
                pipeline="idle",
                pipeline_job_id=46,
                status_code="edit_failure",
                latest_outcome_code="edit_failure",
            )
            self._pump()
            self.assertEqual(
                primary.property("text"),
                "The original selection was not changed.",
            )
            self.assertEqual(hud.property("displayedKind"), "warning")
        finally:
            self._close(bridge, engine)

    def test_overlapping_capture_keeps_previous_job_secondary_and_stale_retire_is_safe(self):
        app, bridge, engine, hud = self._load_hud(reduced_motion="reduce")
        try:
            app.interface_state.update(
                pipeline="success",
                pipeline_job_id=101,
                pipeline_mode="dictation",
                status_code="success",
            )
            app.interface_state.update(
                capture="listening",
                capture_job_id=102,
                capture_mode="dictation",
                mic_level_band="good",
            )
            self._pump()
            self.assertEqual(hud.property("displayedPrimary"), "Listening")
            self.assertEqual(
                hud.property("displayedSecondary"),
                "Previous dictation: Inserted",
            )
            self.assertEqual(hud.property("displayedKind"), "listening")
            self.assertFalse(
                app.interface_state.retire_pipeline_job(101, {"success"})
            )
            self.assertTrue(bool(hud.property("shouldShow")))

            app.interface_state.update(
                capture="idle",
                capture_job_id=0,
                pipeline="transcribing",
                pipeline_job_id=103,
                mic_level_band="silent",
            )
            self._pump()
            self.assertFalse(
                app.interface_state.retire_pipeline_job(101, {"success"})
            )
            self._pump()
            self.assertEqual(
                hud.property("displayedPrimary"), "Transcribing locally"
            )
            self.assertEqual(
                app.interface_state.snapshot()["pipeline_job_id"], 103
            )
        finally:
            self._close(bridge, engine)

    def test_real_settle_timer_waits_for_capture_and_cannot_retire_newer_job(self):
        runtime = SpeakrApp.__new__(SpeakrApp)
        runtime._shutting_down = False
        runtime.interface_state = InterfaceState(
            {
                "availability": "ready",
                "pipeline": "success",
                "pipeline_job_id": 701,
                "capture": "listening",
                "capture_job_id": 702,
            }
        )

        runtime._schedule_pipeline_settle(701, delay=0.02, expected={"success"})
        time.sleep(0.06)
        snapshot = runtime.interface_state.snapshot()
        self.assertEqual(snapshot["pipeline_job_id"], 701)
        self.assertEqual(snapshot["capture_job_id"], 702)

        runtime.interface_state.update(capture="idle", capture_job_id=0)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if runtime.interface_state.snapshot()["pipeline_job_id"] == 0:
                break
            time.sleep(0.01)
        self.assertEqual(runtime.interface_state.snapshot()["pipeline_job_id"], 0)

        runtime.interface_state.update(
            pipeline="success", pipeline_job_id=711, status_code="success"
        )
        runtime._schedule_pipeline_settle(711, delay=0.04, expected={"success"})
        runtime.interface_state.update(
            pipeline="transcribing",
            pipeline_job_id=713,
            status_code="transcribing",
        )
        time.sleep(0.09)
        snapshot = runtime.interface_state.snapshot()
        self.assertEqual(snapshot["pipeline"], "transcribing")
        self.assertEqual(snapshot["pipeline_job_id"], 713)

    def test_latched_monitor_geometry_reflows_large_hud_at_150_and_200_percent(self):
        for scale in (150, 200):
            with self.subTest(scale=scale):
                edge = "top" if scale == 150 else "bottom"
                app, bridge, engine, hud = self._load_hud(
                    reduced_motion="reduce",
                    hud_size="large",
                    hud_edge=edge,
                    text_scale=scale,
                    hud_scale=scale,
                )
                try:
                    app.interface_state.update(
                        capture="listening",
                        capture_job_id=201,
                        mic_level_band="low",
                    )
                    self._pump()
                    app.interface_state.update(
                        active_monitor_x=100,
                        active_monitor_y=50,
                        active_monitor_width=640,
                        active_monitor_height=520,
                    )
                    self._pump()

                    expected_scale = scale / 100.0
                    self.assertEqual(
                        hud.width(),
                        min(
                            round(460 * expected_scale),
                            max(240, 640 - round(32 * expected_scale)),
                        ),
                    )
                    self.assertEqual(hud.height(), round(128 * expected_scale))
                    self.assertGreaterEqual(hud.x(), 100)
                    self.assertGreaterEqual(hud.y(), 50)
                    self.assertLessEqual(hud.x() + hud.width(), 740)
                    self.assertLessEqual(hud.y() + hud.height(), 570)
                    inset = round(24 * expected_scale)
                    expected_y = (
                        50 + inset
                        if edge == "top"
                        else 50 + 520 - hud.height() - inset
                    )
                    self.assertEqual(hud.y(), expected_y)

                    for object_name in (
                        "hudPanel",
                        "hudStateContent",
                        "hudStateIcon",
                        "hudPrimaryText",
                        "hudSecondaryText",
                        "hudSignalPath",
                    ):
                        item = hud.findChild(QObject, object_name)
                        self.assertIsInstance(item, QQuickItem, object_name)
                        top_left = item.mapToScene(QPointF(0, 0))
                        bottom_right = item.mapToScene(
                            QPointF(item.width(), item.height())
                        )
                        self.assertGreaterEqual(top_left.x(), -0.5, object_name)
                        self.assertGreaterEqual(top_left.y(), -0.5, object_name)
                        self.assertLessEqual(
                            bottom_right.x(), hud.width() + 0.5, object_name
                        )
                        self.assertLessEqual(
                            bottom_right.y(), hud.height() + 0.5, object_name
                        )
                    for object_name in ("hudPrimaryText", "hudSecondaryText"):
                        label = hud.findChild(QObject, object_name)
                        required_height = max(
                            float(label.property("implicitHeight") or 0),
                            float(label.property("contentHeight") or 0),
                        )
                        self.assertGreaterEqual(
                            label.height() + 0.5,
                            required_height,
                            f"{object_name} glyphs are clipped at {scale}%",
                        )
                finally:
                    self._close(bridge, engine)

    def test_high_contrast_is_opaque_and_full_motion_uses_only_bounded_tokens(self):
        app, bridge, engine, hud = self._load_hud(
            theme="high_contrast",
            visual_effects="full",
            reduced_motion="system",
            motion="system",
        )
        try:
            theme = hud.findChild(QObject, "hudTheme")
            panel = hud.findChild(QObject, "hudPanel")
            self.assertTrue(bool(theme.property("highContrast")))
            self.assertEqual(theme.property("effectTier"), "off")
            self.assertEqual(theme.property("motionStandard"), 160)
            self.assertEqual(theme.property("motionEmphasis"), 220)
            self.assertAlmostEqual(
                QColor(panel.property("fillColor")).alphaF(), 1.0, places=5
            )
            self.assertEqual(
                self.hud_source.count(
                    "duration: Math.round(tokens.motionStandard / 2)"
                ),
                2,
            )
            self.assertNotIn("NumberAnimation on", self.hud_source)
            self.assertNotIn("RotationAnimation", self.hud_source)

            badge = hud.findChild(QObject, "hudStateBadge")
            glyph = hud.findChild(QObject, "hudStateGlyph")
            self.assertIsNotNone(badge)
            self.assertIsNotNone(glyph)
            for pipeline, status_code, expected_kind, semantic_role in (
                ("error", "pipeline_error", "danger", "danger"),
                ("idle", "no_speech", "warning", "warning"),
            ):
                app.interface_state.update(
                    pipeline=pipeline,
                    pipeline_job_id=501,
                    status_code=status_code,
                )
                QTest.qWait(190)
                self._pump()
                self.assertEqual(hud.property("displayedKind"), expected_kind)
                self.assertEqual(
                    QColor(glyph.property("color")),
                    QColor(theme.property("background")),
                )
                self.assertEqual(
                    QColor(badge.property("color")),
                    QColor(theme.property(semantic_role)),
                )
                self.assertGreaterEqual(
                    self._contrast(
                        glyph.property("color"), badge.property("color")
                    ),
                    4.5,
                )
        finally:
            self._close(bridge, engine)

    def test_software_renderer_forces_reduced_tier_without_native_hud_blur(self):
        native_window = _NativeWindow(software_renderer=True)
        app, bridge, engine, hud = self._load_hud(
            native_window=native_window,
            theme="dark",
            visual_effects="full",
            reduced_motion="reduce",
        )
        try:
            theme = hud.findChild(QObject, "hudTheme")
            atmosphere = hud.findChild(QObject, "hudAtmosphere")
            panel = hud.findChild(QObject, "hudPanel")
            self.assertTrue(bool(theme.property("softwareRenderer")))
            self.assertEqual(theme.property("effectTier"), "reduced")
            self.assertFalse(bool(atmosphere.property("visible")))
            self.assertAlmostEqual(
                QColor(panel.property("fillColor")).alphaF(), 1.0, places=5
            )
        finally:
            self._close(bridge, engine)

    def test_success_bloom_starts_after_crossfade_reveals_success_state(self):
        app, bridge, engine, hud = self._load_hud(
            theme="dark",
            reduced_motion="system",
            motion="system",
        )
        try:
            ring = hud.findChild(QObject, "hudSuccessRing")
            bloom = hud.findChild(QObject, "hudSuccessBloom")
            self.assertIsNotNone(ring)
            self.assertIsNotNone(bloom)

            app.interface_state.update(
                pipeline="formatting", pipeline_job_id=601
            )
            QTest.qWait(190)
            self.assertEqual(hud.property("displayedKind"), "active")

            app.interface_state.update(
                pipeline="success", pipeline_job_id=601, status_code="success"
            )
            QTest.qWait(40)
            self.assertFalse(bool(ring.property("visible")))
            self.assertFalse(bool(bloom.property("running")))
            self.assertAlmostEqual(float(ring.property("opacity")), 0.0, places=3)

            QTest.qWait(65)
            self.assertTrue(bool(ring.property("visible")))
            self.assertTrue(bool(bloom.property("running")))
            self.assertEqual(hud.property("displayedKind"), "success")
            self.assertLess(float(ring.property("scale")), 1.1)
        finally:
            self._close(bridge, engine)

    @unittest.skipUnless(sys.platform == "win32", "Windows focus probe")
    def test_windows_native_probe_preserves_foreground_focus_and_caret(self):
        script = textwrap.dedent(
            f"""
            import ctypes
            import os
            import sys

            os.environ["QT_QPA_PLATFORM"] = "windows"
            os.environ["QT_QUICK_BACKEND"] = "software"

            from ctypes import wintypes
            from PySide6.QtCore import Property, QObject, QPointF, Signal, QUrl
            from PySide6.QtQml import QQmlApplicationEngine
            from PySide6.QtQuickControls2 import QQuickStyle
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

            class Bridge(QObject):
                stateChanged = Signal()
                settingsChanged = Signal()
                quittingChanged = Signal()

                def __init__(self):
                    super().__init__()
                    self._state = {{
                        "availability": "ready", "capture": "idle",
                        "capture_job_id": 0, "pipeline": "idle",
                        "pipeline_job_id": 0, "enabled": True,
                    }}
                    self._settings = {{"ui": {{
                        "theme": "dark", "hud_visibility": "while_dictating",
                        "hud_size": "standard", "hud_edge": "bottom",
                        "hud_scale": 100, "text_scale": 100,
                        "reduced_motion": "reduce",
                        "background_announcements": False,
                    }}}}

                @Property("QVariantMap", notify=stateChanged)
                def state(self):
                    return self._state

                @Property("QVariantMap", notify=settingsChanged)
                def settings(self):
                    return self._settings

                @Property(bool, notify=quittingChanged)
                def quitting(self):
                    return False

            class GUITHREADINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                    ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                    ("rcCaret", wintypes.RECT),
                ]

            def identities(hwnd):
                thread_id = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                info = GUITHREADINFO()
                info.cbSize = ctypes.sizeof(info)
                if not thread_id or not ctypes.windll.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
                    return None
                return int(info.hwndFocus or 0), int(info.hwndCaret or 0)

            QQuickStyle.setStyle("Basic")
            app = QApplication([])
            if app.platformName() != "windows":
                sys.exit(77)
            host = QWidget()
            host.setWindowTitle("Speakr HUD focus probe")
            edit = QLineEdit(host)
            edit.setGeometry(20, 20, 280, 44)
            edit.setText("caret identity")
            edit.setCursorPosition(5)
            host.resize(320, 84)
            host.show()
            host.activateWindow()
            edit.setFocus()
            QTest.qWait(120)
            ctypes.windll.user32.SetForegroundWindow(int(host.winId()))
            QTest.qWait(80)

            before_window = int(ctypes.windll.user32.GetForegroundWindow() or 0)
            before_identity = identities(before_window)
            if not before_window or before_identity is None or before_identity[0] == 0:
                sys.exit(77)

            bridge = Bridge()
            engine = QQmlApplicationEngine()
            engine.rootContext().setContextProperty("bridge", bridge)
            engine.load(QUrl.fromLocalFile({str(self.qml / 'Hud.qml')!r}))
            if len(engine.rootObjects()) != 1:
                sys.exit(2)
            hud = engine.rootObjects()[0]
            bridge._state = dict(bridge._state, capture="listening", capture_job_id=1)
            bridge.stateChanged.emit()
            QTest.qWait(180)

            after_window = int(ctypes.windll.user32.GetForegroundWindow() or 0)
            after_identity = identities(after_window)
            if after_identity is None:
                sys.exit(77)
            if before_window != after_window:
                sys.exit(3)
            if before_identity != after_identity:
                sys.exit(4)
            if QApplication.focusWidget() is not edit or hud.isActive():
                sys.exit(5)
            stage = hud.findChild(QObject, "hudSignalPath")
            pending = list(stage.childItems())
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                label = item.property("text")
                content_height = item.property("contentHeight")
                if label and content_height is not None:
                    top = item.mapToScene(QPointF(0, 0)).y()
                    if top + float(content_height) > hud.height() + 0.5:
                        sys.exit(6)
            sys.exit(0)
            """
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "windows"
        environment["QT_QUICK_BACKEND"] = "software"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 77:
            self.skipTest("interactive Windows focus/caret identities unavailable")
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
