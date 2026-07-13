from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import (
    QMetaObject,
    QObject,
    QPointF,
    Q_RETURN_ARG,
    Qt,
    QUrl,
)
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge
from tests.qml_lifecycle import dispose_qml_fixture


class _VocabularyApp:
    def __init__(self):
        self.interface_state = InterfaceState(
            {
                "availability": "ready",
                "enabled": True,
                "hotkey": "right ctrl",
            }
        )
        self.enabled = True
        self.mutation_failure = ""
        self.reload_succeeds = True
        self.reload_attempts = 0
        self.opened = []
        self.removed = []
        self.approved = []
        self.forgotten = []
        self._next_id = 20
        self.manual = [
            {"id": "4:a1", "kind": "word", "word": "Speakr"},
            {
                "id": "8:b2",
                "kind": "replacement",
                "heard": "speak her",
                "intended": "Speakr",
            },
        ]
        self.learned = [
            {"id": "orbital", "word": "Orbital", "count": 4},
            {"id": "luminous", "word": "Luminous", "count": 2},
        ]

    @staticmethod
    def settings_snapshot():
        return {
            "ui": {
                "theme": "dark",
                "density": "comfortable",
                "text_scale": 100,
                "reduced_motion": "reduce",
                "visual_effects": "system",
            }
        }

    @staticmethod
    def practice_snapshot():
        return {}

    def list_manual_words(self):
        return list(self.manual)

    def list_learned_words(self):
        return list(self.learned)

    @staticmethod
    def subscribe_settings(_callback):
        return lambda: None

    @staticmethod
    def subscribe_practice(_callback):
        return lambda: None

    def _allow_mutation(self):
        if not self.mutation_failure:
            return True
        if self.mutation_failure == "busy":
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current local dictation before changing Vocabulary.",
                "dismiss",
                blocking=False,
            )
        elif self.mutation_failure == "invalid":
            self.interface_state.latch_issue(
                "dictionary_invalid",
                "Enter one word or name without '=>'.",
                "edit_vocabulary",
                blocking=False,
            )
        elif self.mutation_failure == "changed":
            self.interface_state.latch_issue(
                "dictionary_changed",
                "That dictionary entry changed. Refresh and try again.",
                "reload_dictionary",
                blocking=False,
            )
        else:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "The local dictionary is unchanged.",
                "open_dictionary",
                blocking=False,
            )
        return False

    def add_word(self, word):
        if not self._allow_mutation():
            return False
        self._next_id += 1
        self.manual.append(
            {"id": f"{self._next_id}:word", "kind": "word", "word": word}
        )
        return True

    def add_replacement(self, heard, intended):
        if not self._allow_mutation():
            return False
        self._next_id += 1
        self.manual.append(
            {
                "id": f"{self._next_id}:replacement",
                "kind": "replacement",
                "heard": heard,
                "intended": intended,
            }
        )
        return True

    def remove_manual_word(self, entry_id):
        if not self._allow_mutation():
            return False
        self.removed.append(entry_id)
        self.manual = [entry for entry in self.manual if entry["id"] != entry_id]
        return True

    def approve_learned_word(self, word):
        if not self._allow_mutation():
            return False
        self.approved.append(word)
        self._next_id += 1
        self.manual.append(
            {"id": f"{self._next_id}:approved", "kind": "word", "word": word}
        )
        self.learned = [entry for entry in self.learned if entry["word"] != word]
        return True

    def forget_learned_word(self, word):
        if not self._allow_mutation():
            return False
        self.forgotten.append(word)
        self.learned = [entry for entry in self.learned if entry["word"] != word]
        return True

    def reload_dictionary(self):
        self.reload_attempts += 1
        return self.reload_succeeds

    def open_local(self, kind):
        self.opened.append(kind)
        return True

    def dismiss_issue(self):
        self.interface_state.dismiss_issue()
        return True


class VocabularyQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        cls.qapp = QApplication.instance() or QApplication([])
        cls.qml = (
            Path(__file__).resolve().parents[1] / "speakr" / "ui" / "qml"
        )

    def _fixture(self, *, text_scale=100, mode="dark", app_setup=None):
        app = _VocabularyApp()
        if app_setup is not None:
            app_setup(app)
        bridge = Bridge(app)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        component = QQmlComponent(engine)
        component.setData(
            f"""
import QtQuick
import QtQuick.Controls
import "."

Item {{
    id: fixture
    objectName: "vocabularyFixture"
    width: 640
    height: 520

    Theme {{
        id: theme
        mode: "{mode}"
        textScale: {text_scale} / 100.0
        reduceMotion: true
    }}

    VocabularyPage {{
        anchors.fill: parent
        tokens: theme
        appState: bridge.state
        manualWords: bridge.manualWords
        learnedWords: bridge.learnedWords
    }}
}}
""".encode("utf-8"),
            QUrl.fromLocalFile(str(self.qml / "VocabularyHarness.qml")),
        )
        fixture = component.create()
        self.assertIsNotNone(
            fixture, [error.toString() for error in component.errors()]
        )

        window = QQuickWindow()
        window.setWidth(640)
        window.setHeight(520)
        QQmlEngine.setObjectOwnership(fixture, QQmlEngine.CppOwnership)
        fixture.setParent(window.contentItem())
        fixture.setParentItem(window.contentItem())
        window.show()
        self._settle(fixture)
        page = fixture.findChild(QObject, "vocabularyPage")
        self.assertIsNotNone(page)
        return app, bridge, engine, fixture, page, window, warnings

    def _dispose(self, bridge, engine, fixture, window, warnings):
        dispose_qml_fixture(
            self.qapp,
            engine,
            roots=(fixture,),
            windows=(window,),
            context_objects=(bridge,),
        )
        self.assertEqual(warnings, [])

    def _settle(self, item, cycles=8):
        for _ in range(cycles):
            self.qapp.processEvents()
            item.ensurePolished()

    @staticmethod
    def _invoke_qml(target, method):
        return QMetaObject.invokeMethod(
            target,
            method,
            Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"),
        )

    @staticmethod
    def _focus_rings(control):
        rings = []
        for child in control.findChildren(QObject):
            meta = child.metaObject()
            if meta.indexOfProperty("shown") >= 0 and meta.indexOfProperty(
                "cornerRadius"
            ) >= 0:
                rings.append(child)
        return rings

    @classmethod
    def _find_visual_child(cls, item, object_name):
        for child in item.childItems():
            if child.objectName() == object_name:
                return child
            match = cls._find_visual_child(child, object_name)
            if match is not None:
                return match
        return None

    def test_real_bridge_results_preserve_failed_inputs_and_refresh_counts(self):
        app, bridge, engine, fixture, page, window, warnings = self._fixture()
        try:
            word = fixture.findChild(QObject, "newManualWordField")
            heard = fixture.findChild(QObject, "newReplacementHeardField")
            intended = fixture.findChild(QObject, "newReplacementIntendedField")
            issue = fixture.findChild(QObject, "vocabularyIssueNotice")
            summary = fixture.findChild(QObject, "vocabularySummaryStatus")
            self.assertIsNotNone(word)
            self.assertIsNotNone(heard)
            self.assertIsNotNone(intended)
            self.assertIsNotNone(issue)
            self.assertIsNotNone(summary)

            app.mutation_failure = "busy"
            word.setProperty("text", "Preserve Me")
            self.assertFalse(self._invoke_qml(page, "submitWord"))
            self._settle(fixture)
            self.assertEqual(word.property("text"), "Preserve Me")
            self.assertTrue(issue.property("visible"))
            self.assertEqual(issue.property("kind"), "warning")
            self.assertIn("temporarily paused", issue.property("title"))

            app.mutation_failure = ""
            self.assertTrue(self._invoke_qml(page, "submitWord"))
            self._settle(fixture)
            self.assertEqual(word.property("text"), "")
            self.assertEqual(page.property("manualWordCount"), 2)

            app.mutation_failure = "save"
            page.setProperty("tabIndex", 1)
            heard.setProperty("text", "luminous or bit")
            intended.setProperty("text", "Luminous Orbit")
            self.assertFalse(self._invoke_qml(page, "submitReplacement"))
            self._settle(fixture)
            self.assertEqual(heard.property("text"), "luminous or bit")
            self.assertEqual(intended.property("text"), "Luminous Orbit")
            self.assertEqual(issue.property("kind"), "danger")

            app.mutation_failure = ""
            self.assertTrue(self._invoke_qml(page, "submitReplacement"))
            self._settle(fixture)
            self.assertEqual(heard.property("text"), "")
            self.assertEqual(intended.property("text"), "")
            self.assertEqual(page.property("replacementCount"), 2)
            self.assertIn("2 manual words", summary.property("description"))
            self.assertIn("2 replacements", summary.property("description"))
            self.assertEqual(warnings, [])
        finally:
            self._dispose(bridge, engine, fixture, window, warnings)

    def test_content_bound_ids_and_forget_actions_require_confirmation(self):
        app, bridge, engine, fixture, page, window, warnings = self._fixture()
        try:
            manual_remove = self._find_visual_child(
                fixture, "removeManualButton_4:a1"
            )
            learned_forget = self._find_visual_child(
                fixture, "forgetLearnedButton_orbital"
            )
            confirmation = fixture.findChild(QObject, "vocabularyConfirmation")
            cancel = fixture.findChild(QObject, "cancelVocabularyDeletion")
            confirm = fixture.findChild(QObject, "confirmVocabularyDeletion")
            for item in (
                manual_remove,
                learned_forget,
                confirmation,
                cancel,
                confirm,
            ):
                self.assertIsNotNone(item)

            self.assertTrue(QMetaObject.invokeMethod(manual_remove, "click"))
            self._settle(fixture)
            self.assertTrue(confirmation.property("visible"))
            self.assertEqual(page.property("pendingId"), "4:a1")
            self.assertEqual(app.removed, [])
            self.assertEqual(window.activeFocusItem().objectName(), "cancelVocabularyDeletion")

            self.assertTrue(QMetaObject.invokeMethod(cancel, "click"))
            self._settle(fixture)
            self.assertFalse(confirmation.property("visible"))
            self.assertEqual(app.removed, [])

            self.assertTrue(QMetaObject.invokeMethod(manual_remove, "click"))
            self._settle(fixture)
            self.assertTrue(QMetaObject.invokeMethod(confirm, "click"))
            self._settle(fixture)
            self.assertEqual(app.removed, ["4:a1"])

            page.setProperty("tabIndex", 2)
            self._settle(fixture)
            self.assertTrue(QMetaObject.invokeMethod(learned_forget, "click"))
            self._settle(fixture)
            self.assertEqual(page.property("pendingId"), "orbital")
            self.assertEqual(app.forgotten, [])
            self.assertTrue(QMetaObject.invokeMethod(confirm, "click"))
            self._settle(fixture)
            self.assertEqual(app.forgotten, ["Orbital"])

            approve = self._find_visual_child(
                fixture, "approveLearnedButton_luminous"
            )
            self.assertIsNotNone(approve)
            self.assertTrue(QMetaObject.invokeMethod(approve, "click"))
            self._settle(fixture)
            self.assertEqual(app.approved, ["Luminous"])
            self.assertEqual(page.property("learnedWordCount"), 0)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(bridge, engine, fixture, window, warnings)

    def test_long_replacement_confirmation_keeps_actions_visible_and_scrollable(self):
        heard = "heard-" + "h" * 97
        intended = "intended-" + "i" * 94
        self.assertEqual(len(heard), 103)
        self.assertEqual(len(intended), 103)
        entry_id = "12:long-bound-id"

        def setup(app):
            app.manual = [
                {
                    "id": entry_id,
                    "kind": "replacement",
                    "heard": heard,
                    "intended": intended,
                }
            ]
            app.learned = []

        app, bridge, engine, fixture, page, window, warnings = self._fixture(
            text_scale=200,
            mode="high_contrast",
            app_setup=setup,
        )
        try:
            page.setProperty("tabIndex", 1)
            self._settle(fixture)
            remove = self._find_visual_child(
                fixture, f"removeReplacementButton_{entry_id}"
            )
            confirmation = fixture.findChild(QObject, "vocabularyConfirmation")
            body_scroll = fixture.findChild(
                QObject, "vocabularyConfirmationBodyScroll"
            )
            actions = fixture.findChild(QObject, "vocabularyConfirmationActions")
            cancel = fixture.findChild(QObject, "cancelVocabularyDeletion")
            confirm = fixture.findChild(QObject, "confirmVocabularyDeletion")
            for item in (
                remove,
                confirmation,
                body_scroll,
                actions,
                cancel,
                confirm,
            ):
                self.assertIsNotNone(item)

            self.assertTrue(QMetaObject.invokeMethod(remove, "click"))
            self._settle(fixture, 12)
            self.assertTrue(confirmation.property("visible"))
            self.assertEqual(page.property("pendingId"), entry_id)
            self.assertLessEqual(confirmation.property("height"), window.height())
            self.assertLessEqual(
                confirmation.property("y") + confirmation.property("height"),
                window.height() + 1,
            )

            body_viewport = body_scroll.property("contentItem")
            self.assertGreater(
                body_viewport.property("contentHeight"),
                body_viewport.height() + 1,
            )
            for item in (actions, cancel, confirm):
                position = item.mapToItem(window.contentItem(), QPointF(0, 0))
                self.assertTrue(item.isVisible(), item.objectName())
                self.assertGreaterEqual(position.x(), -1, item.objectName())
                self.assertGreaterEqual(position.y(), -1, item.objectName())
                self.assertLessEqual(
                    position.x() + item.width(),
                    window.width() + 1,
                    item.objectName(),
                )
                self.assertLessEqual(
                    position.y() + item.height(),
                    window.height() + 1,
                    item.objectName(),
                )

            self.assertEqual(
                window.activeFocusItem().objectName(),
                "cancelVocabularyDeletion",
            )
            body_scroll.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            self._settle(fixture)
            self.assertEqual(body_viewport.property("contentY"), 0)
            QTest.keyClick(window, Qt.Key.Key_PageDown)
            self._settle(fixture)
            self.assertGreater(body_viewport.property("contentY"), 0)

            cancel.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            self._settle(fixture)
            QTest.keyClick(window, Qt.Key.Key_Tab)
            self._settle(fixture)
            self.assertEqual(
                window.activeFocusItem().objectName(),
                "confirmVocabularyDeletion",
            )
            QTest.keyClick(window, Qt.Key.Key_Space)
            self._settle(fixture)
            self.assertEqual(app.removed, [entry_id])
            self.assertFalse(confirmation.property("visible"))
            self.assertEqual(warnings, [])
        finally:
            self._dispose(bridge, engine, fixture, window, warnings)

    def test_recovery_routes_cover_invalid_changed_save_and_reload_failure(self):
        app, bridge, engine, fixture, page, window, warnings = self._fixture()
        try:
            issue = fixture.findChild(QObject, "vocabularyIssueNotice")
            reload_failure = fixture.findChild(
                QObject, "vocabularyReloadFailure"
            )
            self.assertIsNotNone(issue)
            self.assertIsNotNone(reload_failure)

            app.mutation_failure = "invalid"
            field = fixture.findChild(QObject, "newManualWordField")
            field.setProperty("text", "bad => value")
            self.assertFalse(self._invoke_qml(page, "submitWord"))
            self._settle(fixture)
            self.assertEqual(issue.property("actionText"), "Open dictionary file")
            self.assertTrue(self._invoke_qml(page, "runIssueAction"))
            self.assertEqual(app.opened, ["dictionary"])

            app.interface_state.latch_issue(
                "dictionary_changed",
                "That dictionary entry changed. Refresh and try again.",
                "reload_dictionary",
                blocking=False,
            )
            app.reload_succeeds = False
            self._settle(fixture)
            self.assertEqual(issue.property("actionText"), "Reload from file")
            self.assertFalse(self._invoke_qml(page, "runIssueAction"))
            self._settle(fixture)
            self.assertTrue(page.property("reloadFailed"))
            self.assertTrue(reload_failure.property("visible"))
            self.assertEqual(app.reload_attempts, 1)

            app.reload_succeeds = True
            self.assertTrue(self._invoke_qml(page, "reloadVocabulary"))
            self._settle(fixture)
            self.assertFalse(page.property("reloadFailed"))
            self.assertEqual(app.reload_attempts, 2)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(bridge, engine, fixture, window, warnings)

    def test_narrow_200_percent_reflow_and_visible_keyboard_focus(self):
        app, bridge, engine, fixture, page, window, warnings = self._fixture(
            text_scale=200, mode="high_contrast"
        )
        try:
            scroll = fixture.findChild(QObject, "vocabularyScroll")
            field = fixture.findChild(QObject, "newManualWordField")
            reload_button = fixture.findChild(QObject, "reloadVocabularyButton")
            self.assertIsNotNone(scroll)
            self.assertIsNotNone(field)
            self.assertIsNotNone(reload_button)

            for name in (
                "vocabularyHeroSurface",
                "vocabularySectionNavigation",
                "vocabularyContentSurface",
                "vocabularyLocalFileSurface",
            ):
                surface = fixture.findChild(QObject, name)
                self.assertIsNotNone(surface, name)
                self.assertGreaterEqual(surface.x(), 0, name)
                self.assertLessEqual(surface.x() + surface.width(), page.width() + 1, name)

            self.assertLessEqual(scroll.property("contentWidth"), scroll.width() + 0.5)
            self.assertGreaterEqual(field.height(), 44)
            field.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            self._settle(fixture)
            self.assertTrue(field.property("activeFocus"))
            rings = self._focus_rings(field)
            self.assertTrue(rings)
            self.assertTrue(any(ring.property("shown") and ring.isVisible() for ring in rings))

            remove_button = self._find_visual_child(
                fixture, "removeManualButton_4:a1"
            )
            confirmation = fixture.findChild(QObject, "vocabularyConfirmation")
            cancel = fixture.findChild(QObject, "cancelVocabularyDeletion")
            self.assertIsNotNone(remove_button)
            self.assertIsNotNone(confirmation)
            self.assertIsNotNone(cancel)
            self.assertTrue(QMetaObject.invokeMethod(remove_button, "click"))
            self._settle(fixture)
            self.assertTrue(confirmation.property("visible"))
            confirmation_x = confirmation.property("x")
            confirmation_y = confirmation.property("y")
            confirmation_width = confirmation.property("width")
            confirmation_height = confirmation.property("height")
            self.assertGreaterEqual(confirmation_x, 0)
            self.assertLessEqual(
                confirmation_x + confirmation_width, page.width() + 1
            )
            self.assertGreaterEqual(confirmation_y, 0)
            self.assertLessEqual(
                confirmation_y + confirmation_height, page.height() + 1
            )
            self.assertEqual(window.activeFocusItem().objectName(), "cancelVocabularyDeletion")
            self.assertTrue(QMetaObject.invokeMethod(cancel, "click"))
            self._settle(fixture)

            reload_button.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            self._settle(fixture, 12)
            viewport = scroll.property("contentItem")
            position = reload_button.mapToItem(viewport, QPointF(0, 0))
            self.assertGreaterEqual(position.y(), -1)
            self.assertLessEqual(
                position.y() + reload_button.height(), viewport.height() + 1
            )
            self.assertGreater(viewport.property("contentY"), 0)
            self.assertEqual(warnings, [])
        finally:
            self._dispose(bridge, engine, fixture, window, warnings)

    def test_page_uses_only_shared_luminous_orbit_primitives(self):
        source = (self.qml / "VocabularyPage.qml").read_text(encoding="utf-8")
        for component in (
            "GlassSurface {",
            "SectionHeading {",
            "InlineNotice {",
            "StatusOrb {",
            "QuietButton {",
            "QuietTextField {",
        ):
            self.assertIn(component, source)
        for contract in (
            'objectName: "manualWordsTab"',
            'objectName: "replacementsTab"',
            'objectName: "learnedWordsTab"',
            'objectName: "vocabularyConfirmation"',
            'objectName: "openDictionaryFileButton"',
            'objectName: "reloadVocabularyButton"',
            "readonly property string entryId:",
            "contentWidth: availableWidth",
        ):
            self.assertIn(contract, source)
        for forbidden in (
            "http://",
            "https://",
            "XMLHttpRequest",
            "ShaderEffect",
            "Timer {",
            "Animation.Infinite",
            "ParticleSystem",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3,8}", source))
        self.assertIsNone(re.search(r"\bText\s*\{", source))
        self.assertIsNone(re.search(r"\bTextArea\s*\{", source))


if __name__ == "__main__":
    unittest.main()
