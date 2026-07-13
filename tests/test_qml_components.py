from __future__ import annotations

import inspect
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QAccessible, QColor
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from speakr import qt_ui
from tests.qml_lifecycle import qml_test_application


class QmlComponentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = qml_test_application()
        cls.qml = (
            Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        )

    def _component(self, engine, name):
        return QQmlComponent(engine, QUrl.fromLocalFile(str(self.qml / name)))

    def _theme(self, engine):
        component = self._component(engine, "Theme.qml")
        theme = component.create()
        self.assertIsNotNone(
            theme, [error.toString() for error in component.errors()]
        )
        theme.setParent(engine)
        return theme

    @staticmethod
    def _visual_items(item):
        result = []
        pending = list(item.childItems())
        while pending:
            child = pending.pop()
            result.append(child)
            pending.extend(child.childItems())
        return result

    def _run_font_probe(self, qpa):
        script = textwrap.dedent(
            f"""
            from PySide6.QtCore import QObject, QUrl
            from PySide6.QtGui import QFontInfo
            from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
            from PySide6.QtQuickControls2 import QQuickStyle
            from PySide6.QtWidgets import QApplication
            from speakr.qt_ui import _normalize_system_ui_font

            QQuickStyle.setStyle("Basic")
            application = QApplication([])
            assert application.platformName() == {qpa!r}
            assert _normalize_system_ui_font(application)
            engine = QQmlApplicationEngine()
            component = QQmlComponent(
                engine,
                QUrl.fromLocalFile({str(self.qml / 'Theme.qml')!r}),
            )
            theme = component.create()
            assert theme is not None
            button_component = QQmlComponent(
                engine,
                QUrl.fromLocalFile({str(self.qml / 'QuietButton.qml')!r}),
            )
            button = button_component.createWithInitialProperties(
                {{"tokens": theme, "text": "Speakr"}}
            )
            assert button is not None
            label = button.findChild(QObject, "buttonLabel")
            assert label is not None
            application.processEvents()
            values = [
                str(theme.property("fontFamily")).strip(),
                QFontInfo(label.property("font")).family().strip(),
                application.font().family().strip(),
            ]
            print("FONT_PROBE=" + "\\t".join(values))

            button.deleteLater()
            button_component.deleteLater()
            theme.deleteLater()
            component.deleteLater()
            engine.deleteLater()
            application.processEvents()
            """
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = qpa
        environment["QT_QUICK_BACKEND"] = "software"
        environment["QSG_RHI_BACKEND"] = "software"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.qml.parents[2],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        combined = result.stdout + "\n" + result.stderr
        self.assertEqual(result.returncode, 0, combined)
        self.assertEqual(
            result.stderr.strip(),
            "",
            "The production font probe emitted a QML/Qt runtime diagnostic:\n"
            + combined,
        )

        marker = "FONT_PROBE="
        encoded = next(
            (
                line.removeprefix(marker)
                for line in result.stdout.splitlines()
                if line.startswith(marker)
            ),
            "",
        )
        values = encoded.split("\t")
        self.assertEqual(len(values), 3, combined)
        self.assertEqual(len(set(values)), 1, values)
        self.assertNotIn(
            values[0].casefold(),
            {"", "sans serif", "serif", "monospace"},
        )
        return values[0]

    @staticmethod
    def _hex(value):
        return QColor(value).name(QColor.NameFormat.HexRgb).upper()

    @staticmethod
    def _luminance(value):
        color = QColor(value)
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    @classmethod
    def _contrast(cls, first, second):
        left, right = cls._luminance(first), cls._luminance(second)
        return (max(left, right) + 0.05) / (min(left, right) + 0.05)

    def test_luminous_orbit_palette_and_compatibility_aliases_are_exact(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        try:
            expected = {
                "light": {
                    "canvas": "#EDF1FA",
                    "surfaceStrong": "#F8FAFF",
                    "textPrimary": "#17182A",
                    "textSecondary": "#55596D",
                    "borderMeaningful": "#747A92",
                    "accent": "#6657D8",
                    "accentText": "#F8FAFF",
                },
                "dark": {
                    "canvas": "#090B18",
                    "surfaceStrong": "#20243A",
                    "textPrimary": "#F2F3FC",
                    "textSecondary": "#B4B7C9",
                    "borderMeaningful": "#737A99",
                    "accent": "#A89AFB",
                    "accentText": "#17182A",
                },
            }
            aliases = {
                "background": "canvas",
                "surface": "surfaceStrong",
                "text": "textPrimary",
                "mutedText": "textSecondary",
                "border": "borderMeaningful",
            }

            for mode, palette in expected.items():
                theme.setProperty("mode", mode)
                self.qapp.processEvents()
                for role, value in palette.items():
                    self.assertEqual(self._hex(theme.property(role)), value, role)
                for alias, source in aliases.items():
                    self.assertEqual(
                        QColor(theme.property(alias)), QColor(theme.property(source))
                    )
                self.assertAlmostEqual(
                    QColor(theme.property("surface")).alphaF(), 1.0, places=5
                )
        finally:
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_system_high_contrast_overrides_every_saved_theme_and_effect_choice(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        try:
            palette = theme.findChild(QObject, "themeSystemPalette")
            self.assertIsNotNone(palette)
            role_map = {
                "canvas": "window",
                "windowText": "windowText",
                "surfaceStrong": "base",
                "surfaceRaised": "button",
                "buttonText": "buttonText",
                "textPrimary": "text",
                "textSecondary": "text",
                "borderMeaningful": "text",
                "accent": "highlight",
                "accentText": "highlightedText",
                "accentForeground": "text",
                "success": "text",
                "successSurface": "base",
                "warning": "text",
                "warningSurface": "base",
                "danger": "text",
                "dangerSurface": "base",
                "info": "text",
                "infoSurface": "base",
                "focus": "text",
                "disabledControlSurface": "button",
                "disabledControlText": "buttonText",
                "disabledButtonText": "buttonText",
                "disabledText": "text",
            }
            material_roles = (
                "shellSurface",
                "navigationSurface",
                "majorSurface",
                "noticeSurface",
                "contentSurface",
                "hudSurface",
            )
            for mode in ("system", "light", "dark", "high_contrast"):
                for effects in ("system", "full", "reduced", "off"):
                    with self.subTest(mode=mode, effects=effects):
                        theme.setProperty("mode", mode)
                        theme.setProperty("visualEffects", effects)
                        theme.setProperty("systemHighContrast", True)
                        theme.setProperty("systemReduceTransparency", False)
                        theme.setProperty("softwareRenderer", False)
                        self.qapp.processEvents()

                        self.assertTrue(theme.property("systemHighContrastActive"))
                        self.assertTrue(theme.property("highContrast"))
                        self.assertFalse(theme.property("manualHighContrast"))
                        self.assertEqual(theme.property("effectTier"), "off")
                        for token_role, system_role in role_map.items():
                            self.assertEqual(
                                QColor(theme.property(token_role)),
                                QColor(palette.property(system_role)),
                                token_role,
                            )
                        for role in material_roles:
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
        finally:
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_divergent_system_palette_uses_canonical_pairs_in_rendered_components(self):
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
        for scale in (1.0, 2.0):
            with self.subTest(scale=scale):
                engine = QQmlApplicationEngine()
                theme = self._theme(engine)
                components = []
                objects = []
                window = QQuickWindow()
                try:
                    theme.setProperty("mode", "dark")
                    theme.setProperty("systemPaletteOverride", divergent)
                    theme.setProperty("systemHighContrast", True)
                    theme.setProperty("visualEffects", "full")
                    theme.setProperty("textScale", scale)
                    theme.setProperty("reduceMotion", True)
                    self.qapp.processEvents()

                    def create(name, properties):
                        component = self._component(engine, name)
                        components.append(component)
                        item = component.createWithInitialProperties(
                            {"tokens": theme, **properties}
                        )
                        self.assertIsNotNone(
                            item, [error.toString() for error in component.errors()]
                        )
                        objects.append(item)
                        item.setParentItem(window.contentItem())
                        return item

                    primary = create(
                        "QuietButton.qml",
                        {"kind": "primary", "text": "Continue"},
                    )
                    primary.setX(32)
                    primary.setY(32)
                    primary.setWidth(220)
                    primary.setHeight(primary.implicitHeight())

                    disabled = create(
                        "QuietButton.qml",
                        {"enabled": False, "text": "Unavailable"},
                    )
                    disabled.setX(290)
                    disabled.setY(32)
                    disabled.setWidth(220)
                    disabled.setHeight(disabled.implicitHeight())

                    selected_nav = create(
                        "NavigationButton.qml",
                        {"selected": True, "text": "Home"},
                    )
                    selected_nav.setX(32)
                    selected_nav.setY(130)
                    selected_nav.setWidth(220)
                    selected_nav.setHeight(selected_nav.implicitHeight())

                    notices = []
                    for index, kind in enumerate(("warning", "danger")):
                        notice = create(
                            "InlineNotice.qml",
                            {
                                "kind": kind,
                                "title": kind.title(),
                                "message": "Local recovery remains available.",
                            },
                        )
                        notice.setX(32 + index * 330)
                        notice.setY(230)
                        notice.setWidth(300)
                        notice.setHeight(notice.implicitHeight())
                        notices.append(notice)

                    status = create(
                        "StatusOrb.qml",
                        {"statusKind": "danger", "label": "Needs attention"},
                    )
                    status.setX(290)
                    status.setY(130)
                    status.setWidth(260)
                    status.setHeight(status.implicitHeight())

                    disabled_switch = create(
                        "QuietSwitch.qml",
                        {"checked": True, "enabled": False},
                    )
                    disabled_switch.setX(550)
                    disabled_switch.setY(32)
                    disabled_switch.setWidth(disabled_switch.implicitWidth())
                    disabled_switch.setHeight(disabled_switch.implicitHeight())

                    combo = create(
                        "QuietComboBox.qml",
                        {"model": ["System"], "currentIndex": 0},
                    )
                    combo.setX(550)
                    combo.setY(105)
                    combo.setWidth(220)
                    combo.setHeight(combo.implicitHeight())

                    chrome = create("WindowChrome.qml", {})
                    chrome.setX(32)
                    chrome.setY(390)
                    chrome.setWidth(780)
                    chrome.setHeight(chrome.implicitHeight())

                    signal_path = create(
                        "SignalPath.qml",
                        {"activeStage": 2},
                    )
                    signal_path.setX(32)
                    signal_path.setY(500)
                    signal_path.setWidth(640)
                    signal_path.setHeight(signal_path.implicitHeight())

                    setting_row = create(
                        "SettingRow.qml",
                        {
                            "showCategory": True,
                            "category": "Dictation",
                            "label": "Dictation mode",
                            "description": "Choose how capture begins and ends.",
                            "currentValue": False,
                        },
                    )
                    setting_row.setX(32)
                    setting_row.setY(610)
                    setting_row.setWidth(780)
                    setting_row.setHeight(setting_row.implicitHeight())

                    window.setColor(theme.property("surface"))
                    window.setWidth(900)
                    window.setHeight(820)
                    window.show()
                    window.requestActivate()
                    self.qapp.processEvents()
                    primary.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                    QTest.mouseMove(
                        window,
                        QPoint(
                            round(combo.x() + combo.width() / 2),
                            round(combo.y() + combo.height() / 2),
                        ),
                    )
                    self.qapp.processEvents()

                    self.assertTrue(theme.property("systemHighContrastActive"))
                    self.assertEqual(theme.property("effectTier"), "off")
                    self.assertEqual(self._hex(theme.property("canvas")), "#000000")
                    self.assertEqual(
                        self._hex(theme.property("windowText")), "#FFFFFF"
                    )
                    self.assertEqual(self._hex(theme.property("surface")), "#FFFFFF")
                    self.assertEqual(self._hex(theme.property("text")), "#000000")
                    self.assertEqual(self._hex(theme.property("buttonText")), "#FFFFFF")
                    self.assertEqual(
                        self._hex(theme.property("accentForeground")), "#000000"
                    )

                    self.assertGreaterEqual(
                        self._contrast(
                            theme.property("textPrimary"), theme.property("surface")
                        ),
                        7.0,
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            theme.property("borderMeaningful"),
                            theme.property("surface"),
                        ),
                        3.0,
                    )
                    for notice in notices:
                        self.assertEqual(
                            QColor(notice.property("color")),
                            QColor(theme.property("surface")),
                        )
                        self.assertGreaterEqual(
                            self._contrast(
                                notice.property("semanticColor"),
                                notice.property("color"),
                            ),
                            7.0,
                        )
                        notice_icon = notice.findChild(QObject, "noticeIcon")
                        self.assertEqual(
                            QColor(notice_icon.property("edgeColor")),
                            QColor(theme.property("accentText")),
                        )

                    disabled_background = disabled.findChild(
                        QObject, "buttonBackground"
                    )
                    disabled_label = disabled.findChild(QObject, "buttonLabel")
                    self.assertEqual(
                        self._hex(disabled_background.property("color")), "#000000"
                    )
                    self.assertEqual(
                        self._hex(disabled_label.property("color")), "#FFFFFF"
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            disabled_label.property("color"),
                            disabled_background.property("color"),
                        ),
                        7.0,
                    )
                    self.assertEqual(
                        QColor(disabled.property("resolvedBorderColor")),
                        QColor(theme.property("buttonText")),
                    )

                    primary_background = primary.findChild(
                        QObject, "buttonBackground"
                    )
                    primary_label = primary.findChild(QObject, "buttonLabel")
                    self.assertEqual(
                        self._hex(primary_background.property("color")), "#FFD400"
                    )
                    self.assertEqual(
                        self._hex(primary_label.property("color")), "#000000"
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            primary_label.property("color"),
                            primary_background.property("color"),
                        ),
                        7.0,
                    )
                    self.assertEqual(
                        QColor(primary.property("resolvedBorderColor")),
                        QColor(theme.property("accentText")),
                    )

                    nav_background = selected_nav.findChild(
                        QObject, "navigationBackground"
                    )
                    nav_label = next(
                        item
                        for item in self._visual_items(selected_nav)
                        if item.property("text") == "Home"
                    )
                    self.assertEqual(self._hex(nav_background.property("color")), "#FFD400")
                    self.assertEqual(
                        QColor(nav_background.property("edgeColor")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertEqual(self._hex(nav_label.property("color")), "#000000")
                    nav_marker = selected_nav.findChild(
                        QObject, "navigationSelectionMarker"
                    )
                    self.assertIsNotNone(nav_marker)
                    self.assertEqual(
                        QColor(nav_marker.property("color")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            nav_label.property("color"),
                            nav_background.property("color"),
                        ),
                        7.0,
                    )

                    status_badge = status.findChild(QObject, "statusOrbBadge")
                    status_glyph = status.findChild(QObject, "statusOrbGlyph")
                    self.assertEqual(
                        QColor(status_badge.property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertEqual(
                        QColor(status_badge.property("edgeColor")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            status_glyph.property("color"),
                            status_badge.property("color"),
                        ),
                        7.0,
                    )

                    switch_track = disabled_switch.findChild(
                        QObject, "switchTrack"
                    )
                    switch_knob = disabled_switch.findChild(
                        QObject, "switchKnob"
                    )
                    self.assertEqual(
                        QColor(switch_track.property("color")),
                        QColor(theme.property("disabledControlSurface")),
                    )
                    self.assertEqual(
                        QColor(switch_knob.property("color")),
                        QColor(theme.property("buttonText")),
                    )
                    self.assertEqual(
                        QColor(
                            disabled_switch.property("resolvedTrackBorderColor")
                        ),
                        QColor(theme.property("buttonText")),
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            switch_knob.property("color"),
                            switch_track.property("color"),
                        ),
                        7.0,
                    )

                    combo_background = combo.findChild(QObject, "comboBackground")
                    combo_label = combo.findChild(QObject, "comboSelectedLabel")
                    self.assertTrue(bool(combo.property("usesHighlightSurface")))
                    self.assertEqual(
                        QColor(combo_background.property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertEqual(
                        QColor(combo_label.property("color")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertEqual(
                        QColor(combo.property("resolvedBorderColor")),
                        QColor(theme.property("accentText")),
                    )

                    chrome_nodes = [
                        item
                        for item in self._visual_items(chrome)
                        if item.objectName() == "chromeSignalNode"
                    ]
                    self.assertEqual(len(chrome_nodes), 3)
                    for node in chrome_nodes:
                        self.assertEqual(
                            QColor(node.property("color")),
                            QColor(theme.property("text")),
                        )

                    category_label = setting_row.findChild(
                        QObject, "settingCategoryLabel"
                    )
                    self.assertEqual(
                        QColor(category_label.property("color")),
                        QColor(theme.property("text")),
                    )

                    connector_surfaces = sorted(
                        (
                            item
                            for item in self._visual_items(signal_path)
                            if item.objectName() == "signalConnector"
                        ),
                        key=lambda item: item.mapToScene(QPointF(0, 0)).x(),
                    )
                    connector_fills = [
                        item
                        for item in self._visual_items(signal_path)
                        if item.objectName() == "signalConnectorFill"
                    ]
                    self.assertEqual(len(connector_surfaces), 2)
                    self.assertEqual(len(connector_fills), 2)
                    for connector in connector_surfaces:
                        self.assertEqual(
                            QColor(connector.property("color")),
                            QColor(theme.property("surface")),
                        )
                        self.assertEqual(
                            QColor(connector.property("edgeColor")),
                            QColor(theme.property("text")),
                        )
                    for fill in connector_fills:
                        self.assertEqual(
                            QColor(fill.property("color")),
                            QColor(theme.property("text")),
                        )

                    signal_surfaces = sorted(
                        (
                            item
                            for item in self._visual_items(signal_path)
                            if item.objectName() == "signalNodeSurface"
                        ),
                        key=lambda item: item.mapToScene(QPointF(0, 0)).x(),
                    )
                    signal_glyphs = sorted(
                        (
                            item
                            for item in self._visual_items(signal_path)
                            if item.objectName() == "signalNodeGlyph"
                        ),
                        key=lambda item: item.mapToScene(QPointF(0, 0)).x(),
                    )
                    self.assertEqual(len(signal_surfaces), 3)
                    self.assertEqual(len(signal_glyphs), 3)
                    self.assertEqual(
                        QColor(signal_surfaces[0].property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertEqual(
                        QColor(signal_surfaces[0].property("edgeColor")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertEqual(
                        QColor(signal_glyphs[0].property("color")),
                        QColor(theme.property("accentText")),
                    )
                    self.assertEqual(
                        QColor(signal_surfaces[1].property("color")),
                        QColor(theme.property("surface")),
                    )
                    self.assertEqual(
                        QColor(signal_surfaces[1].property("edgeColor")),
                        QColor(theme.property("text")),
                    )
                    self.assertEqual(
                        QColor(signal_glyphs[1].property("color")),
                        QColor(theme.property("text")),
                    )

                    focus_rings = [
                        item
                        for item in self._visual_items(primary)
                        if "FocusRing" in item.metaObject().className()
                    ]
                    self.assertEqual(len(focus_rings), 1)
                    self.assertTrue(focus_rings[0].isVisible())
                    self.assertGreaterEqual(
                        self._contrast(
                            theme.property("focus"), window.color()
                        ),
                        3.0,
                    )
                    image = window.grabWindow()
                    self.assertFalse(image.isNull())
                    ratio = image.devicePixelRatio()
                    connector_centers = []
                    for connector in connector_surfaces:
                        center = connector.mapToScene(
                            QPointF(connector.width() / 2, connector.height() / 2)
                        )
                        connector_centers.append(
                            image.pixelColor(
                                round(center.x() * ratio),
                                round(center.y() * ratio),
                            )
                        )
                    self.assertEqual(
                        self._hex(connector_centers[0]),
                        self._hex(theme.property("text")),
                    )
                    self.assertEqual(
                        self._hex(connector_centers[1]),
                        self._hex(theme.property("surface")),
                    )
                    clearance = int(theme.property("focusWidth")) + int(
                        theme.property("focusClearance")
                    )
                    focus_x = round(
                        (primary.x() + primary.width() / 2) * ratio
                    )
                    focus_y = round((primary.y() - clearance + 1) * ratio)
                    rendered_focus = image.pixelColor(focus_x, focus_y)
                    self.assertEqual(
                        self._hex(rendered_focus), self._hex(theme.property("focus"))
                    )
                    self.assertGreaterEqual(
                        self._contrast(rendered_focus, window.color()), 3.0
                    )
                finally:
                    window.close()
                    for item in objects:
                        item.setParentItem(None)
                        item.deleteLater()
                    for component in components:
                        component.deleteLater()
                    theme.deleteLater()
                    engine.deleteLater()
                    self.qapp.processEvents()

    def test_manual_high_contrast_roles_are_deterministic_and_audited(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        try:
            theme.setProperty("mode", "high_contrast")
            theme.setProperty("systemHighContrast", False)
            self.qapp.processEvents()
            self.assertTrue(theme.property("manualHighContrast"))
            self.assertFalse(theme.property("systemHighContrastActive"))

            expected = {
                "canvas": "#000000",
                "windowText": "#FFFFFF",
                "surfaceStrong": "#000000",
                "surfaceRaised": "#303030",
                "buttonText": "#FFFFFF",
                "textPrimary": "#FFFFFF",
                "textSecondary": "#E6E6E6",
                "borderMeaningful": "#00E5FF",
                "accent": "#FFD400",
                "accentText": "#000000",
                "accentForeground": "#FFD400",
                "accentHoverSurface": "#FFE466",
                "accentPressedSurface": "#E6B800",
                "success": "#00E676",
                "warning": "#FFD400",
                "danger": "#FF7294",
                "info": "#00D4FF",
                "disabledControlSurface": "#303030",
                "disabledControlText": "#D0D0D0",
                "disabledButtonText": "#B8B8B8",
                "disabledText": "#B8B8B8",
            }
            for role, value in expected.items():
                self.assertEqual(self._hex(theme.property(role)), value, role)
                self.assertAlmostEqual(
                    QColor(theme.property(role)).alphaF(), 1.0, places=5
                )

            surface = theme.property("surfaceStrong")
            self.assertGreaterEqual(
                self._contrast(theme.property("textPrimary"), surface), 7.0
            )
            self.assertGreaterEqual(
                self._contrast(theme.property("textSecondary"), surface), 4.5
            )
            for role in ("borderMeaningful", "focus"):
                self.assertGreaterEqual(
                    self._contrast(theme.property(role), surface), 3.0, role
                )
            for foreground, background in (
                ("accentText", "accent"),
                ("accentText", "accentHoverSurface"),
                ("accentText", "accentPressedSurface"),
                ("success", "successSurface"),
                ("warning", "warningSurface"),
                ("danger", "dangerSurface"),
                ("info", "infoSurface"),
            ):
                self.assertGreaterEqual(
                    self._contrast(
                        theme.property(foreground), theme.property(background)
                    ),
                    7.0,
                    f"{foreground}/{background}",
                )
            for foreground in (
                "disabledControlText",
                "disabledButtonText",
                "disabledText",
            ):
                self.assertGreaterEqual(
                    self._contrast(
                        theme.property(foreground),
                        theme.property("disabledControlSurface"),
                    ),
                    4.5,
                    foreground,
                )
        finally:
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_theme_uses_normalized_system_font_without_platform_literals(self):
        source = (self.qml / "Theme.qml").read_text(encoding="utf-8")
        normalizer = inspect.getsource(qt_ui._normalize_system_ui_font)
        self.assertIn(
            "readonly property string fontFamily: Application.font.family",
            source,
        )
        self.assertNotIn("FontInfo", source)
        self.assertNotIn("Qt.platform", source)
        self.assertNotIn("sys.platform", normalizer)
        for private_or_literal_family in (
            "SF Pro",
            "Segoe UI",
            ".AppleSystemUIFont",
        ):
            self.assertNotIn(private_or_literal_family, source)
            self.assertNotIn(private_or_literal_family, normalizer)

        startup = inspect.getsource(qt_ui.run_native_ui)
        self.assertLess(
            startup.index("_normalize_system_ui_font"),
            startup.index("QQmlApplicationEngine"),
        )

    @unittest.skipUnless(sys.platform == "win32", "native Windows font proof")
    def test_windows_native_qpa_resolves_system_font_to_segoe_ui(self):
        self.assertEqual(self._run_font_probe("windows"), "Segoe UI")

    @unittest.skipUnless(sys.platform == "darwin", "hosted macOS font proof")
    def test_macos_hosted_probe_uses_system_font_without_alias_warning(self):
        self.assertTrue(self._run_font_probe("offscreen"))

    def test_effect_resolution_and_material_opacity_are_deterministic(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        try:
            theme.setProperty("mode", "dark")
            theme.setProperty("visualEffects", "full")
            self.qapp.processEvents()
            self.assertEqual(theme.property("effectTier"), "full")
            for role, alpha in (
                ("shellSurface", 0.72),
                ("navigationSurface", 0.76),
                ("majorSurface", 0.84),
                ("noticeSurface", 0.88),
                ("contentSurface", 0.94),
                ("hudSurface", 1.0),
            ):
                self.assertAlmostEqual(
                    QColor(theme.property(role)).alphaF(), alpha, delta=0.005
                )

            theme.setProperty("systemReduceTransparency", True)
            self.qapp.processEvents()
            self.assertEqual(theme.property("effectTier"), "reduced")
            self.assertAlmostEqual(
                QColor(theme.property("shellSurface")).alphaF(), 0.94, delta=0.005
            )
            self.assertAlmostEqual(
                QColor(theme.property("contentSurface")).alphaF(), 1.0, places=5
            )

            theme.setProperty("systemReduceTransparency", False)
            theme.setProperty("softwareRenderer", True)
            self.qapp.processEvents()
            self.assertEqual(theme.property("effectTier"), "reduced")

            theme.setProperty("softwareRenderer", False)
            theme.setProperty("visualEffects", "off")
            self.qapp.processEvents()
            self.assertEqual(theme.property("effectTier"), "off")
            for role in (
                "shellSurface",
                "navigationSurface",
                "majorSurface",
                "noticeSurface",
                "contentSurface",
                "hudSurface",
            ):
                self.assertAlmostEqual(
                    QColor(theme.property(role)).alphaF(), 1.0, places=5
                )
            self.assertAlmostEqual(
                QColor(theme.property("atmosphereViolet")).alphaF(), 0.0, places=5
            )

            theme.setProperty("visualEffects", "full")
            theme.setProperty("mode", "high_contrast")
            self.qapp.processEvents()
            self.assertEqual(theme.property("effectTier"), "off")
            self.assertTrue(theme.property("highContrast"))
        finally:
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_radius_motion_and_focus_tokens_match_contract(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        try:
            self.assertEqual(theme.property("radiusControl"), 14)
            self.assertEqual(theme.property("radiusPanel"), 20)
            self.assertEqual(theme.property("radiusShell"), 28)
            self.assertEqual(theme.property("radius"), 14)
            self.assertEqual(theme.property("radiusLarge"), 20)
            self.assertEqual(theme.property("focusWidth"), 2)
            self.assertEqual(theme.property("focusClearance"), 2)
            self.assertEqual(theme.property("motionFast"), 100)
            self.assertEqual(theme.property("motionStandard"), 160)
            self.assertEqual(theme.property("motionEmphasis"), 220)
            self.assertEqual(theme.property("motionToggle"), 140)
            self.assertEqual(theme.property("motionDisclosure"), 120)
            self.assertEqual(theme.property("motionOnboarding"), 180)

            theme.setProperty("reduceMotion", True)
            self.qapp.processEvents()
            for token in (
                "motionFast",
                "motionStandard",
                "motionEmphasis",
                "motionHover",
                "motionToggle",
                "motionDisclosure",
                "motionStage",
                "motionOnboarding",
            ):
                self.assertEqual(theme.property(token), 0, token)
        finally:
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_new_primitives_load_without_warnings(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        theme = self._theme(engine)
        objects = []
        components = []
        try:
            for name in (
                "CosmicBackdrop.qml",
                "GlassSurface.qml",
                "FocusRing.qml",
                "StatusOrb.qml",
                "SectionHeading.qml",
                "InlineNotice.qml",
                "ChromeButton.qml",
            ):
                component = self._component(engine, name)
                components.append(component)
                item = component.createWithInitialProperties({"tokens": theme})
                self.assertIsNotNone(
                    item,
                    f"{name}: {[error.toString() for error in component.errors()]}",
                )
                objects.append(item)
            self.qapp.processEvents()
            self.assertEqual(warnings, [])
        finally:
            for item in objects:
                item.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_section_heading_exposes_heading_semantics(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        component = self._component(engine, "SectionHeading.qml")
        heading = component.createWithInitialProperties(
            {
                "tokens": theme,
                "title": "Microphone and language",
                "description": "Choose the local input and speech language.",
            }
        )
        self.assertIsNotNone(
            heading, [error.toString() for error in component.errors()]
        )
        try:
            self.qapp.processEvents()
            accessible = QAccessible.queryAccessibleInterface(heading)
            self.assertIsNotNone(accessible)
            self.assertEqual(accessible.role(), QAccessible.Role.Heading)
            self.assertEqual(
                accessible.text(QAccessible.Text.Name),
                "Microphone and language",
            )
            self.assertEqual(
                accessible.text(QAccessible.Text.Description),
                "Choose the local input and speech language.",
            )
        finally:
            heading.deleteLater()
            component.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_signal_path_accessibility_defaults_on_and_can_be_suppressed(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        component = self._component(engine, "SignalPath.qml")
        window = QQuickWindow()
        visible_path = component.createWithInitialProperties(
            {"tokens": theme}
        )
        suppressed_path = component.createWithInitialProperties(
            {"tokens": theme, "accessibilityEnabled": False}
        )
        self.assertIsNotNone(
            visible_path, [error.toString() for error in component.errors()]
        )
        self.assertIsNotNone(
            suppressed_path,
            [error.toString() for error in component.errors()],
        )
        try:
            window.setWidth(800)
            window.setHeight(160)
            visible_path.setParentItem(window.contentItem())
            visible_path.setWidth(360)
            visible_path.setHeight(60)
            suppressed_path.setParentItem(window.contentItem())
            suppressed_path.setX(400)
            suppressed_path.setWidth(360)
            suppressed_path.setHeight(60)
            window.show()
            self.qapp.processEvents()

            root_accessible = QAccessible.queryAccessibleInterface(window)
            self.assertIsNotNone(root_accessible)

            def descendants(interface):
                result = []
                for index in range(interface.childCount()):
                    child = interface.child(index)
                    result.append(child)
                    result.extend(descendants(child))
                return result

            accessible_items = descendants(root_accessible)
            processing_paths = [
                item
                for item in accessible_items
                if item.role() == QAccessible.Role.List
                and item.text(QAccessible.Text.Name) == "Processing stages"
            ]
            signal_nodes = [
                item
                for item in accessible_items
                if item.role() == QAccessible.Role.StaticText
                and item.text(QAccessible.Text.Name)
                in {"Transcribe", "Clean up", "Insert"}
            ]
            self.assertEqual(len(processing_paths), 1)
            self.assertEqual(len(signal_nodes), 3)
            self.assertTrue(visible_path.property("accessibilityEnabled"))
            self.assertFalse(suppressed_path.property("accessibilityEnabled"))
        finally:
            window.close()
            visible_path.setParentItem(None)
            suppressed_path.setParentItem(None)
            visible_path.deleteLater()
            suppressed_path.deleteLater()
            component.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_interactive_components_keep_44_pixel_targets(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        objects = []
        components = []
        try:
            for name in (
                "QuietButton.qml",
                "QuietSwitch.qml",
                "QuietTextField.qml",
                "QuietComboBox.qml",
                "NavigationButton.qml",
                "ChromeButton.qml",
            ):
                component = self._component(engine, name)
                components.append(component)
                item = component.createWithInitialProperties({"tokens": theme})
                self.assertIsNotNone(
                    item,
                    f"{name}: {[error.toString() for error in component.errors()]}",
                )
                objects.append(item)
                self.assertGreaterEqual(item.implicitHeight(), 44, name)
                self.assertGreaterEqual(item.implicitWidth(), 44, name)
        finally:
            for item in objects:
                item.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_combo_selected_values_reflow_at_supported_text_scales(self):
        values = ("Hold to speak", "Comfortable", "While dictating")
        for scale in (1.0, 1.5, 2.0):
            for selected_value in values:
                engine = QQmlApplicationEngine()
                window = QQuickWindow()
                window.setWidth(280)
                window.setHeight(400)
                window.show()
                theme = self._theme(engine)
                component = self._component(engine, "QuietComboBox.qml")
                combo = None
                try:
                    theme.setProperty("textScale", scale)
                    combo = component.createWithInitialProperties(
                        {
                            "tokens": theme,
                            "model": [selected_value],
                            "currentIndex": 0,
                            "accessibleName": "Setting choice",
                        }
                    )
                    self.assertIsNotNone(
                        combo,
                        [error.toString() for error in component.errors()],
                    )
                    combo.setParentItem(window.contentItem())
                    combo.setWidth(combo.implicitWidth())
                    combo.setHeight(300)
                    for _ in range(4):
                        self.qapp.processEvents()
                        combo.ensurePolished()
                    combo.setHeight(combo.implicitHeight())
                    for _ in range(4):
                        self.qapp.processEvents()
                        combo.ensurePolished()

                    selected_label = combo.findChild(
                        QObject, "comboSelectedLabel"
                    )
                    indicator = combo.findChild(QObject, "comboIndicator")
                    self.assertIsNotNone(selected_label)
                    self.assertIsNotNone(indicator)

                    epsilon = 0.5
                    self.assertGreaterEqual(
                        combo.height(), 44, (scale, selected_value)
                    )
                    self.assertEqual(combo.property("displayText"), selected_value)
                    self.assertEqual(selected_label.property("text"), selected_value)
                    self.assertFalse(
                        selected_label.property("truncated"),
                        (scale, selected_value),
                    )
                    self.assertLessEqual(
                        selected_label.property("contentWidth"),
                        selected_label.width() + epsilon,
                        (scale, selected_value),
                    )
                    self.assertLessEqual(
                        selected_label.property("contentHeight"),
                        selected_label.height() + epsilon,
                        (scale, selected_value),
                    )
                    self.assertLessEqual(
                        selected_label.x() + selected_label.width(),
                        indicator.x() + epsilon,
                        (scale, selected_value),
                    )

                    accessible = QAccessible.queryAccessibleInterface(combo)
                    self.assertIsNotNone(accessible)
                    self.assertIn(
                        selected_value,
                        accessible.text(QAccessible.Text.Description),
                        (scale, selected_value),
                    )
                finally:
                    if combo is not None:
                        combo.setParentItem(None)
                        combo.deleteLater()
                    window.close()
                    theme.deleteLater()
                    engine.deleteLater()
                    self.qapp.processEvents()

    def test_combo_popup_options_wrap_and_remain_scrollable(self):
        engine = QQmlApplicationEngine()
        window = QQuickWindow()
        window.setWidth(280)
        window.setHeight(520)
        window.show()
        theme = self._theme(engine)
        theme.setProperty("textScale", 2.0)
        harness_source = b"""
import QtQuick

Item {
    required property var tokens
    required property Item host
    parent: host
    width: 280
    height: 520
    property Item popupList: combo.popup.contentItem
    function openPopup() { combo.popup.open() }
    function closePopup() { combo.popup.close() }

    QuietComboBox {
        id: combo
        tokens: parent.tokens
        width: implicitWidth
        model: [
            "Hold to speak", "Comfortable", "While dictating",
            "Press to start and stop", "Always", "Off"
        ]
    }
}
"""
        component = QQmlComponent(engine)
        component.setData(
            harness_source,
            QUrl.fromLocalFile(str(self.qml / "ComboPopupHarness.qml")),
        )
        harness = component.createWithInitialProperties(
            {"tokens": theme, "host": window.contentItem()}
        )
        self.assertIsNotNone(
            harness, [error.toString() for error in component.errors()]
        )
        try:
            self.assertTrue(QMetaObject.invokeMethod(harness, "openPopup"))
            for _ in range(8):
                self.qapp.processEvents()
                harness.ensurePolished()

            popup_list = harness.property("popupList")
            self.assertIsNotNone(popup_list)
            self.assertEqual(popup_list.property("count"), 6)
            self.assertGreater(
                popup_list.property("contentHeight"), popup_list.height()
            )

            def descendants(item):
                result = []
                for child in item.childItems():
                    result.append(child)
                    result.extend(descendants(child))
                return result

            option_labels = [
                item
                for item in descendants(popup_list)
                if item.objectName() == "comboOptionLabel"
            ]
            self.assertGreaterEqual(len(option_labels), 1)
            for label in option_labels:
                self.assertFalse(label.property("truncated"), label.property("text"))
                self.assertLessEqual(
                    label.property("contentWidth"), label.width() + 0.5
                )
                self.assertLessEqual(
                    label.property("contentHeight"), label.height() + 0.5
                )

            self.assertLessEqual(
                popup_list.height(), theme.property("space32") * 10
            )
            self.assertTrue(QMetaObject.invokeMethod(harness, "closePopup"))
        finally:
            harness.setParentItem(None)
            harness.deleteLater()
            window.close()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_inline_notice_action_never_overflows_at_supported_text_scales(self):
        for scale in (1.0, 1.5, 2.0):
            engine = QQmlApplicationEngine()
            window = QQuickWindow()
            window.setWidth(300)
            window.setHeight(1000)
            window.show()
            theme = self._theme(engine)
            component = self._component(engine, "InlineNotice.qml")
            notice = None
            try:
                theme.setProperty("textScale", scale)
                notice = component.createWithInitialProperties(
                    {
                        "tokens": theme,
                        "title": "Microphone access needed",
                        "message": (
                            "Speakr needs microphone access before dictation can "
                            "start safely."
                        ),
                        "detail": "Nothing is sent off this device.",
                        "actionText": "Open microphone privacy settings",
                    }
                )
                self.assertIsNotNone(
                    notice,
                    [error.toString() for error in component.errors()],
                )
                notice.setParentItem(window.contentItem())
                notice.setWidth(280)
                notice.setHeight(900)
                for _ in range(4):
                    self.qapp.processEvents()
                    notice.ensurePolished()
                notice.setHeight(notice.implicitHeight())
                for _ in range(4):
                    self.qapp.processEvents()
                    notice.ensurePolished()

                layout = notice.findChild(QObject, "noticeLayout")
                text_column = notice.findChild(QObject, "noticeTextColumn")
                action = notice.findChild(QObject, "noticeAction")
                action_label = notice.findChild(QObject, "noticeActionLabel")
                icon = notice.findChild(QObject, "noticeIcon")
                self.assertIsNotNone(layout)
                self.assertIsNotNone(text_column)
                self.assertIsNotNone(action)
                self.assertIsNotNone(action_label)
                self.assertIsNotNone(icon)

                epsilon = 0.5
                self.assertGreaterEqual(action.x(), -epsilon, scale)
                self.assertLessEqual(
                    action.x() + action.width(), layout.width() + epsilon, scale
                )
                self.assertLessEqual(
                    action.y() + action.height(), layout.height() + epsilon, scale
                )
                self.assertGreaterEqual(text_column.x(), icon.width(), scale)
                self.assertLessEqual(
                    text_column.x() + text_column.width(),
                    layout.width() + epsilon,
                    scale,
                )
                self.assertGreaterEqual(
                    notice.height(), layout.y() + layout.height(), scale
                )
                self.assertEqual(
                    action_label.property("text"),
                    "Open microphone privacy settings",
                    scale,
                )
                self.assertFalse(action_label.property("truncated"), scale)
                self.assertLessEqual(
                    action_label.property("contentWidth"),
                    action_label.width() + epsilon,
                    scale,
                )
                self.assertLessEqual(
                    action_label.property("contentHeight"),
                    action_label.height() + epsilon,
                    scale,
                )
            finally:
                if notice is not None:
                    notice.setParentItem(None)
                    notice.deleteLater()
                window.close()
                theme.deleteLater()
                engine.deleteLater()
                self.qapp.processEvents()

    def test_high_contrast_highlight_glyphs_use_highlighted_text(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        components = []
        objects = []
        try:
            theme.setProperty("mode", "high_contrast")
            self.qapp.processEvents()
            self.assertTrue(theme.property("manualHighContrast"))
            self.assertEqual(self._hex(theme.property("accent")), "#FFD400")
            self.assertEqual(self._hex(theme.property("accentText")), "#000000")

            for name, badge_name, glyph_name in (
                ("InlineNotice.qml", "noticeIcon", "noticeIconGlyph"),
                ("StatusOrb.qml", "statusOrbBadge", "statusOrbGlyph"),
            ):
                component = self._component(engine, name)
                components.append(component)
                item = component.createWithInitialProperties({"tokens": theme})
                self.assertIsNotNone(
                    item, [error.toString() for error in component.errors()]
                )
                objects.append(item)
                badge = item.findChild(QObject, badge_name)
                glyph = item.findChild(QObject, glyph_name)
                self.assertEqual(
                    QColor(badge.property("color")), QColor(theme.property("accent"))
                )
                self.assertEqual(
                    QColor(glyph.property("color")),
                    QColor(theme.property("accentText")),
                )
        finally:
            for item in objects:
                item.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_manual_high_contrast_component_states_and_focus_render_at_100_and_200_percent(self):
        for scale in (1.0, 2.0):
            with self.subTest(scale=scale):
                engine = QQmlApplicationEngine()
                theme = self._theme(engine)
                components = []
                objects = []
                window = QQuickWindow()
                try:
                    theme.setProperty("mode", "high_contrast")
                    theme.setProperty("systemHighContrast", False)
                    theme.setProperty("textScale", scale)
                    theme.setProperty("reduceMotion", True)
                    self.qapp.processEvents()

                    def create(name, properties):
                        component = self._component(engine, name)
                        components.append(component)
                        item = component.createWithInitialProperties(
                            {"tokens": theme, **properties}
                        )
                        self.assertIsNotNone(
                            item, [error.toString() for error in component.errors()]
                        )
                        objects.append(item)
                        item.setParentItem(window.contentItem())
                        return item

                    primary = create(
                        "QuietButton.qml",
                        {"kind": "primary", "text": "Start Practice"},
                    )
                    primary.setX(32)
                    primary.setY(32)
                    primary.setWidth(220)
                    primary.setHeight(primary.implicitHeight())

                    selected_nav = create(
                        "NavigationButton.qml",
                        {"selected": True, "text": "Home"},
                    )
                    selected_nav.setX(32)
                    selected_nav.setY(120)
                    selected_nav.setWidth(220)
                    selected_nav.setHeight(selected_nav.implicitHeight())

                    checked_switch = create(
                        "QuietSwitch.qml", {"checked": True, "text": "On"}
                    )
                    checked_switch.setX(32)
                    checked_switch.setY(210)
                    checked_switch.setWidth(220)
                    checked_switch.setHeight(checked_switch.implicitHeight())

                    disabled = create(
                        "QuietButton.qml",
                        {"enabled": False, "text": "Unavailable"},
                    )
                    disabled.setX(280)
                    disabled.setY(32)
                    disabled.setWidth(220)
                    disabled.setHeight(disabled.implicitHeight())

                    semantic = []
                    for index, kind in enumerate(("success", "warning", "danger")):
                        status = create(
                            "StatusOrb.qml",
                            {"statusKind": kind, "label": kind.title()},
                        )
                        status.setX(280)
                        status.setY(120 + index * 70)
                        status.setWidth(220)
                        status.setHeight(status.implicitHeight())
                        semantic.append(status)

                    window.setColor(theme.property("canvas"))
                    window.setWidth(540)
                    window.setHeight(380)
                    window.show()
                    window.requestActivate()
                    self.qapp.processEvents()
                    primary.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                    self.qapp.processEvents()

                    primary_background = primary.findChild(
                        QObject, "buttonBackground"
                    )
                    primary_label = primary.findChild(QObject, "buttonLabel")
                    self.assertEqual(
                        QColor(primary_background.property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            primary_label.property("color"),
                            primary_background.property("color"),
                        ),
                        7.0,
                    )

                    nav_background = max(
                        (
                            item
                            for item in self._visual_items(selected_nav)
                            if "Rectangle" in item.metaObject().className()
                            and item.isVisible()
                            and QColor(item.property("color")).alpha() > 0
                        ),
                        key=lambda item: item.width() * item.height(),
                    )
                    nav_label = next(
                        item
                        for item in self._visual_items(selected_nav)
                        if item.property("text") == "Home"
                    )
                    self.assertEqual(
                        QColor(nav_background.property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            nav_label.property("color"),
                            nav_background.property("color"),
                        ),
                        7.0,
                    )

                    switch_track = checked_switch.findChild(QObject, "switchTrack")
                    switch_knob = checked_switch.findChild(QObject, "switchKnob")
                    self.assertEqual(
                        QColor(switch_track.property("color")),
                        QColor(theme.property("accent")),
                    )
                    self.assertGreaterEqual(
                        self._contrast(
                            switch_knob.property("color"),
                            switch_track.property("color"),
                        ),
                        7.0,
                    )

                    disabled_background = disabled.findChild(
                        QObject, "buttonBackground"
                    )
                    disabled_label = disabled.findChild(QObject, "buttonLabel")
                    self.assertGreaterEqual(
                        self._contrast(
                            disabled_label.property("color"),
                            disabled_background.property("color"),
                        ),
                        4.5,
                    )

                    symbols = set()
                    for status in semantic:
                        badge = status.findChild(QObject, "statusOrbBadge")
                        glyph = status.findChild(QObject, "statusOrbGlyph")
                        symbols.add(glyph.property("text"))
                        self.assertEqual(
                            QColor(badge.property("color")),
                            QColor(theme.property("accent")),
                        )
                        self.assertGreaterEqual(
                            self._contrast(
                                glyph.property("color"), badge.property("color")
                            ),
                            7.0,
                        )
                    self.assertEqual(symbols, {"\u2713", "!", "\u00d7"})

                    focus_rings = [
                        item
                        for item in self._visual_items(primary)
                        if "FocusRing" in item.metaObject().className()
                    ]
                    self.assertEqual(len(focus_rings), 1)
                    self.assertTrue(focus_rings[0].isVisible())
                    self.assertEqual(theme.property("focusWidth"), 2)
                    self.assertGreaterEqual(
                        self._contrast(
                            theme.property("focus"), theme.property("canvas")
                        ),
                        3.0,
                    )

                    image = window.grabWindow()
                    self.assertFalse(image.isNull())
                    ratio = image.devicePixelRatio()
                    clearance = int(theme.property("focusWidth")) + int(
                        theme.property("focusClearance")
                    )
                    focus_x = round(
                        (primary.x() + primary.width() / 2) * ratio
                    )
                    focus_y = round((primary.y() - clearance + 1) * ratio)
                    self.assertEqual(
                        self._hex(image.pixelColor(focus_x, focus_y)),
                        self._hex(theme.property("focus")),
                    )
                finally:
                    window.close()
                    for item in objects:
                        item.setParentItem(None)
                        item.deleteLater()
                    for component in components:
                        component.deleteLater()
                    theme.deleteLater()
                    engine.deleteLater()
                    self.qapp.processEvents()

    def test_danger_button_pressed_pair_is_distinct_and_high_contrast_safe(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        theme.setProperty("reduceMotion", True)
        component = self._component(engine, "QuietButton.qml")
        button = component.createWithInitialProperties(
            {"tokens": theme, "kind": "danger", "text": "Remove"}
        )
        self.assertIsNotNone(
            button, [error.toString() for error in component.errors()]
        )
        try:
            background = button.findChild(QObject, "buttonBackground")
            label = button.findChild(QObject, "buttonLabel")
            for mode in ("light", "dark", "high_contrast"):
                theme.setProperty("mode", mode)
                button.setProperty("down", False)
                self.qapp.processEvents()
                self.assertEqual(
                    QColor(background.property("color")),
                    QColor(theme.property("dangerSurface")),
                    mode,
                )
                self.assertEqual(
                    QColor(label.property("color")),
                    QColor(theme.property("danger")),
                    mode,
                )

                button.setProperty("down", True)
                self.qapp.processEvents()
                self.assertEqual(
                    QColor(background.property("color")),
                    QColor(theme.property("dangerPressedSurface")),
                    mode,
                )
                self.assertEqual(
                    QColor(label.property("color")),
                    QColor(theme.property("dangerStrongText")),
                    mode,
                )
                self.assertNotEqual(
                    QColor(theme.property("dangerHoverSurface")),
                    QColor(theme.property("dangerSurface")),
                    mode,
                )

            source = (self.qml / "QuietButton.qml").read_text(encoding="utf-8")
            self.assertIn("hovered ? tokens.dangerHoverSurface", source)
        finally:
            button.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_switch_pressed_and_text_field_error_states_are_concrete(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        theme.setProperty("reduceMotion", True)
        switch_component = self._component(engine, "QuietSwitch.qml")
        field_component = self._component(engine, "QuietTextField.qml")
        switch = switch_component.createWithInitialProperties({"tokens": theme})
        field = field_component.createWithInitialProperties({"tokens": theme})
        self.assertIsNotNone(
            switch, [error.toString() for error in switch_component.errors()]
        )
        self.assertIsNotNone(
            field, [error.toString() for error in field_component.errors()]
        )
        try:
            track = switch.findChild(QObject, "switchTrack")
            knob = switch.findChild(QObject, "switchKnob")
            field_background = field.findChild(QObject, "textFieldBackground")

            switch.setProperty("checked", True)
            switch.setProperty("down", False)
            self.qapp.processEvents()
            self.assertEqual(
                QColor(track.property("color")), QColor(theme.property("accent"))
            )
            switch.setProperty("down", True)
            self.qapp.processEvents()
            self.assertEqual(
                QColor(track.property("color")),
                QColor(theme.property("accentPressedSurface")),
            )

            field.setProperty("error", True)
            field.setProperty("errorMessage", "Enter a valid value")
            self.qapp.processEvents()
            self.assertTrue(field.property("error"))
            self.assertEqual(
                QColor(field_background.property("color")),
                QColor(theme.property("dangerSurface")),
            )
            self.assertEqual(
                QColor(field.property("resolvedBorderColor")),
                QColor(theme.property("danger")),
            )

            switch.setProperty("checked", True)
            switch.setProperty("down", False)
            switch.setProperty("enabled", False)
            for mode in ("light", "dark", "high_contrast"):
                theme.setProperty("mode", mode)
                self.qapp.processEvents()
                self.assertEqual(
                    QColor(track.property("color")),
                    QColor(theme.property("disabledControlSurface")),
                    mode,
                )
                self.assertEqual(
                    QColor(knob.property("color")),
                    QColor(theme.property("disabledControlText")),
                    mode,
                )
                self.assertGreaterEqual(
                    self._contrast(
                        track.property("color"), knob.property("color")
                    ),
                    3.0,
                    mode,
                )

            switch_source = (self.qml / "QuietSwitch.qml").read_text(
                encoding="utf-8"
            )
            field_source = (self.qml / "QuietTextField.qml").read_text(
                encoding="utf-8"
            )
            self.assertIn("hovered ? tokens.accentHoverSurface", switch_source)
            self.assertIn("if (hovered) return tokens.hover", switch_source)
            self.assertIn("hovered && !tokens.highContrast", field_source)
        finally:
            switch.deleteLater()
            field.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_signal_nodes_and_setting_separators_are_opaque(self):
        engine = QQmlApplicationEngine()
        theme = self._theme(engine)
        signal_component = self._component(engine, "SignalNode.qml")
        row_component = self._component(engine, "SettingRow.qml")
        signal = signal_component.createWithInitialProperties(
            {"tokens": theme, "label": "Transcribe", "active": True}
        )
        row = row_component.createWithInitialProperties(
            {"tokens": theme, "label": "Example setting"}
        )
        self.assertIsNotNone(
            signal, [error.toString() for error in signal_component.errors()]
        )
        self.assertIsNotNone(
            row, [error.toString() for error in row_component.errors()]
        )
        try:
            node_surface = signal.findChild(QObject, "signalNodeSurface")
            separator = row.findChild(QObject, "settingSeparator")
            for mode in ("light", "dark", "high_contrast"):
                theme.setProperty("mode", mode)
                self.qapp.processEvents()
                self.assertAlmostEqual(
                    QColor(node_surface.property("color")).alphaF(), 1.0, places=5
                )
                self.assertAlmostEqual(
                    QColor(separator.property("color")).alphaF(), 1.0, places=5
                )
        finally:
            signal.deleteLater()
            row.deleteLater()
            theme.deleteLater()
            engine.deleteLater()
            self.qapp.processEvents()

    def test_foundation_has_no_remote_or_idle_effect_mechanism(self):
        names = {
            "Theme.qml",
            "CosmicBackdrop.qml",
            "GlassSurface.qml",
            "FocusRing.qml",
            "StatusOrb.qml",
            "SectionHeading.qml",
            "InlineNotice.qml",
            "ChromeButton.qml",
        }
        combined = "\n".join(
            (self.qml / name).read_text(encoding="utf-8") for name in names
        )
        for forbidden in (
            "http://",
            "https://",
            "ShaderEffect",
            "Timer {",
            "Animation.Infinite",
            "ParticleSystem",
        ):
            self.assertNotIn(forbidden, combined)

        for name in (
            "QuietButton.qml",
            "QuietSwitch.qml",
            "QuietTextField.qml",
            "QuietComboBox.qml",
            "NavigationButton.qml",
            "ChromeButton.qml",
        ):
            self.assertIn(
                "FocusRing {", (self.qml / name).read_text(encoding="utf-8"), name
            )


if __name__ == "__main__":
    unittest.main()
