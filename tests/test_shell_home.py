from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPointF,
    QRectF,
    Signal,
    Slot,
    Qt,
    QUrl,
)
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from speakr import native_window, qt_ui
from speakr.qt_ui import Bridge
from tests.qml_lifecycle import qml_test_application
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
    def toggleFullScreen(self):
        self.action = "toggleFullScreen"

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


class _CaptureApp(_App):
    def __init__(self):
        super().__init__()
        self.capture_callback = None
        self.cancel_count = 0

    def begin_hotkey_capture(self, callback):
        self.capture_callback = callback
        return True

    def cancel_hotkey_capture(self):
        self.cancel_count += 1


class ShellHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = qml_test_application()
        cls.root = Path(__file__).resolve().parents[1]
        cls.qml = cls.root / "speakr" / "ui" / "qml"

    @staticmethod
    def _visual_items(item):
        result = []
        pending = list(item.childItems())
        while pending:
            child = pending.pop()
            result.append(child)
            pending.extend(child.childItems())
        return result

    def _load_main(self, *, text_scale=100, app=None):
        app = app or _App(text_scale=text_scale)
        bridge = Bridge(app)
        controller = _WindowController()
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.rootContext().setContextProperty("nativeWindow", controller)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        engine._speakr_warning_messages = warnings
        engine.load(QUrl.fromLocalFile(str(self.qml / "Main.qml")))
        self.qapp.processEvents()
        self.qapp.processEvents()
        self.assertEqual(len(engine.rootObjects()), 1, warnings)
        self.assertEqual(warnings, [])
        return app, bridge, controller, engine, engine.rootObjects()[0]

    def _drain_deferred_deletes(self):
        for _ in range(3):
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.qapp.processEvents()

    def _dispose_qml(
        self,
        bridge,
        engine,
        *,
        root=None,
        components=(),
        warnings=None,
    ):
        captured_warnings = (
            warnings
            if warnings is not None
            else getattr(engine, "_speakr_warning_messages", None)
        )
        roots = []
        if root is not None:
            roots.append(root)
        try:
            for engine_root in engine.rootObjects():
                if engine_root not in roots:
                    roots.append(engine_root)
        except RuntimeError:
            pass

        for item in roots:
            try:
                item.hide()
                item.deleteLater()
            except RuntimeError:
                pass
        for component in components:
            if component is None:
                continue
            try:
                component.deleteLater()
            except RuntimeError:
                pass
        try:
            engine.deleteLater()
        except RuntimeError:
            pass
        self._drain_deferred_deletes()

        if captured_warnings is not None:
            self.assertEqual(captured_warnings, [])

        bridge.close()
        bridge.deleteLater()
        self._drain_deferred_deletes()

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
            self._dispose_qml(bridge, engine, root=main)

    def test_fullscreen_shortcut_uses_standard_key_and_invokes_controller(self):
        _app, bridge, controller, engine, main = self._load_main()
        try:
            main.show()
            main.requestActivate()
            QTest.qWait(50)
            self.qapp.processEvents()

            standard = main.findChild(QObject, "standardFullScreenShortcut")
            fallback = main.findChild(QObject, "fallbackFullScreenShortcut")
            self.assertIsNotNone(standard)
            self.assertIsNotNone(fallback)
            self.assertEqual(
                standard.property("context"), Qt.ShortcutContext.WindowShortcut
            )
            self.assertEqual(
                fallback.property("context"), Qt.ShortcutContext.WindowShortcut
            )

            bindings = QKeySequence.keyBindings(QKeySequence.StandardKey.FullScreen)
            standard_available = bool(standard.property("nativeText"))
            fallback_sequence = QKeySequence(
                "Ctrl+Meta+F" if sys.platform == "darwin" else "F11"
            )
            if standard_available:
                self.assertTrue(standard.property("enabled"))
                self.assertFalse(fallback.property("enabled"))
                self.assertGreaterEqual(len(bindings), 1)
                QTest.keySequence(main, bindings[0])
            else:
                self.assertFalse(standard.property("enabled"))
                self.assertTrue(fallback.property("enabled"))
                QTest.keySequence(main, fallback_sequence)
            self.qapp.processEvents()
            self.assertEqual(controller.action, "toggleFullScreen")

            if standard_available:
                controller.action = ""
                self.assertTrue(standard.setProperty("sequences", []))
                self.qapp.processEvents()
                self.assertFalse(standard.property("enabled"))
                self.assertTrue(fallback.property("enabled"))
                QTest.keySequence(main, fallback_sequence)
                self.qapp.processEvents()
                self.assertEqual(controller.action, "toggleFullScreen")
        finally:
            self._dispose_qml(bridge, engine, root=main)

    def test_window_controls_follow_platform_visual_focus_order(self):
        _app, bridge, _controller, engine, main = self._load_main()
        try:
            main.show()
            for _ in range(20):
                self.qapp.processEvents()

            chrome = main.findChild(QObject, "windowChrome")
            controls = {
                "minimize": main.findChild(QQuickItem, "minimizeWindowButton"),
                "maximize": main.findChild(QQuickItem, "maximizeWindowButton"),
                "close": main.findChild(QQuickItem, "closeWindowButton"),
            }
            self.assertTrue(all(control is not None for control in controls.values()))
            expected = (
                ["close", "minimize", "maximize"]
                if bool(chrome.property("controlsOnLeft"))
                else ["minimize", "maximize", "close"]
            )

            for current_name, next_name in zip(expected, expected[1:]):
                current = controls[current_name]
                following = current.nextItemInFocusChain(True)
                self.assertEqual(following.objectName(), controls[next_name].objectName())
                previous = controls[next_name].nextItemInFocusChain(False)
                self.assertEqual(previous.objectName(), current.objectName())

            first = controls[expected[0]]
            last = controls[expected[-1]]
            before = first.nextItemInFocusChain(False)
            after = last.nextItemInFocusChain(True)
            control_names = {control.objectName() for control in controls.values()}
            self.assertNotIn(before.objectName(), control_names)
            self.assertNotIn(after.objectName(), control_names)
            self.assertTrue(before.isVisible())
            self.assertTrue(after.isVisible())
            self.assertEqual(
                before.nextItemInFocusChain(True).objectName(), first.objectName()
            )
            self.assertEqual(
                after.nextItemInFocusChain(False).objectName(), last.objectName()
            )
        finally:
            self._dispose_qml(bridge, engine, root=main)

    def test_main_visibility_handler_and_runtime_load_are_warning_free(self):
        source = (self.qml / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("onVisibilityChanged: function()", source)
        self.assertIn("root.visibility === Window.Hidden", source)
        self.assertNotRegex(source, r"\bif\s*\(\s*visibility\s*===")

        _app, bridge, _controller, engine, main = self._load_main()
        try:
            main.show()
            self.qapp.processEvents()
            main.hide()
            self.qapp.processEvents()
        finally:
            self._dispose_qml(bridge, engine, root=main)

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
            self._dispose_qml(bridge, engine, root=main)

    def test_missing_native_controller_keeps_only_the_system_titlebar(self):
        app = _App()
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        main = None
        try:
            engine.load(QUrl.fromLocalFile(str(self.qml / "Main.qml")))
            self.qapp.processEvents()
            self.assertEqual(len(engine.rootObjects()), 1, warnings)
            self.assertEqual(warnings, [])
            main = engine.rootObjects()[0]
            chrome = main.findChild(QObject, "windowChrome")
            self.assertIsNotNone(chrome)
            self.assertFalse(chrome.property("visible"))
            self.assertGreater(
                main.findChild(QObject, "pageContentSurface").height(), 0
            )
        finally:
            self._dispose_qml(
                bridge, engine, root=main, warnings=warnings
            )

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
            self._dispose_qml(bridge, engine, root=main)

    def test_os_high_contrast_shell_screenshot_overrides_saved_light_full_at_100_and_200_percent(self):
        class _SavedAppearanceApp(_App):
            def settings_snapshot(inner_self):
                settings = super().settings_snapshot()
                settings["ui"]["theme"] = "light"
                settings["ui"]["visual_effects"] = "full"
                return settings

        accessibility = {
            "system_high_contrast": True,
            "system_reduced_motion": False,
            "system_reduce_transparency": False,
        }
        for text_scale in (100, 200):
            with self.subTest(text_scale=text_scale):
                palette_component = None
                palette_probe = None
                with mock.patch(
                    "speakr.qt_ui._system_accessibility_preferences",
                    return_value=accessibility,
                ):
                    _app, bridge, _controller, engine, main = self._load_main(
                        app=_SavedAppearanceApp(text_scale=text_scale)
                    )
                try:
                    main.setWidth(640)
                    main.setHeight(520)
                    main.show()
                    for _ in range(20):
                        self.qapp.processEvents()

                    theme = main.findChild(QObject, "themeTokens")
                    backdrop = main.findChild(QQuickItem, "cosmicBackdrop")
                    quitting_overlay = main.findChild(QQuickItem, "quittingOverlay")
                    self.assertIsNotNone(theme)
                    self.assertIsNotNone(backdrop)
                    self.assertIsNotNone(quitting_overlay)
                    theme.setProperty(
                        "systemPaletteOverride",
                        {
                            "window": "#000000",
                            "windowText": "#FFFFFF",
                            "base": "#FFFFFF",
                            "text": "#000000",
                            "button": "#000000",
                            "buttonText": "#FFFFFF",
                            "highlight": "#FFD400",
                            "highlightedText": "#000000",
                        },
                    )
                    self.qapp.processEvents()

                    expected_root_palette = {
                        "window": theme.property("background"),
                        "windowText": theme.property("windowText"),
                        "base": theme.property("surface"),
                        "text": theme.property("text"),
                        "button": theme.property("surfaceRaised"),
                        "buttonText": theme.property("buttonText"),
                        "highlight": theme.property("accent"),
                        "highlightedText": theme.property("accentText"),
                    }
                    for role, expected in expected_root_palette.items():
                        expression = QQmlExpression(
                            engine.rootContext(), main, f"palette.{role}"
                        )
                        value, undefined = expression.evaluate()
                        self.assertFalse(undefined, role)
                        self.assertFalse(expression.hasError(), role)
                        self.assertEqual(QColor(value), QColor(expected), role)

                    palette_component = QQmlComponent(engine)
                    palette_component.setData(
                        b"""
import QtQuick
import QtQuick.Controls

Control {
    id: probe
    required property Item host
    parent: host
    z: 1000
    x: 8
    y: 8
    width: 224
    height: 48

    property color windowRole: palette.window
    property color windowTextRole: palette.windowText
    property color baseRole: palette.base
    property color textRole: palette.text
    property color buttonRole: palette.button
    property color buttonTextRole: palette.buttonText
    property color highlightRole: palette.highlight
    property color highlightedTextRole: palette.highlightedText

    contentItem: Row {
        spacing: 8

        Rectangle {
            objectName: "windowPairSurface"
            width: 48; height: 48; color: probe.windowRole
            Rectangle {
                objectName: "windowPairForeground"
                anchors.centerIn: parent
                width: 20; height: 20; color: probe.windowTextRole
            }
        }
        Rectangle {
            objectName: "basePairSurface"
            width: 48; height: 48; color: probe.baseRole
            Rectangle {
                objectName: "basePairForeground"
                anchors.centerIn: parent
                width: 20; height: 20; color: probe.textRole
            }
        }
        Rectangle {
            objectName: "buttonPairSurface"
            width: 48; height: 48; color: probe.buttonRole
            Rectangle {
                objectName: "buttonPairForeground"
                anchors.centerIn: parent
                width: 20; height: 20; color: probe.buttonTextRole
            }
        }
        Rectangle {
            objectName: "highlightPairSurface"
            width: 48; height: 48; color: probe.highlightRole
            Rectangle {
                objectName: "highlightPairForeground"
                anchors.centerIn: parent
                width: 20; height: 20; color: probe.highlightedTextRole
            }
        }
    }
}
""",
                        QUrl.fromLocalFile(str(self.qml / "PaletteProbe.qml")),
                    )
                    palette_probe = palette_component.createWithInitialProperties(
                        {"host": main.contentItem()}
                    )
                    self.assertIsNotNone(
                        palette_probe,
                        [
                            error.toString()
                            for error in palette_component.errors()
                        ],
                    )
                    self.qapp.processEvents()
                    rendered_pairs = main.grabWindow()
                    self.assertFalse(rendered_pairs.isNull())
                    ratio = rendered_pairs.devicePixelRatio()
                    for pair, background_role, foreground_role in (
                        ("windowPair", "window", "windowText"),
                        ("basePair", "base", "text"),
                        ("buttonPair", "button", "buttonText"),
                        ("highlightPair", "highlight", "highlightedText"),
                    ):
                        surface = palette_probe.findChild(
                            QQuickItem, f"{pair}Surface"
                        )
                        foreground = palette_probe.findChild(
                            QQuickItem, f"{pair}Foreground"
                        )
                        self.assertIsNotNone(surface)
                        self.assertIsNotNone(foreground)
                        surface_point = surface.mapToScene(
                            QPointF(4, surface.height() / 2)
                        )
                        foreground_point = foreground.mapToScene(
                            QPointF(
                                foreground.width() / 2,
                                foreground.height() / 2,
                            )
                        )
                        self.assertEqual(
                            rendered_pairs.pixelColor(
                                round(surface_point.x() * ratio),
                                round(surface_point.y() * ratio),
                            ),
                            QColor(expected_root_palette[background_role]),
                        )
                        self.assertEqual(
                            rendered_pairs.pixelColor(
                                round(foreground_point.x() * ratio),
                                round(foreground_point.y() * ratio),
                            ),
                            QColor(expected_root_palette[foreground_role]),
                        )
                    self.assertTrue(theme.property("systemHighContrastActive"))
                    self.assertTrue(theme.property("highContrast"))
                    self.assertFalse(theme.property("manualHighContrast"))
                    self.assertEqual(theme.property("effectTier"), "off")
                    self.assertEqual(QColor(main.property("color")).alpha(), 255)
                    self.assertEqual(
                        QColor(quitting_overlay.property("color")),
                        QColor(theme.property("surface")),
                    )
                    self.assertEqual(
                        QColor(quitting_overlay.property("color")).alpha(), 255
                    )
                    self.assertEqual(
                        sum(item.isVisible() for item in backdrop.childItems()), 1
                    )
                    for role in (
                        "shellSurface",
                        "navigationSurface",
                        "majorSurface",
                        "noticeSurface",
                        "contentSurface",
                    ):
                        self.assertAlmostEqual(
                            QColor(theme.property(role)).alphaF(), 1.0, places=5
                        )
                    for role in (
                        "atmosphereViolet",
                        "atmosphereCyan",
                        "atmosphereBlush",
                        "orbitLine",
                        "shadow",
                    ):
                        self.assertAlmostEqual(
                            QColor(theme.property(role)).alphaF(), 0.0, places=5
                        )

                    visual_items = self._visual_items(main.contentItem())
                    summary_surface = next(
                        (
                            item
                            for item in visual_items
                            if item.objectName() == "homeSummarySymbolSurface"
                        ),
                        None,
                    )
                    summary_glyph = next(
                        (
                            item
                            for item in visual_items
                            if item.objectName() == "homeSummarySymbolGlyph"
                        ),
                        None,
                    )
                    self.assertIsNotNone(summary_surface)
                    self.assertIsNotNone(summary_glyph)
                    self.assertEqual(
                        QColor(summary_surface.property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertEqual(
                        QColor(summary_surface.property("edgeColor")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertEqual(
                        QColor(summary_glyph.property("color")),
                        QColor(theme.property("accentText")),
                    )
                    chrome_nodes = [
                        item
                        for item in visual_items
                        if item.objectName() == "chromeSignalNode"
                    ]
                    self.assertEqual(len(chrome_nodes), 3)
                    for node in chrome_nodes:
                        self.assertEqual(
                            QColor(node.property("color")),
                            QColor(theme.property("text")),
                        )

                    bridge._quitting = True
                    bridge.quittingChanged.emit()
                    self.qapp.processEvents()
                    self.assertTrue(quitting_overlay.isVisible())
                    overlay_copy = [
                        item
                        for item in self._visual_items(quitting_overlay)
                        if item.property("text")
                    ]
                    self.assertGreaterEqual(len(overlay_copy), 2)
                    for label in overlay_copy:
                        self.assertEqual(
                            QColor(label.property("color")),
                            QColor(theme.property("text")),
                        )

                    image = main.grabWindow()
                    self.assertFalse(image.isNull())
                    self.assertGreaterEqual(image.width(), 640)
                    self.assertGreaterEqual(image.height(), 520)
                    self.assertEqual(image.pixelColor(0, 0).alpha(), 255)
                    self.assertEqual(
                        image.pixelColor(image.width() // 2, image.height() // 2).alpha(),
                        255,
                    )
                finally:
                    if palette_probe is not None:
                        palette_probe.setParentItem(None)
                        palette_probe.deleteLater()
                    if palette_component is not None:
                        palette_component.deleteLater()
                    bridge._quitting = False
                    bridge.quittingChanged.emit()
                    self._dispose_qml(bridge, engine, root=main)

    def test_navigation_and_practice_cancel_untimed_hotkey_capture(self):
        app = _CaptureApp()
        _app, bridge, _controller, engine, main = self._load_main(app=app)
        try:
            main.show()
            for _ in range(20):
                self.qapp.processEvents()
            shortcut = main.findChild(QObject, "homeBoundedShortcutButton")
            navigation = [
                item
                for item in self._visual_items(main.contentItem())
                if "NavigationButton" in item.metaObject().className()
                and item.isVisible()
            ]
            settings_nav = next(
                (item for item in navigation if item.property("text") == "Settings"),
                None,
            )
            home_nav = next(
                (item for item in navigation if item.property("text") == "Home"),
                None,
            )
            practice = main.findChild(QObject, "homeBoundedPracticeButton")
            for control in (shortcut, settings_nav, home_nav, practice):
                self.assertIsNotNone(control)

            self.assertTrue(QMetaObject.invokeMethod(shortcut, "click"))
            self.qapp.processEvents()
            self.assertTrue(bridge.capturingHotkey)
            self.assertTrue(QMetaObject.invokeMethod(settings_nav, "click"))
            self.qapp.processEvents()
            self.assertEqual(main.property("currentPage"), "settings")
            self.assertFalse(bridge.capturingHotkey)
            self.assertEqual(app.cancel_count, 1)

            self.assertTrue(QMetaObject.invokeMethod(home_nav, "click"))
            self.qapp.processEvents()
            self.assertEqual(main.property("currentPage"), "home")
            self.assertTrue(QMetaObject.invokeMethod(shortcut, "click"))
            self.qapp.processEvents()
            self.assertTrue(bridge.capturingHotkey)
            self.assertTrue(QMetaObject.invokeMethod(practice, "click"))
            self.qapp.processEvents()
            self.assertEqual(main.property("currentPage"), "practice")
            self.assertFalse(bridge.capturingHotkey)
            self.assertEqual(app.cancel_count, 2)
        finally:
            bridge.cancelHotkeyCapture()
            self._dispose_qml(bridge, engine, root=main)

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
            self._dispose_qml(
                bridge,
                engine,
                root=main,
                components=(component,),
                warnings=warnings,
            )

    def test_home_reflows_at_minimum_size_and_200_percent_text(self):
        _app, bridge, _controller, engine, main = self._load_main(text_scale=200)
        try:
            main.show()
            main.setWidth(640)
            main.setHeight(520)
            for _ in range(50):
                self.qapp.processEvents()
            self.assertEqual(main.property("topNavigationColumns"), 2)
            self.assertEqual(main.property("topNavigationRows"), 3)
            content = main.findChild(QQuickItem, "pageContentSurface")
            home = main.findChild(QQuickItem, "homePage")
            viewport = main.findChild(QQuickItem, "homeBoundedViewport")
            hero = main.findChild(QQuickItem, "homeBoundedReadinessHero")
            switch = main.findChild(QObject, "dictationSwitch")
            summary_repeater = main.findChild(QObject, "summaryRepeater")
            self.assertIsNotNone(content)
            self.assertIsNotNone(home)
            self.assertIsNotNone(viewport)
            self.assertIsNotNone(hero)
            self.assertGreater(hero.width(), 0)
            self.assertGreater(hero.height(), 0)
            self.assertGreaterEqual(switch.width(), 44)
            self.assertIsNotNone(summary_repeater)
            self.assertEqual(summary_repeater.property("count"), 4)

            content_origin = content.mapToScene(QPointF(0, 0))
            content_left = content_origin.x()
            content_right = content_left + content.width()
            self.assertLessEqual(
                float(viewport.property("contentWidth")), viewport.width() + 0.5
            )

            bounded = [
                item
                for item in self._visual_items(home)
                if item.isVisible()
                and item.width() > 0
                and item.height() > 0
            ]
            self.assertIn(switch, bounded)
            self.assertGreaterEqual(len(bounded), 40)
            for item in bounded:
                with self.subTest(item=item.objectName() or item.metaObject().className()):
                    origin = item.mapToScene(QPointF(0, 0))
                    self.assertGreaterEqual(origin.x(), content_left - 0.5)
                    self.assertLessEqual(
                        origin.x() + item.width(), content_right + 0.5
                    )
        finally:
            self._dispose_qml(bridge, engine, root=main)

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
