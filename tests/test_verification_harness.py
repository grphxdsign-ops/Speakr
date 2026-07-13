from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, QUrl
from PySide6.QtGui import QColor, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from scripts.capture_ui_verification import capture_scenarios
from scripts.verify_luminous_interface import (
    REQUIRED_EVIDENCE_TESTS,
    detect_missing_interactive_windows_proof,
    detect_qml_runtime_warnings,
)
from speakr import qt_ui
from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge
from tests.test_qml_load import _App
from tests.test_shell_home import _WindowController


class _MatrixApp(_App):
    def settings_snapshot(self):
        settings = super().settings_snapshot()
        settings["ui"].update(
            {
                "theme": "light",
                "visual_effects": "off",
                "motion": "reduced",
                "reduced_motion": "reduce",
            }
        )
        return settings


class _FocusStealingHud:
    def __init__(self):
        self.suppressed = False
        self.hidden = False

    def property(self, name):
        if name == "focusGuardSuppressed":
            return self.suppressed
        return None

    def setProperty(self, name, value):
        if name == "focusGuardSuppressed":
            self.suppressed = bool(value)
            return True
        return False

    @staticmethod
    def isActive():
        return True

    def hide(self):
        self.hidden = True


class VerificationHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]
        cls.qml = cls.root / "speakr" / "ui" / "qml"

    @classmethod
    def _pump(cls, count=6):
        for _ in range(count):
            cls.qapp.processEvents()

    def _load_main(self, app=None):
        app = app or _MatrixApp()
        bridge = Bridge(app)
        controller = _WindowController()
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.rootContext().setContextProperty("nativeWindow", controller)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        engine.load(QUrl.fromLocalFile(str(self.qml / "Main.qml")))
        self._pump()
        self.assertEqual(len(engine.rootObjects()), 1, warnings)
        self.assertEqual(warnings, [])
        engine._verification_warnings = warnings
        return app, bridge, controller, engine, engine.rootObjects()[0]

    def _close_main(self, bridge, engine, tray=None):
        warnings = getattr(engine, "_verification_warnings", [])
        if tray is not None:
            tray.hide()
            tray.deleteLater()
        for root in engine.rootObjects():
            root.hide()
            root.deleteLater()
        engine.collectGarbage()
        engine.deleteLater()
        bridge.close()
        bridge.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self._pump()
        self.assertEqual(warnings, [], "QML warnings were emitted during teardown")

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
        first_luminance = cls._luminance(QColor(first))
        second_luminance = cls._luminance(QColor(second))
        return (max(first_luminance, second_luminance) + 0.05) / (
            min(first_luminance, second_luminance) + 0.05
        )

    def test_required_evidence_map_resolves_to_real_tests(self):
        loader = unittest.defaultTestLoader
        for area, test_ids in REQUIRED_EVIDENCE_TESTS.items():
            with self.subTest(area=area):
                self.assertGreater(len(test_ids), 0)
                for test_id in test_ids:
                    suite = loader.loadTestsFromName(test_id)
                    self.assertEqual(
                        suite.countTestCases(),
                        1,
                        f"missing evidence test: {test_id}",
                    )

    def test_every_qml_component_is_reachable_and_has_no_unbounded_effect(self):
        sources = {
            path.stem: path.read_text(encoding="utf-8")
            for path in self.qml.glob("*.qml")
        }
        reachable = set()
        pending = ["Main", "Hud"]
        while pending:
            component = pending.pop()
            if component in reachable:
                continue
            reachable.add(component)
            source = sources[component]
            for candidate in sources:
                if candidate in reachable:
                    continue
                pattern = rf"(?<![.\w]){re.escape(candidate)}\s*\{{"
                if re.search(pattern, source):
                    pending.append(candidate)

        self.assertEqual(set(sources), reachable)
        forbidden = {
            "infinite animation": re.compile(r"Animation\.Infinite|loops\s*:"),
            "unconditional running animation": re.compile(r"running\s*:\s*true\b"),
        }
        for component, source in sources.items():
            for description, pattern in forbidden.items():
                self.assertIsNone(
                    pattern.search(source), f"{component}.qml has {description}"
                )
            for url in re.findall(r"https?://[^\s\"']+", source, re.IGNORECASE):
                self.assertRegex(
                    url,
                    r"^http://(?:127(?:\.\d{1,3}){3}|localhost)(?::\d+)?(?:/|$)",
                    f"{component}.qml has a non-loopback URL",
                )

    def test_runtime_warning_parser_rejects_green_qml_failures(self):
        clean = "Ran 157 tests in 20.0s\n\nOK\n"
        self.assertEqual(detect_qml_runtime_warnings(clean), [])
        diagnostics = "\n".join(
            (
                "file:///tmp/Main.qml:71: TypeError: Cannot read property 'x' of null",
                "file:///tmp/Hud.qml:99:5: Binding loop detected for property width",
                "file:///tmp/Page.qml:17:9: onFoo is deprecated. Use function syntax",
            )
        )
        matches = detect_qml_runtime_warnings(clean + diagnostics)
        self.assertEqual(len(matches), 3)
        skipped_focus = (
            "test_windows_native_probe_preserves_foreground_focus_and_caret "
            "(test_hud_qml.HudQmlTests.test_windows_native_probe_preserves_"
            "foreground_focus_and_caret) ... skipped 'interactive desktop unavailable'"
        )
        expected = 1 if sys.platform == "win32" else 0
        self.assertEqual(
            len(detect_missing_interactive_windows_proof(skipped_focus)), expected
        )

    def test_effect_tier_theme_and_contrast_matrix(self):
        engine = QQmlApplicationEngine()
        component = QQmlComponent(
            engine, QUrl.fromLocalFile(str(self.qml / "Theme.qml"))
        )
        theme = component.create()
        self.assertIsNotNone(theme, [error.toString() for error in component.errors()])
        try:
            theme.setProperty("systemHighContrast", False)
            theme.setProperty("systemReduceTransparency", False)
            theme.setProperty("softwareRenderer", False)
            for mode in ("light", "dark"):
                for effects, expected in (
                    ("full", "full"),
                    ("reduced", "reduced"),
                    ("off", "off"),
                ):
                    with self.subTest(mode=mode, effects=effects):
                        theme.setProperty("mode", mode)
                        theme.setProperty("visualEffects", effects)
                        self._pump(2)
                        self.assertEqual(theme.property("effectTier"), expected)
                        self.assertGreaterEqual(
                            self._contrast(
                                theme.property("text"), theme.property("surface")
                            ),
                            7.0,
                        )
                        self.assertGreaterEqual(
                            self._contrast(
                                theme.property("mutedText"),
                                theme.property("surface"),
                            ),
                            4.5,
                        )
                        if effects == "off":
                            self.assertEqual(theme.property("shellOpacity"), 1.0)
                            self.assertEqual(
                                QColor(theme.property("atmosphereViolet")).alphaF(),
                                0.0,
                            )

            for effects in ("system", "full", "reduced", "off"):
                with self.subTest(high_contrast_effects=effects):
                    theme.setProperty("mode", "high_contrast")
                    theme.setProperty("visualEffects", effects)
                    self._pump(2)
                    self.assertEqual(theme.property("effectTier"), "off")
                    for role in (
                        "shellOpacity",
                        "navigationOpacity",
                        "majorOpacity",
                        "noticeOpacity",
                        "contentOpacity",
                        "hudOpacity",
                    ):
                        self.assertEqual(theme.property(role), 1.0, role)

            theme.setProperty("mode", "dark")
            theme.setProperty("visualEffects", "full")
            theme.setProperty("softwareRenderer", True)
            self._pump(2)
            self.assertEqual(theme.property("effectTier"), "reduced")
            theme.setProperty("softwareRenderer", False)
            theme.setProperty("systemReduceTransparency", True)
            self._pump(2)
            self.assertEqual(theme.property("effectTier"), "reduced")
        finally:
            theme.deleteLater()
            engine.deleteLater()
            self._pump()

    def test_all_pages_reflow_and_focus_heading_across_size_scale_matrix(self):
        pages = {
            "home": ("homeBoundedViewport", "Home"),
            "practice": ("practiceScroll", "Practice"),
            "vocabulary": ("vocabularyScroll", "Vocabulary"),
            "settings": ("settingsScroll", "Settings"),
            "help": ("helpScroll", "Help & diagnostics"),
        }
        for text_scale in (100, 150, 200):
            with self.subTest(text_scale=text_scale):
                app = _MatrixApp(text_scale=text_scale)
                _app, bridge, _controller, engine, main = self._load_main(app)
                try:
                    main.show()
                    for width, height in ((960, 700), (640, 520)):
                        main.setWidth(width)
                        main.setHeight(height)
                        self._pump()
                        self.assertEqual(main.width(), width)
                        self.assertEqual(main.height(), height)
                        for page, (scroll_name, heading) in pages.items():
                            main.setProperty("currentPage", page)
                            self.assertTrue(
                                QMetaObject.invokeMethod(main, "focusCurrentPage")
                            )
                            self._pump()
                            scroll = main.findChild(QObject, scroll_name)
                            self.assertIsNotNone(scroll, scroll_name)
                            self.assertLessEqual(
                                float(scroll.property("contentWidth")),
                                float(scroll.property("availableWidth")) + 0.5,
                                f"{page} horizontally overflows at "
                                f"{width}x{height}/{text_scale}%",
                            )
                            focused = main.activeFocusItem()
                            self.assertIsNotNone(focused, page)
                            self.assertEqual(str(focused.property("text")), heading)
                    self.assertEqual(engine._verification_warnings, [])
                finally:
                    self._close_main(bridge, engine)

    def test_close_hides_main_while_tray_and_event_loop_remain_alive(self):
        app, bridge, _controller, engine, main = self._load_main()
        icon = QIcon(str(self.root / "assets" / "icon.png"))
        self.assertFalse(icon.isNull())
        self.qapp.setQuitOnLastWindowClosed(False)
        tray = qt_ui._build_tray(qt_ui._load_qt(), app, bridge, icon)
        bridge.attach_frontend(main, None, tray)
        try:
            tray.show()
            main.show()
            self._pump()
            self.assertTrue(main.isVisible())
            self.assertTrue(tray.isVisible())

            self.assertFalse(main.close())
            self._pump()

            self.assertFalse(main.isVisible())
            self.assertTrue(tray.isVisible())
            self.assertFalse(self.qapp.quitOnLastWindowClosed())
            self.assertFalse(self.qapp.closingDown())
        finally:
            self._close_main(bridge, engine, tray)

    def test_show_main_restores_hidden_and_minimized_window(self):
        _app, bridge, _controller, engine, main = self._load_main()
        bridge.attach_frontend(main, None, None)
        try:
            main.showMinimized()
            self._pump()
            self.assertEqual(main.visibility(), QWindow.Visibility.Minimized)
            bridge.show_main()
            self._pump()
            self.assertTrue(main.isVisible())
            self.assertEqual(main.visibility(), QWindow.Visibility.Windowed)

            main.hide()
            self._pump()
            self.assertFalse(main.isVisible())
            bridge.show_main()
            self._pump()
            self.assertTrue(main.isVisible())
            self.assertEqual(main.visibility(), QWindow.Visibility.Windowed)
        finally:
            self._close_main(bridge, engine)

    def test_hud_focus_guard_fails_closed_and_latches_recovery(self):
        app = _App()
        bridge = Bridge(app)
        hud = _FocusStealingHud()
        bridge.attach_frontend(None, hud, None)
        try:
            bridge._verify_hud_focus()
            snapshot = app.interface_state.snapshot()
            self.assertTrue(hud.suppressed)
            self.assertTrue(hud.hidden)
            self.assertEqual(snapshot["last_issue"]["code"], "hud_focus_guard")
            self.assertEqual(snapshot["last_issue"]["action"], "open_speakr")
            self.assertFalse(snapshot["last_issue"]["blocking"])
        finally:
            bridge.close()
            bridge.deleteLater()
            self._pump()

    def test_platform_screenshot_manifest_is_complete_and_idempotent(self):
        names = (
            "help-light-off-640x520-200",
            "hud-error-high-contrast-large-200",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = capture_scenarios(output, names)
            second = capture_scenarios(output, names)
            self.assertEqual(first, second)
            self.assertEqual(len(first["scenarios"]), len(names))
            self.assertIn(first["platform"]["qpa"], {"offscreen", "windows", "cocoa"})
            for artifact in first["scenarios"]:
                self.assertEqual(artifact["qml_warnings"], [])
                self.assertEqual(len(artifact["sha256"]), 64)
                self.assertGreater(artifact["width"], 0)
                self.assertGreater(artifact["height"], 0)
                self.assertGreater((output / artifact["file"]).stat().st_size, 100)

    def test_verification_tools_add_no_network_surface(self):
        for path in (
            self.root / "scripts" / "capture_ui_verification.py",
            self.root / "scripts" / "verify_luminous_interface.py",
        ):
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"https?://")
            self.assertNotRegex(source, r"\b(import|from)\s+(requests|socket|httpx|urllib)")

        state = InterfaceState({"availability": "ready"}).snapshot()
        forbidden_fragments = (
            "audio",
            "transcript",
            "selected",
            "clipboard",
            "window_title",
            "screen_content",
        )
        for key in state:
            self.assertFalse(
                any(fragment in key.casefold() for fragment in forbidden_fragments),
                key,
            )

    @unittest.skipUnless(sys.platform == "win32", "Windows QPA fallback proof")
    def test_windows_10_real_qpa_uses_scene_glass_and_visible_system_frame(self):
        script = textwrap.dedent(
            f"""
            import os
            import sys
            from pathlib import Path

            os.environ["QT_QPA_PLATFORM"] = "windows"
            os.environ["QT_QUICK_BACKEND"] = "software"
            os.environ["QSG_RHI_BACKEND"] = "software"

            from PySide6.QtCore import QObject
            from PySide6.QtGui import QColor
            from PySide6.QtQml import QQmlApplicationEngine
            from PySide6.QtQuickControls2 import QQuickStyle
            from PySide6.QtWidgets import QApplication

            from speakr import native_window, qt_ui
            from speakr.qt_ui import Bridge
            from tests.test_qml_load import _App

            class Windows10FrameAdapter(native_window._WindowsAdapter):
                def enable_custom_chrome(self, _window):
                    return False

            QQuickStyle.setStyle("Basic")
            application = QApplication([])
            if application.platformName() != "windows":
                sys.exit(2)
            qt = qt_ui._load_qt()
            app = _App()
            bridge = Bridge(app)
            adapter = Windows10FrameAdapter(build=19045)
            controller = native_window.NativeWindowController(
                qt=qt,
                theme="dark",
                visual_effects="full",
                software_renderer=False,
                platform_name="win32",
                adapter=adapter,
            )
            engine = QQmlApplicationEngine()
            engine.rootContext().setContextProperty("bridge", bridge)
            engine.rootContext().setContextProperty("nativeWindow", controller)
            original = {{}}

            def attach(root):
                original["flags"] = root.flags()
                controller.attach(root)

            main, component = qt_ui._create_qml_root(
                qt,
                engine,
                Path({str(self.qml / 'Main.qml')!r}),
                before_complete=attach,
            )
            main.show()
            for _ in range(8):
                application.processEvents()

            chrome = main.findChild(QObject, "windowChrome")
            backdrop = main.findChild(QObject, "cosmicBackdrop")
            ok = (
                controller.material == "scene_glass"
                and controller.effectTier == "full"
                and not controller.nativeMaterialAvailable
                and not controller.customChromeEnabled
                and not main.property("nativeMaterialActive")
                and QColor(main.property("color")).alphaF() == 1.0
                and main.flags() == original["flags"]
                and main.isVisible()
                and chrome is not None
                and not chrome.property("visible")
                and backdrop is not None
                and backdrop.property("paintCanvas")
            )
            controller.detach()
            bridge.close()
            main.hide()
            main.deleteLater()
            component.deleteLater()
            engine.deleteLater()
            application.processEvents()
            sys.exit(0 if ok else 3)
            """
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "windows"
        environment["QT_QUICK_BACKEND"] = "software"
        environment["QSG_RHI_BACKEND"] = "software"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows QPA maximize proof")
    def test_windows_real_qpa_custom_maximize_changes_hwnd_and_restores(self):
        script = textwrap.dedent(
            f"""
            import ctypes
            import os
            import sys
            from pathlib import Path

            os.environ["QT_QPA_PLATFORM"] = "windows"
            os.environ["QT_QUICK_BACKEND"] = "software"
            os.environ["QSG_RHI_BACKEND"] = "software"

            from PySide6.QtCore import QMetaObject, QObject
            from PySide6.QtGui import QWindow
            from PySide6.QtQml import QQmlApplicationEngine
            from PySide6.QtQuickControls2 import QQuickStyle
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication

            from speakr import native_window, qt_ui
            from speakr.qt_ui import Bridge
            from tests.test_qml_load import _App

            QQuickStyle.setStyle("Basic")
            application = QApplication([])
            if application.platformName() != "windows":
                sys.exit(2)
            qt = qt_ui._load_qt()
            app = _App()
            bridge = Bridge(app)
            adapter = native_window._WindowsAdapter(build=19045)
            controller = native_window.NativeWindowController(
                qt=qt,
                theme="dark",
                visual_effects="full",
                software_renderer=False,
                platform_name="win32",
                adapter=adapter,
            )
            engine = QQmlApplicationEngine()
            engine.rootContext().setContextProperty("bridge", bridge)
            engine.rootContext().setContextProperty("nativeWindow", controller)
            main, component = qt_ui._create_qml_root(
                qt,
                engine,
                Path({str(self.qml / 'Main.qml')!r}),
                before_complete=controller.attach,
            )
            screen = application.primaryScreen()
            if screen is None:
                sys.exit(3)
            work = screen.availableGeometry()
            width = min(800, max(640, work.width() - 160))
            height = min(600, max(520, work.height() - 160))
            x = work.x() + max(0, (work.width() - width) // 2)
            y = work.y() + max(0, (work.height() - height) // 2)
            main.setGeometry(x, y, width, height)
            main.show()
            QTest.qWait(180)

            button = main.findChild(QObject, "maximizeWindowButton")
            if button is None or not controller.customChromeEnabled:
                sys.exit(4)
            original = main.geometry()
            hwnd = int(main.winId())
            if not hwnd or ctypes.windll.user32.IsZoomed(hwnd):
                sys.exit(5)

            if not QMetaObject.invokeMethod(button, "click"):
                sys.exit(6)
            QTest.qWait(260)
            maximized = main.geometry()
            tolerance = 16
            maximize_ok = (
                bool(ctypes.windll.user32.IsZoomed(hwnd))
                and controller.maximized
                and main.visibility() == QWindow.Visibility.Maximized
                and main.visibility() != QWindow.Visibility.FullScreen
                and maximized != original
                and maximized.left() >= work.left() - tolerance
                and maximized.top() >= work.top() - tolerance
                and maximized.right() <= work.right() + tolerance
                and maximized.bottom() <= work.bottom() + tolerance
            )
            if not maximize_ok:
                sys.exit(7)

            if not QMetaObject.invokeMethod(button, "click"):
                sys.exit(8)
            QTest.qWait(260)
            restored = main.geometry()
            restore_ok = (
                not bool(ctypes.windll.user32.IsZoomed(hwnd))
                and not controller.maximized
                and main.visibility() == QWindow.Visibility.Windowed
                and main.visibility() != QWindow.Visibility.FullScreen
                and abs(restored.x() - original.x()) <= tolerance
                and abs(restored.y() - original.y()) <= tolerance
                and abs(restored.width() - original.width()) <= tolerance
                and abs(restored.height() - original.height()) <= tolerance
            )
            controller.detach()
            bridge.close()
            main.hide()
            main.deleteLater()
            component.deleteLater()
            engine.deleteLater()
            application.processEvents()
            sys.exit(0 if restore_ok else 9)
            """
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "windows"
        environment["QT_QUICK_BACKEND"] = "software"
        environment["QSG_RHI_BACKEND"] = "software"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            "Production custom maximize/restore failed. "
            f"Child exit {result.returncode}.\nstdout:\n{result.stdout}"
            f"\nstderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
