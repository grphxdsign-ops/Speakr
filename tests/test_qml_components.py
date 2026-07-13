from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow
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
                icon = notice.findChild(QObject, "noticeIcon")
                self.assertIsNotNone(layout)
                self.assertIsNotNone(text_column)
                self.assertIsNotNone(action)
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
            self.assertIn(
                "accentText: highContrast ? systemPalette.highlightedText",
                (self.qml / "Theme.qml").read_text(encoding="utf-8"),
            )

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

            switch_source = (self.qml / "QuietSwitch.qml").read_text(
                encoding="utf-8"
            )
            field_source = (self.qml / "QuietTextField.qml").read_text(
                encoding="utf-8"
            )
            self.assertIn("hovered ? tokens.accentHoverSurface", switch_source)
            self.assertIn("if (hovered) return tokens.hover", switch_source)
            self.assertIn("hovered ? tokens.surfaceRaised", field_source)
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
