from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from speakr import native_window
from speakr.interface_state import InterfaceState


class EffectResolutionTests(unittest.TestCase):
    def test_resolution_priority_and_native_materials(self):
        cases = (
            (
                {"visual_effects": "full", "high_contrast": True},
                ("off", "solid"),
            ),
            (
                {"visual_effects": "off"},
                ("off", "solid"),
            ),
            (
                {"visual_effects": "full", "reduce_transparency": True},
                ("reduced", "scene_glass"),
            ),
            (
                {"visual_effects": "system", "software_renderer": True},
                ("reduced", "scene_glass"),
            ),
            (
                {"visual_effects": "reduced"},
                ("reduced", "scene_glass"),
            ),
            (
                {
                    "visual_effects": "full",
                    "platform_name": "win32",
                    "native_material_available": True,
                },
                ("full", "mica"),
            ),
            (
                {
                    "visual_effects": "system",
                    "platform_name": "darwin",
                    "native_material_available": True,
                },
                ("full", "vibrancy"),
            ),
            (
                {"visual_effects": "unknown", "platform_name": "linux"},
                ("full", "scene_glass"),
            ),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                result = native_window.resolve_effects(**arguments)
                self.assertEqual((result.effect_tier, result.material), expected)

    def test_module_import_does_not_load_qt_or_pyobjc(self):
        repo = Path(__file__).resolve().parents[1]
        code = (
            "import sys; import speakr.native_window; "
            "assert not any(k == 'PySide6' or k.startswith('PySide6.') for k in sys.modules); "
            "assert 'AppKit' not in sys.modules and 'objc' not in sys.modules"
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repo)
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_explicit_qt_software_backend_is_detected(self):
        from speakr import qt_ui

        with mock.patch.dict(os.environ, {"QT_QUICK_BACKEND": "software"}, clear=False):
            self.assertTrue(qt_ui._prefer_software_renderer())


class HitRegionTests(unittest.TestCase):
    def setUp(self):
        self.regions = native_window.normalize_hit_regions(
            {"x": 0, "y": 0, "width": 800, "height": 48},
            (650, 0, 50, 48),
            (700, 0, 50, 48),
            (750, 0, 50, 48),
            8,
        )

    def test_controls_caption_and_resize_edges_have_stable_precedence(self):
        self.assertEqual(
            native_window.windows_hit_test(775, 24, 800, 600, self.regions),
            native_window.HTCLOSE,
        )
        self.assertEqual(
            native_window.windows_hit_test(725, 24, 800, 600, self.regions),
            native_window.HTMAXBUTTON,
        )
        self.assertEqual(
            native_window.windows_hit_test(675, 24, 800, 600, self.regions),
            native_window.HTMINBUTTON,
        )
        self.assertEqual(
            native_window.windows_hit_test(400, 24, 800, 600, self.regions),
            native_window.HTCAPTION,
        )
        self.assertEqual(
            native_window.windows_hit_test(2, 2, 800, 600, self.regions),
            native_window.HTTOPLEFT,
        )
        self.assertEqual(
            native_window.windows_hit_test(799, 599, 800, 600, self.regions),
            native_window.HTBOTTOMRIGHT,
        )

    def test_maximized_window_disables_resize_regions(self):
        self.assertEqual(
            native_window.windows_hit_test(
                2, 2, 800, 600, self.regions, maximized=True
            ),
            native_window.HTCAPTION,
        )

    def test_invalid_regions_are_neutral_and_border_is_bounded(self):
        regions = native_window.normalize_hit_regions(
            {"width": -1}, None, None, None, 500
        )
        self.assertIsNone(regions["titlebar"])
        self.assertEqual(regions["resize_border"], 32.0)
        self.assertEqual(
            native_window.windows_hit_test("bad", 2, 100, 100, regions),
            native_window.HTCLIENT,
        )


class WindowsAdapterTests(unittest.TestCase):
    class _Dwm:
        def __init__(self, backdrop_result=0):
            self.backdrop_result = backdrop_result
            self.calls = []

        def DwmSetWindowAttribute(self, hwnd, attribute, value, _size):
            import ctypes

            number = ctypes.cast(value, ctypes.POINTER(ctypes.c_int)).contents.value
            attr = int(getattr(attribute, "value", attribute))
            handle = int(getattr(hwnd, "value", hwnd) or 0)
            self.calls.append((handle, attr, number))
            if attr == native_window._WindowsAdapter._DWMWA_SYSTEMBACKDROP_TYPE:
                return self.backdrop_result
            return 0

    class _Window:
        @staticmethod
        def winId():
            return 1234

    def test_supported_build_applies_dark_mode_corners_and_mica(self):
        dwm = self._Dwm()
        adapter = native_window._WindowsAdapter(build=22621, dwmapi=dwm)

        self.assertTrue(adapter.native_available())
        self.assertTrue(adapter.apply_material(self._Window(), "dark"))
        self.assertIn((1234, 20, 1), dwm.calls)
        self.assertIn((1234, 33, 2), dwm.calls)
        self.assertIn((1234, 38, 2), dwm.calls)

        adapter.restore_material()
        self.assertIn((1234, 38, 1), dwm.calls)

    def test_detach_restores_all_dwm_attributes_and_forgets_handle(self):
        dwm = self._Dwm()
        adapter = native_window._WindowsAdapter(build=22621, dwmapi=dwm)
        self.assertTrue(adapter.apply_material(self._Window(), "dark"))

        adapter.detach()

        self.assertIn((1234, 38, 1), dwm.calls)
        self.assertIn((1234, 33, 0), dwm.calls)
        self.assertIn((1234, 20, 0), dwm.calls)
        self.assertEqual(adapter._hwnd, 0)

    def test_old_build_or_failed_backdrop_never_claims_mica(self):
        old = native_window._WindowsAdapter(build=22000, dwmapi=self._Dwm())
        self.assertFalse(old.native_available())
        self.assertFalse(old.apply_material(self._Window(), "light"))

        failed = native_window._WindowsAdapter(
            build=22621, dwmapi=self._Dwm(backdrop_result=-1)
        )
        self.assertFalse(failed.apply_material(self._Window(), "light"))


class MacAdapterTests(unittest.TestCase):
    def test_capability_is_lazy_and_requires_visual_effect_view(self):
        available = native_window._MacAdapter(
            appkit=SimpleNamespace(NSVisualEffectView=object()),
            objc_module=object(),
        )
        missing = native_window._MacAdapter(
            appkit=SimpleNamespace(),
            objc_module=object(),
        )

        self.assertTrue(available.native_available())
        self.assertFalse(missing.native_available())

    def test_reapplying_vibrancy_does_not_stack_effect_views(self):
        class Effect:
            allocations = 0

            @classmethod
            def alloc(cls):
                cls.allocations += 1
                return cls()

            def initWithFrame_(self, _frame): return self
            def setAutoresizingMask_(self, _value): pass
            def setBlendingMode_(self, _value): pass
            def setMaterial_(self, _value): pass
            def setState_(self, _value): pass
            def removeFromSuperview(self): pass

        class Content:
            def __init__(self): self.added = 0
            def bounds(self): return (0, 0, 100, 100)
            def addSubview_positioned_relativeTo_(self, *_args): self.added += 1

        class Native:
            def __init__(self): self.content = Content()
            def contentView(self): return self.content
            def isOpaque(self): return True
            def backgroundColor(self): return "original"
            def setOpaque_(self, _value): pass
            def setBackgroundColor_(self, _value): pass

        native = Native()
        view = SimpleNamespace(window=lambda: native)
        objc_module = SimpleNamespace(objc_object=lambda **_kwargs: view)
        appkit = SimpleNamespace(
            NSVisualEffectView=Effect,
            NSViewWidthSizable=1,
            NSViewHeightSizable=2,
            NSVisualEffectBlendingModeBehindWindow=0,
            NSVisualEffectMaterialUnderWindowBackground=21,
            NSVisualEffectStateActive=1,
            NSWindowBelow=-1,
            NSColor=SimpleNamespace(clearColor=lambda: "clear"),
        )
        adapter = native_window._MacAdapter(
            appkit=appkit, objc_module=objc_module
        )
        window = SimpleNamespace(winId=lambda: 123)

        self.assertTrue(adapter.apply_material(window, "dark"))
        self.assertTrue(adapter.apply_material(window, "light"))
        self.assertEqual(Effect.allocations, 1)
        self.assertEqual(native.content.added, 1)

    def test_failed_material_cleanup_keeps_state_for_retry(self):
        class Effect:
            def __init__(self): self.failures = 1
            def removeFromSuperview(self):
                if self.failures:
                    self.failures -= 1
                    raise RuntimeError("transient remove failure")

        class Native:
            def __init__(self):
                self.opacity = []
                self.backgrounds = []
            def setOpaque_(self, value): self.opacity.append(value)
            def setBackgroundColor_(self, value): self.backgrounds.append(value)

        adapter = native_window._MacAdapter(
            appkit=SimpleNamespace(NSVisualEffectView=object()),
            objc_module=object(),
        )
        effect = Effect()
        native = Native()
        adapter._effect_view = effect
        adapter._native_window = native
        adapter._was_opaque = True
        adapter._background_color = "original"

        self.assertFalse(adapter.restore_material())
        self.assertIs(adapter._effect_view, effect)
        self.assertEqual(adapter._background_color, "original")

        self.assertTrue(adapter.restore_material())
        self.assertIsNone(adapter._effect_view)
        self.assertIsNone(adapter._was_opaque)
        self.assertIsNone(adapter._background_color)

    def test_failed_chrome_cleanup_keeps_state_for_retry(self):
        class Button:
            def __init__(self): self.hidden = None
            def setHidden_(self, value): self.hidden = value

        class Native:
            def __init__(self):
                self.style_failures = 1
                self.button = Button()
            def setStyleMask_(self, _value):
                if self.style_failures:
                    self.style_failures -= 1
                    raise RuntimeError("transient style failure")
            def setTitlebarAppearsTransparent_(self, _value): pass
            def setTitleVisibility_(self, _value): pass
            def standardWindowButton_(self, _kind): return self.button

        adapter = native_window._MacAdapter(
            appkit=SimpleNamespace(NSVisualEffectView=object()),
            objc_module=object(),
        )
        native = Native()
        state = (15, False, 0, [(1, False)])
        adapter._native_window = native
        adapter._chrome_state = state

        self.assertFalse(adapter.restore_custom_chrome(None))
        self.assertIs(adapter._chrome_state, state)

        self.assertTrue(adapter.restore_custom_chrome(None))
        self.assertIsNone(adapter._chrome_state)
        self.assertFalse(native.button.hidden)


try:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtWidgets import QApplication

    from speakr import qt_ui

    _QT_AVAILABLE = qt_ui.qt_available()
except (ImportError, OSError):
    _QT_AVAILABLE = False


class _FakeAdapter:
    def __init__(self, *, available=True, material_succeeds=True, chrome_succeeds=True):
        self.available = available
        self.material_succeeds = material_succeeds
        self.chrome_succeeds = chrome_succeeds
        self.applied = []
        self.restored = 0
        self.chrome_calls = 0

    def native_available(self):
        return self.available

    def apply_material(self, window, theme):
        self.applied.append((window, theme))
        return self.material_succeeds

    def restore_material(self):
        self.restored += 1

    def enable_custom_chrome(self, _window):
        self.chrome_calls += 1
        return self.chrome_succeeds

    @staticmethod
    def restore_custom_chrome(_window):
        return None

    @staticmethod
    def show_system_menu(_window, _x, _y):
        return False

    def detach(self):
        self.restore_material()


@unittest.skipUnless(_QT_AVAILABLE, "PySide6-Essentials is optional")
class NativeControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])
        cls.qt = qt_ui._load_qt()

    def test_controller_exposes_contract_and_keeps_system_frame_without_opt_in(self):
        adapter = _FakeAdapter()
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="full",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        original = window.flags()
        try:
            self.assertTrue(controller.attach(window))
            self.assertEqual(controller.material, "mica")
            self.assertEqual(controller.effectTier, "full")
            self.assertTrue(controller.nativeMaterialAvailable)
            self.assertFalse(controller.customChromeEnabled)
            self.assertEqual(window.flags(), original)
            self.assertEqual(adapter.chrome_calls, 0)
            for name in (
                "material",
                "effectTier",
                "customChromeEnabled",
                "nativeMaterialAvailable",
                "systemReduceTransparency",
                "softwareRenderer",
                "maximized",
                "active",
            ):
                self.assertGreaterEqual(controller.metaObject().indexOfProperty(name), 0)
        finally:
            controller.detach()
            window.deleteLater()

    def test_native_failure_and_accessibility_preferences_fall_back_safely(self):
        adapter = _FakeAdapter(material_succeeds=False)
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="full",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        try:
            controller.attach(window)
            self.assertEqual(controller.material, "scene_glass")
            self.assertFalse(controller.nativeMaterialAvailable)

            controller.update_environment(
                high_contrast=True, reduce_transparency=False
            )
            self.assertEqual(controller.effectTier, "off")
            self.assertEqual(controller.material, "solid")

            controller.update_environment(
                high_contrast=False, reduce_transparency=True
            )
            self.assertEqual(controller.effectTier, "reduced")
            self.assertEqual(controller.material, "scene_glass")
            self.assertTrue(controller.systemReduceTransparency)
        finally:
            controller.detach()
            window.deleteLater()

    def test_explicit_high_contrast_theme_forces_solid_effects_off(self):
        adapter = _FakeAdapter()
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="full",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        try:
            controller.attach(window)
            self.assertEqual(controller.material, "mica")

            qt_ui._apply_native_preferences(
                controller,
                self.qt,
                {
                    "ui": {"theme": "high_contrast", "visual_effects": "full"},
                    "system_high_contrast": False,
                    "system_reduce_transparency": False,
                },
            )

            self.assertEqual(controller.effectTier, "off")
            self.assertEqual(controller.material, "solid")
        finally:
            controller.detach()
            window.deleteLater()

    def test_custom_chrome_failure_restores_normal_window_flags(self):
        adapter = _FakeAdapter(chrome_succeeds=False)
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        original = window.flags()
        try:
            self.assertTrue(controller.attach(window))
            self.assertEqual(adapter.chrome_calls, 1)
            self.assertFalse(controller.customChromeEnabled)
            self.assertEqual(window.flags(), original)
            self.assertEqual(controller.material, "solid")
        finally:
            controller.detach()
            window.deleteLater()

    def test_unsupported_platform_never_claims_custom_chrome(self):
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="unsupported",
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        original = window.flags()
        try:
            self.assertTrue(controller.attach(window))
            self.assertFalse(controller.customChromeEnabled)
            self.assertEqual(window.flags(), original)
        finally:
            controller.detach()
            window.deleteLater()

    def test_qml_main_root_attaches_before_component_completion_can_show_it(self):
        adapter = _FakeAdapter(available=False)
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="full",
            platform_name="test",
            adapter=adapter,
        )
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("nativeWindow", controller)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AttachProbe.qml"
            path.write_text(
                """
import QtQuick
import QtQuick.Window
Window {
    visible: false
    property bool attachedBeforeCompletion: false
    Component.onCompleted: {
        attachedBeforeCompletion = nativeWindow.material === "scene_glass"
        visible = true
    }
}
""",
                encoding="utf-8",
            )
            root = component = None
            try:
                root, component = qt_ui._create_qml_root(
                    self.qt, engine, path, before_complete=controller.attach
                )
                self.qapp.processEvents()
                self.assertTrue(root.property("attachedBeforeCompletion"))
                self.assertTrue(root.isVisible())
                self.assertFalse(controller.customChromeEnabled)
            finally:
                controller.detach()
                if root is not None:
                    root.close()
                    root.deleteLater()
                if component is not None:
                    component.deleteLater()
                engine.deleteLater()
                self.qapp.processEvents()

    def test_macos_reduce_transparency_preference_is_published(self):
        def defaults_result(command, **_kwargs):
            key = command[-1]
            return SimpleNamespace(
                stdout="1\n" if key in {"reduceTransparency", "reduceMotion"} else "0\n"
            )

        previous = qt_ui._SYSTEM_ACCESSIBILITY
        try:
            qt_ui._SYSTEM_ACCESSIBILITY = None
            with mock.patch.object(qt_ui.sys, "platform", "darwin"), mock.patch.object(
                qt_ui.subprocess, "run", side_effect=defaults_result
            ):
                preferences = qt_ui._system_accessibility_preferences()
            self.assertTrue(preferences["system_reduce_transparency"])
            self.assertTrue(preferences["system_reduced_motion"])
            self.assertFalse(preferences["system_high_contrast"])
        finally:
            qt_ui._SYSTEM_ACCESSIBILITY = previous

    def test_native_ui_disconnects_system_callbacks_before_teardown(self):
        class App:
            def __init__(self):
                self.interface_state = InterfaceState(
                    {"availability": "ready", "enabled": True}
                )
                self.enabled = True
                self._qt_frontend = None

            @staticmethod
            def settings_snapshot():
                return {
                    "ui": {
                        "onboarding_complete": True,
                        "open_window_on_start": False,
                        "theme": "system",
                        "visual_effects": "off",
                        "density": "comfortable",
                        "text_scale": "system",
                        "reduced_motion": "reduce",
                        "hud_visibility": "off",
                        "hud_size": "standard",
                        "hud_edge": "bottom",
                        "hud_scale": 100,
                        "background_announcements": False,
                    },
                    "hotkey": "right ctrl",
                    "toggle_mode": False,
                    "app_tones": {},
                    "hotkey_exclude_apps": [],
                }

            @staticmethod
            def practice_snapshot(): return {}
            @staticmethod
            def list_manual_words(): return []
            @staticmethod
            def list_learned_words(): return []
            @staticmethod
            def subscribe_settings(_callback): return lambda: None
            @staticmethod
            def subscribe_practice(_callback): return lambda: None

            def _start_core(self):
                QApplication.instance().quit()

        accessibility = {
            "system_high_contrast": False,
            "system_reduced_motion": False,
            "system_reduce_transparency": False,
        }
        with mock.patch.object(
            qt_ui,
            "_system_accessibility_preferences",
            return_value=accessibility,
        ) as preferences:
            self.assertEqual(qt_ui.run_native_ui(App()), 0)
            calls_after_cleanup = preferences.call_count

            self.qapp.paletteChanged.emit(self.qapp.palette())
            self.qapp.applicationStateChanged.emit(
                self.qt.Qt.ApplicationState.ApplicationActive
            )
            self.qapp.processEvents()

            self.assertEqual(preferences.call_count, calls_after_cleanup)

            with mock.patch.object(
                qt_ui,
                "_create_qml_root",
                side_effect=qt_ui.QtUnavailable("synthetic QML failure"),
            ):
                with self.assertRaises(qt_ui.QtUnavailable):
                    qt_ui.run_native_ui(App())
            calls_after_failed_startup = preferences.call_count

            self.qapp.paletteChanged.emit(self.qapp.palette())
            self.qapp.applicationStateChanged.emit(
                self.qt.Qt.ApplicationState.ApplicationActive
            )
            self.qapp.processEvents()

            self.assertEqual(preferences.call_count, calls_after_failed_startup)


if __name__ == "__main__":
    unittest.main()
