from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication


class QmlComponentContractTests(unittest.TestCase):
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

    def _theme(self, engine):
        component = self._component(engine, "Theme.qml")
        theme = component.create()
        self.assertIsNotNone(
            theme, [error.toString() for error in component.errors()]
        )
        theme.setParent(engine)
        return theme

    @staticmethod
    def _hex(value):
        return QColor(value).name(QColor.NameFormat.HexRgb).upper()

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
