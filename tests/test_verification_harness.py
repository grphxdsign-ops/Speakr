from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

from PySide6.QtCore import QMetaObject, QObject, QUrl
from PySide6.QtGui import QColor, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from scripts.capture_ui_verification import capture_scenarios
from scripts.verify_luminous_interface import (
    REQUIRED_EVIDENCE_TESTS,
    ROUTED_PR12_PRODUCT_VETOES,
    detect_missing_interactive_windows_proof,
    detect_qml_runtime_warnings,
    diff_check_commands,
    invalid_evidence_test_ids,
    native_rect_matches_work_area,
    run_verification,
    sanitize_evidence_text,
    scan_raw_runtime_outputs,
)
from speakr import qt_ui
from speakr.interface_state import InterfaceState
from speakr.qt_ui import Bridge
from tests.qml_lifecycle import dispose_qml_fixture
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
        dispose_qml_fixture(
            self.qapp,
            engine,
            context_objects=(bridge,),
        )
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
        self.assertEqual(invalid_evidence_test_ids(), [])
        misspelled = (
            "tests.test_qml_load.QmlLoadTests."
            "test_main_and_hud_load_without_qml_warningz"
        )
        self.assertEqual(
            invalid_evidence_test_ids({"misspelled": (misspelled,)}),
            [misspelled],
        )

    def test_every_qml_component_compiles_without_errors(self):
        engine = QQmlApplicationEngine()
        warnings = []
        components = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        try:
            for path in sorted(self.qml.glob("*.qml")):
                with self.subTest(component=path.name):
                    component = QQmlComponent(
                        engine, QUrl.fromLocalFile(str(path))
                    )
                    components.append(component)
                    self.assertEqual(
                        component.status(),
                        QQmlComponent.Status.Ready,
                        [error.toString() for error in component.errors()],
                    )
                    self.assertEqual(component.errors(), [])
            self.assertEqual(warnings, [])
        finally:
            dispose_qml_fixture(
                self.qapp,
                engine,
                components=tuple(components),
            )
        self.assertEqual(warnings, [])

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
                "file:///tmp/Card.qml:20:5: QML Rectangle: Cannot anchor to an item that is not a parent or sibling",
                "file:///tmp/Flow.qml:30: QML Connections: Detected function onMissing with no matching signal",
                "file:///tmp/Field.qml:40:7: Cannot assign to non-existent property missing",
                "file:///tmp/Icon.qml:50: QML Image: Cannot open: file:///tmp/missing.svg",
                "qt.qpa.fonts: Populating font family aliases took 68 ms. Replace uses of missing font family 'SF Pro Text'",
                "Scenegraph already initialized, setBackend() request ignored",
                "Unable to initialize renderer Direct3D",
            )
        )
        matches = detect_qml_runtime_warnings(clean + diagnostics)
        self.assertEqual(len(matches), 10)
        skipped_focus = (
            "test_windows_native_probe_preserves_foreground_focus_and_caret "
            "(test_hud_qml.HudQmlTests.test_windows_native_probe_preserves_"
            "foreground_focus_and_caret) ... skipped 'interactive desktop unavailable'\n"
            "test_native_windows_gpu_and_software_preserve_focus_and_caret "
            "(test_renderer_truth.RendererDeviceTests.test_native_windows_gpu_"
            "and_software_preserve_focus_and_caret) ... skipped "
            "'Windows focus/caret identity unavailable'"
        )
        expected = 2 if sys.platform == "win32" else 0
        self.assertEqual(
            len(detect_missing_interactive_windows_proof(skipped_focus)), expected
        )

    def test_raw_runtime_log_marker_scan_is_explicit_and_fail_closed(self):
        clean = {
            "unit_and_interface_tests": "Ran 211 tests\nOK\n",
            "platform_screenshots": "Captured 11 UI scenarios\n",
            "qmllint": "file:///advisory.qml:1: warning: advisory only\n",
        }
        self.assertEqual(scan_raw_runtime_outputs(clean), {})

        dirty = dict(clean)
        dirty["platform_screenshots"] += (
            "Unable to initialize graphics renderer Direct3D\n"
        )
        self.assertEqual(
            scan_raw_runtime_outputs(dirty),
            {
                "platform_screenshots": [
                    "Unable to initialize graphics renderer Direct3D"
                ]
            },
        )

    def test_pr12_product_vetoes_are_routed_without_claiming_resolution(self):
        self.assertEqual(
            [item["id"] for item in ROUTED_PR12_PRODUCT_VETOES],
            list(range(1, 12)),
        )
        for item in ROUTED_PR12_PRODUCT_VETOES:
            self.assertIn("PR-12 integration", item["owner"])
            self.assertTrue(item["veto"].endswith("."))

    def test_review_evidence_redacts_machine_local_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            source = " | ".join(
                (
                    str(self.root / "speakr" / "ui" / "qml" / "Main.qml"),
                    (self.root / "speakr" / "ui" / "qml" / "Main.qml").as_uri(),
                    str(Path.home() / "private" / "fixture.log"),
                    str(output / "screenshots"),
                )
            )
            sanitized = sanitize_evidence_text(source, output)
            self.assertNotIn(str(self.root), sanitized)
            self.assertNotIn(self.root.as_uri(), sanitized)
            self.assertNotIn(str(Path.home()), sanitized)
            self.assertNotIn(str(output), sanitized)
            self.assertIn("<repo>", sanitized)
            self.assertIn("<home>", sanitized)
            self.assertIn("<output>", sanitized)

    def test_native_work_area_match_requires_every_edge(self):
        work = (0, 0, 1920, 1080)
        self.assertTrue(native_rect_matches_work_area(work, work, 8, 8))
        self.assertTrue(
            native_rect_matches_work_area((-8, -8, 1928, 1088), work, 8, 8)
        )
        self.assertFalse(
            native_rect_matches_work_area((100, 100, 1820, 980), work, 8, 8)
        )
        self.assertFalse(native_rect_matches_work_area((0, 0, 1920), work, 8, 8))

    def test_diff_checks_cover_committed_and_working_changes(self):
        expected_base = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/main"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        commands = diff_check_commands(
            self.root,
            {"SPEAKR_VERIFY_BASE": "origin/main"},
        )
        self.assertEqual(
            [name for name, _command, _environment in commands],
            ["committed_diff_check", "working_tree_diff_check"],
        )
        self.assertEqual(
            tuple(commands[0][1]),
            ("git", "diff", "--check", f"{expected_base}...HEAD"),
        )
        self.assertEqual(
            tuple(commands[1][1]),
            ("git", "diff", "--check"),
        )

        with tempfile.TemporaryDirectory() as directory:
            fallback = diff_check_commands(
                Path(directory),
                {"SPEAKR_VERIFY_BASE": "missing-base"},
            )
        self.assertEqual(
            fallback,
            [("working_tree_diff_check", ("git", "diff", "--check"), {})],
        )

    def test_missing_qmllint_records_a_failed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch(
                "scripts.verify_luminous_interface._qmllint_executable",
                side_effect=FileNotFoundError("qmllint unavailable"),
            ), mock.patch("sys.stderr", new=io.StringIO()) as stderr:
                self.assertEqual(run_verification(output), 1)
            self.assertIn("FAILED: qmllint_discovery", stderr.getvalue())
            report = json.loads(
                (output / "verification-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["automated_status"], "failed")
            self.assertEqual(report["failed_step"], "qmllint_discovery")
            self.assertEqual(report["steps"][0]["name"], "qmllint_discovery")
            self.assertEqual(report["steps"][0]["exit_code"], None)
            self.assertIn("qmllint unavailable", report["steps"][0]["error"])

    def test_platform_screenshot_runtime_diagnostics_fail_report(self):
        diagnostics = "\n".join(
            (
                "qt.qpa.fonts: Populating font family aliases took 68 ms. "
                "Replace uses of missing font family 'SF Pro Text'",
                "Scenegraph already initialized, setBackend() request ignored",
            )
        )
        completed = subprocess.CompletedProcess(
            args=["fake-screenshot-capture"],
            returncode=0,
            stdout="captured all scenarios\n",
            stderr=diagnostics,
        )
        commands = [
            (
                "platform_screenshots",
                ("fake-screenshot-capture",),
                {},
            )
        ]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch(
                "scripts.verify_luminous_interface._qmllint_executable",
                return_value="qmllint",
            ), mock.patch(
                "scripts.verify_luminous_interface.verification_commands",
                return_value=commands,
            ), mock.patch(
                "scripts.verify_luminous_interface.subprocess.run",
                return_value=completed,
            ), mock.patch("sys.stderr", new=io.StringIO()) as stderr:
                self.assertEqual(run_verification(output), 1)

            self.assertIn("FAILED: platform_screenshots", stderr.getvalue())
            report = json.loads(
                (output / "verification-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["automated_status"], "failed")
            self.assertEqual(report["failed_step"], "platform_screenshots")
            self.assertEqual(
                report["steps"][0]["runtime_qml_warnings"],
                diagnostics.splitlines(),
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
            dispose_qml_fixture(
                self.qapp,
                engine,
                roots=(theme,),
                components=(component,),
            )

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
            "home-system-high-contrast-divergent-640x520-200",
            "hud-error-high-contrast-large-200",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            output.mkdir()
            stale_managed = output / "home-dark-full-960x700-100.png"
            retired_managed = output / "retired-scenario.png"
            unrelated = output / "review-notes.txt"
            outside = output.parent / "outside.png"
            stale_managed.write_bytes(b"stale")
            retired_managed.write_bytes(b"retired")
            unrelated.write_text("keep", encoding="utf-8")
            outside.write_bytes(b"outside")
            (output / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "scenarios": [
                            {
                                "name": "retired-scenario",
                                "file": "retired-scenario.png",
                            },
                            {"name": "outside", "file": "../outside.png"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            first = capture_scenarios(output, names)
            second = capture_scenarios(output, names)
            self.assertEqual(first, second)
            self.assertEqual(first["schema_version"], 2)
            self.assertEqual(len(first["scenarios"]), len(names))
            self.assertIn(first["platform"]["qpa"], {"offscreen", "windows", "cocoa"})
            self.assertEqual(
                first["platform"]["effective_renderer_apis"], ["Software"]
            )
            self.assertEqual(
                first["platform"]["qt_quick_backend_request"], "software"
            )
            self.assertNotIn("qt_quick_backend", first["platform"])
            self.assertFalse(stale_managed.exists())
            self.assertFalse(retired_managed.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")
            self.assertEqual(outside.read_bytes(), b"outside")
            self.assertEqual(
                {path.name for path in output.glob("*.png")},
                {artifact["file"] for artifact in first["scenarios"]},
            )
            self.assertIn("does_not_prove", first["capture_scope"])
            system_high_contrast = next(
                artifact
                for artifact in first["scenarios"]
                if artifact["name"].startswith("home-system-high-contrast")
            )
            self.assertTrue(
                system_high_contrast["simulated_system_high_contrast"]
            )
            for artifact in first["scenarios"]:
                self.assertEqual(artifact["qml_warnings"], [])
                self.assertEqual(artifact["renderer_api"], "Software")
                self.assertEqual(len(artifact["sha256"]), 64)
                self.assertGreater(artifact["width"], 0)
                self.assertGreater(artifact["height"], 0)
                self.assertGreater((output / artifact["file"]).stat().st_size, 100)

    def test_capture_tool_preserves_the_callers_qpa_choice(self):
        probe = (
            "import os; import scripts.capture_ui_verification; "
            "print(os.environ.get('QT_QPA_PLATFORM', '<unset>'))"
        )
        environment = os.environ.copy()
        environment.pop("QT_QPA_PLATFORM", None)
        native = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(native.returncode, 0, native.stderr)
        self.assertEqual(native.stdout.strip(), "<unset>")

        environment["QT_QPA_PLATFORM"] = "offscreen"
        offscreen = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(offscreen.returncode, 0, offscreen.stderr)
        self.assertEqual(offscreen.stdout.strip(), "offscreen")

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
            from tests.qml_lifecycle import dispose_qml_fixture
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
            warnings = []
            engine.warnings.connect(
                lambda values: warnings.extend(error.toString() for error in values)
            )
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
            ok = False
            try:
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
            finally:
                controller.detach()
                dispose_qml_fixture(
                    application,
                    engine,
                    components=(component,),
                    context_objects=(bridge, controller),
                )
            if warnings:
                print("QML warnings: " + "; ".join(warnings), file=sys.stderr)
            sys.exit(0 if ok and not warnings else 3)
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
        self.assertEqual(
            detect_qml_runtime_warnings(result.stdout + "\n" + result.stderr),
            [],
            "The Windows fallback child emitted a swallowed QML diagnostic",
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows QPA maximize proof")
    def test_windows_real_qpa_custom_maximize_changes_hwnd_and_restores(self):
        script = textwrap.dedent(
            f"""
            import ctypes
            from ctypes import wintypes
            import os
            import sys
            from pathlib import Path

            os.environ["QT_QPA_PLATFORM"] = "windows"
            os.environ["QT_QUICK_BACKEND"] = "software"
            os.environ["QSG_RHI_BACKEND"] = "software"

            from PySide6.QtCore import QMetaObject, QObject, Qt
            from PySide6.QtQml import QQmlApplicationEngine
            from PySide6.QtQuickControls2 import QQuickStyle
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication

            from speakr import native_window, qt_ui
            from speakr.qt_ui import Bridge
            from scripts.verify_luminous_interface import native_rect_matches_work_area
            from tests.qml_lifecycle import dispose_qml_fixture
            from tests.test_qml_load import _App

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            def fail(code, message):
                print(f"Win32 maximize proof {{code}}: {{message}}", file=sys.stderr)
                raise SystemExit(code)

            def native_rect(hwnd):
                value = wintypes.RECT()
                if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(value)):
                    fail(10, "GetWindowRect failed")
                return (value.left, value.top, value.right, value.bottom)

            def work_rect(hwnd):
                monitor = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)
                if not monitor:
                    fail(11, "MonitorFromWindow failed")
                value = MONITORINFO()
                value.cbSize = ctypes.sizeof(value)
                if not user32.GetMonitorInfoW(monitor, ctypes.byref(value)):
                    fail(12, "GetMonitorInfoW failed")
                return (
                    value.rcWork.left,
                    value.rcWork.top,
                    value.rcWork.right,
                    value.rcWork.bottom,
                )

            def metric(index, hwnd):
                get_dpi = getattr(user32, "GetDpiForWindow", None)
                get_metric_for_dpi = getattr(user32, "GetSystemMetricsForDpi", None)
                if callable(get_dpi) and callable(get_metric_for_dpi):
                    try:
                        dpi = int(get_dpi(ctypes.c_void_p(hwnd)) or 96)
                        return int(get_metric_for_dpi(index, dpi))
                    except (OSError, TypeError, ValueError):
                        pass
                return int(user32.GetSystemMetrics(index))

            QQuickStyle.setStyle("Basic")
            application = QApplication([])
            if application.platformName() != "windows":
                sys.exit(2)
            user32 = ctypes.windll.user32
            user32.IsZoomed.restype = wintypes.BOOL
            user32.MonitorFromWindow.restype = wintypes.HANDLE
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
            warnings = []
            engine.warnings.connect(
                lambda values: warnings.extend(error.toString() for error in values)
            )
            main, component = qt_ui._create_qml_root(
                qt,
                engine,
                Path({str(self.qml / 'Main.qml')!r}),
                before_complete=controller.attach,
            )
            try:
                screen = application.primaryScreen()
                if screen is None:
                    fail(3, "no primary screen")
                available = screen.availableGeometry()
                width = min(800, max(640, available.width() - 160))
                height = min(600, max(520, available.height() - 160))
                x = available.x() + max(0, (available.width() - width) // 2)
                y = available.y() + max(0, (available.height() - height) // 2)
                main.setGeometry(x, y, width, height)
                main.show()
                QTest.qWait(180)

                button = main.findChild(QObject, "maximizeWindowButton")
                if button is None or not controller.customChromeEnabled:
                    fail(4, "custom maximize button was unavailable")
                original_logical = tuple(main.geometry().getRect())
                hwnd = int(main.winId())
                if not hwnd or user32.IsZoomed(ctypes.c_void_p(hwnd)):
                    fail(5, "window did not begin in a normal Win32 state")
                original_native = native_rect(hwnd)

                if not QMetaObject.invokeMethod(button, "click"):
                    fail(6, "maximize button invocation failed")
                QTest.qWait(260)
                maximized_logical = tuple(main.geometry().getRect())
                maximized_native = native_rect(hwnd)
                work = work_rect(hwnd)
                horizontal_frame = (
                    metric(32, hwnd) + metric(92, hwnd) + 2
                )
                vertical_frame = (
                    metric(33, hwnd) + metric(92, hwnd) + 2
                )
                state = main.windowStates()
                maximize_ok = (
                    bool(user32.IsZoomed(ctypes.c_void_p(hwnd)))
                    and controller.maximized
                    and bool(state & Qt.WindowState.WindowMaximized)
                    and button.property("windowAction") == "restore"
                    and maximized_logical != original_logical
                    and maximized_native != original_native
                    and native_rect_matches_work_area(
                        maximized_native,
                        work,
                        horizontal_frame,
                        vertical_frame,
                    )
                )
                if not maximize_ok:
                    fail(
                        7,
                        f"unexpected maximize state: state={{int(state.value)}}, "
                        f"visibility={{main.visibility()}}, native={{maximized_native}}, "
                        f"work={{work}}",
                    )

                if not QMetaObject.invokeMethod(button, "click"):
                    fail(8, "restore button invocation failed")
                QTest.qWait(260)
                restored_state = main.windowStates()
                restore_ok = (
                    not bool(user32.IsZoomed(ctypes.c_void_p(hwnd)))
                    and not controller.maximized
                    and not bool(restored_state & Qt.WindowState.WindowMaximized)
                    and not bool(restored_state & Qt.WindowState.WindowFullScreen)
                    and button.property("windowAction") == "maximize"
                    and tuple(main.geometry().getRect()) == original_logical
                    and native_rect(hwnd) == original_native
                )
                if not restore_ok:
                    fail(
                        9,
                        f"restore was not exact: state={{int(restored_state.value)}}, "
                        f"logical={{tuple(main.geometry().getRect())}}, "
                        f"native={{native_rect(hwnd)}}",
                    )
            finally:
                controller.detach()
                dispose_qml_fixture(
                    application,
                    engine,
                    components=(component,),
                    context_objects=(bridge, controller),
                )
                if warnings:
                    print("QML warnings: " + "; ".join(warnings), file=sys.stderr)
                    raise SystemExit(13)
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
        self.assertEqual(
            detect_qml_runtime_warnings(result.stdout + "\n" + result.stderr),
            [],
            "The Win32 maximize child emitted a swallowed QML diagnostic",
        )


if __name__ == "__main__":
    unittest.main()
