from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import Property, QMetaObject, QObject, QRectF, Signal, Slot, QUrl
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from speakr import native_window, qt_ui
from speakr.qt_ui import Bridge
from tests.test_qml_load import _App


class _WindowController(QObject):
    materialChanged = Signal()
    customChromeEnabledChanged = Signal()
    systemReduceTransparencyChanged = Signal()
    softwareRendererChanged = Signal()
    maximizedChanged = Signal()

    def __init__(self):
        super().__init__()
        self._material = "scene_glass"
        self._custom = True
        self._maximized = False
        self.hit_regions = None
        self.action = ""
        self.visual_preferences = None

    @Property(str, notify=materialChanged)
    def material(self):
        return self._material

    @Property(bool, notify=customChromeEnabledChanged)
    def customChromeEnabled(self):
        return self._custom

    @Property(bool, notify=systemReduceTransparencyChanged)
    def systemReduceTransparency(self):
        return False

    @Property(bool, notify=softwareRendererChanged)
    def softwareRenderer(self):
        return False

    @Property(bool, notify=maximizedChanged)
    def maximized(self):
        return self._maximized

    def set_custom_chrome(self, enabled: bool):
        enabled = bool(enabled)
        if self._custom != enabled:
            self._custom = enabled
            self.customChromeEnabledChanged.emit()

    @Slot(result=bool)
    def beginSystemMove(self):
        self.action = "move"
        return True

    @Slot(object, result=bool)
    def beginSystemResize(self, _edge):
        self.action = "resize"
        return True

    @Slot()
    def minimize(self):
        self.action = "minimize"

    @Slot()
    def toggleMaximize(self):
        self._maximized = not self._maximized
        self.action = "toggleMaximize"
        self.maximizedChanged.emit()

    @Slot()
    def closeMain(self):
        self.action = "close"

    @Slot(float, float, result=bool)
    def showSystemMenu(self, _x, _y):
        self.action = "systemMenu"
        return True

    @Slot("QVariant", "QVariant", "QVariant", "QVariant", "QVariant")
    def setHitRegions(self, titlebar, minimize, maximize, close, resize_border):
        self.hit_regions = (titlebar, minimize, maximize, close, resize_border)

    @Slot(str, str)
    def applyVisualPreferences(self, theme, visual_effects):
        self.visual_preferences = (theme, visual_effects)


class _NativeAdapter:
    def native_available(self):
        return False

    def apply_material(self, _window, _theme):
        return False

    def restore_material(self):
        return None

    def enable_custom_chrome(self, _window):
        return True

    def restore_custom_chrome(self, _window):
        return None

    def show_system_menu(self, _window, _x, _y):
        return False

    def detach(self):
        return None


class ShellHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]
        cls.qml = cls.root / "speakr" / "ui" / "qml"

    def _load_main(self, *, text_scale=100):
        app = _App(text_scale=text_scale)
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
        self.qapp.processEvents()
        self.qapp.processEvents()
        self.assertEqual(len(engine.rootObjects()), 1, warnings)
        self.assertEqual(warnings, [])
        return app, bridge, controller, engine, engine.rootObjects()[0]

    def test_custom_chrome_reports_logical_hit_regions_and_44px_controls(self):
        _app, bridge, controller, engine, main = self._load_main()
        try:
            self.assertTrue(bool(main.property("customChromeReady")))
            chrome = main.findChild(QObject, "windowChrome")
            drag = main.findChild(QObject, "titlebarDragRegion")
            minimize = main.findChild(QObject, "minimizeWindowButton")
            maximize = main.findChild(QObject, "maximizeWindowButton")
            close = main.findChild(QObject, "closeWindowButton")
            self.assertIsNotNone(chrome)
            self.assertIsNotNone(drag)
            for control in (minimize, maximize, close):
                self.assertIsNotNone(control)
                self.assertGreaterEqual(control.width(), 44)
                self.assertGreaterEqual(control.height(), 44)

            self.assertIsNotNone(controller.hit_regions)
            titlebar_rect, min_rect, max_rect, close_rect, border = controller.hit_regions
            for rect in (titlebar_rect, min_rect, max_rect, close_rect):
                self.assertIsInstance(rect, QRectF)
                self.assertGreater(rect.width(), 0)
                self.assertGreater(rect.height(), 0)
            self.assertGreater(float(border), 0)
            self.assertEqual(controller.visual_preferences, ("system", "system"))

            self.assertTrue(QMetaObject.invokeMethod(minimize, "click"))
            self.assertEqual(controller.action, "minimize")
            self.assertTrue(QMetaObject.invokeMethod(maximize, "click"))
            self.assertEqual(controller.action, "toggleMaximize")
            self.qapp.processEvents()
            self.assertEqual(maximize.property("windowAction"), "restore")
            self.assertTrue(QMetaObject.invokeMethod(close, "click"))
            self.assertEqual(controller.action, "close")
        finally:
            bridge.close()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_system_frame_fallback_hides_duplicate_custom_titlebar(self):
        _app, bridge, controller, engine, main = self._load_main()
        try:
            chrome = main.findChild(QObject, "windowChrome")
            self.assertTrue(chrome.property("visible"))
            controller.set_custom_chrome(False)
            self.qapp.processEvents()
            self.assertFalse(chrome.property("visible"))
            self.assertGreater(main.findChild(QObject, "pageContentSurface").height(), 0)
        finally:
            bridge.close()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_native_material_exposes_the_compositor_without_covering_fallbacks(self):
        _app, bridge, controller, engine, main = self._load_main()
        try:
            backdrop = main.findChild(QObject, "cosmicBackdrop")
            self.assertFalse(bool(main.property("nativeMaterialActive")))
            self.assertTrue(bool(backdrop.property("paintCanvas")))
            self.assertEqual(QColor(main.property("color")).alpha(), 255)

            controller._material = "mica"
            controller.materialChanged.emit()
            self.qapp.processEvents()
            self.assertTrue(bool(main.property("nativeMaterialActive")))
            self.assertFalse(bool(backdrop.property("paintCanvas")))
            self.assertEqual(QColor(main.property("color")).alpha(), 0)
        finally:
            bridge.close()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_real_native_controller_receives_shell_regions_for_snap_and_resize(self):
        app = _App()
        bridge = Bridge(app)
        qt = qt_ui._load_qt()
        controller = native_window.NativeWindowController(
            qt=qt,
            visual_effects="full",
            platform_name="test",
            adapter=_NativeAdapter(),
        )
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.rootContext().setContextProperty("nativeWindow", controller)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        main = component = None
        try:
            main, component = qt_ui._create_qml_root(
                qt,
                engine,
                self.qml / "Main.qml",
                before_complete=controller.attach,
            )
            self.qapp.processEvents()
            self.qapp.processEvents()
            self.assertEqual(warnings, [])
            self.assertTrue(bool(main.property("customChromeReady")))
            self.assertTrue(controller.customChromeEnabled)

            regions = controller._hit_regions
            for name in ("titlebar", "minimize", "maximize", "close"):
                self.assertIsNotNone(regions[name], name)
                self.assertGreater(regions[name][2], 0, name)
                self.assertGreater(regions[name][3], 0, name)
            self.assertGreater(regions["resize_border"], 0)

            max_x, max_y, max_width, max_height = regions["maximize"]
            self.assertEqual(
                native_window.windows_hit_test(
                    max_x + max_width / 2,
                    max_y + max_height / 2,
                    main.width(),
                    main.height(),
                    regions,
                ),
                native_window.HTMAXBUTTON,
            )
            self.assertEqual(
                native_window.windows_hit_test(
                    1, 1, main.width(), main.height(), regions
                ),
                native_window.HTTOPLEFT,
            )
            title_x, title_y, title_width, title_height = regions["titlebar"]
            self.assertEqual(
                native_window.windows_hit_test(
                    title_x + title_width / 2,
                    title_y + title_height / 2,
                    main.width(),
                    main.height(),
                    regions,
                ),
                native_window.HTCAPTION,
            )
        finally:
            controller.detach()
            bridge.close()
            if main is not None:
                main.close()
                main.deleteLater()
            if component is not None:
                component.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_home_reflows_at_minimum_size_and_200_percent_text(self):
        _app, bridge, _controller, engine, main = self._load_main(text_scale=200)
        try:
            main.setWidth(640)
            main.setHeight(520)
            self.qapp.processEvents()
            self.qapp.processEvents()
            self.assertEqual(main.property("topNavigationColumns"), 2)
            self.assertEqual(main.property("topNavigationRows"), 3)
            hero = main.findChild(QObject, "readinessHero")
            switch = main.findChild(QObject, "dictationSwitch")
            summary_repeater = main.findChild(QObject, "summaryRepeater")
            self.assertIsNotNone(hero)
            self.assertGreater(hero.width(), 0)
            self.assertGreater(hero.height(), 0)
            self.assertGreaterEqual(switch.width(), 44)
            self.assertIsNotNone(summary_repeater)
            self.assertEqual(summary_repeater.property("count"), 4)
        finally:
            bridge.close()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_shell_uses_shared_tokens_and_accessible_window_copy(self):
        sources = {
            name: (self.qml / name).read_text(encoding="utf-8")
            for name in ("Main.qml", "HomePage.qml", "WindowChrome.qml")
        }
        for name, source in sources.items():
            self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3,8}\b", source), name)
            self.assertNotIn("http://", source)
            self.assertNotIn("https://", source)

        chrome = sources["WindowChrome.qml"]
        for label in ("Minimize", "Maximize", "Restore", "Close"):
            self.assertIn(label, (self.qml / "ChromeButton.qml").read_text(encoding="utf-8"))
        self.assertIn('Accessible.name: qsTr("Window controls")', chrome)
        self.assertIn("controller.setHitRegions", chrome)
        self.assertIn("beginSystemMove", chrome)
        self.assertIn("showSystemMenu", chrome)

        main = sources["Main.qml"]
        self.assertIn("property bool customChromeReady: true", main)
        for shortcut in range(1, 6):
            self.assertIn(f'"Ctrl+{shortcut}"', main)
        self.assertIn("bridge.stopPractice()", main)
        self.assertIn("bridge.clearPractice()", main)

        home = sources["HomePage.qml"]
        self.assertIn("Everything stays on this device", chrome)
        self.assertIn("Private by design", home)
        self.assertIn("keeps no transcript history", home)


if __name__ == "__main__":
    unittest.main()
