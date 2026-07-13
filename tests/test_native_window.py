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

    class _User32:
        def __init__(self, style=0x86000000):
            self.style = style
            self.style_writes = []
            self.frame_refreshes = []
            self.show_commands = []
            self.zoomed = False
            self.iconic = False

        @staticmethod
        def _value(value):
            return int(getattr(value, "value", value) or 0)

        def GetWindowLongPtrW(self, _hwnd, _index):
            return self.style

        def SetWindowLongPtrW(self, _hwnd, _index, style):
            previous = self.style
            self.style = self._value(style) & 0xFFFFFFFF
            self.style_writes.append(self.style)
            return previous

        def SetWindowPos(self, _hwnd, _after, _x, _y, _width, _height, flags):
            self.frame_refreshes.append(self._value(flags))
            return 1

        def ShowWindow(self, _hwnd, command):
            command = self._value(command)
            self.show_commands.append(command)
            if command == native_window._WindowsAdapter._SW_MAXIMIZE:
                self.zoomed = True
                self.iconic = False
            elif command == native_window._WindowsAdapter._SW_RESTORE:
                self.zoomed = False
                self.iconic = False
            elif command == native_window._WindowsAdapter._SW_MINIMIZE:
                self.iconic = True
            return 1

        def IsZoomed(self, _hwnd):
            return int(self.zoomed)

        def IsIconic(self, _hwnd):
            return int(self.iconic)

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

    def test_custom_chrome_readds_native_system_styles_and_restores_them(self):
        original_style = 0x86000000
        user32 = self._User32(original_style)
        adapter = native_window._WindowsAdapter(build=0, user32=user32)

        self.assertTrue(adapter.enable_custom_chrome(self._Window()))
        self.assertEqual(
            user32.style & adapter._CUSTOM_CHROME_STYLES,
            adapter._CUSTOM_CHROME_STYLES,
        )
        self.assertTrue(
            user32.frame_refreshes[-1] & adapter._SWP_FRAMECHANGED
        )

        self.assertTrue(adapter.restore_custom_chrome(self._Window()))
        self.assertEqual(user32.style, original_style)
        self.assertIsNone(adapter._original_style)
        self.assertEqual(adapter._chrome_hwnd, 0)

    def test_native_window_state_uses_showwindow_and_iszoomed(self):
        user32 = self._User32()
        adapter = native_window._WindowsAdapter(build=0, user32=user32)
        window = self._Window()

        self.assertFalse(adapter.is_maximized(window))
        self.assertTrue(adapter.set_maximized(window, True))
        self.assertTrue(adapter.is_maximized(window))
        self.assertEqual(user32.show_commands, [adapter._SW_MAXIMIZE])

        self.assertTrue(adapter.set_maximized(window, True))
        self.assertEqual(user32.show_commands, [adapter._SW_MAXIMIZE])

        self.assertTrue(adapter.set_maximized(window, False))
        self.assertFalse(adapter.is_maximized(window))
        self.assertEqual(
            user32.show_commands, [adapter._SW_MAXIMIZE, adapter._SW_RESTORE]
        )

        self.assertTrue(adapter.minimize_window(window))
        self.assertEqual(user32.show_commands[-1], adapter._SW_MINIMIZE)

    @unittest.skipUnless(sys.platform == "win32", "requires a real Win32 HWND")
    def test_real_qt_window_keeps_native_styles_and_restores_system_frame(self):
        repo = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repo)
        environment["QT_QPA_PLATFORM"] = "windows"
        environment["QT_QUICK_BACKEND"] = "software"
        code = r'''
import ctypes
from unittest import mock
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication
from speakr.native_window import NativeWindowController, _WindowsAdapter

application = QApplication([])
window = QQuickWindow()
window.setProperty("customChromeReady", True)
original_flags = window.flags()
original_hwnd = int(window.winId())
user32 = ctypes.windll.user32
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
original_style = int(user32.GetWindowLongPtrW(ctypes.c_void_p(original_hwnd), -16)) & 0xFFFFFFFF

adapter = _WindowsAdapter(build=0)
controller = NativeWindowController(
    visual_effects="off", platform_name="win32", adapter=adapter
)
assert controller.attach(window)
assert controller.customChromeEnabled
active_hwnd = int(window.winId())
active_style = int(user32.GetWindowLongPtrW(ctypes.c_void_p(active_hwnd), -16)) & 0xFFFFFFFF
required = 0x00080000 | 0x00040000 | 0x00020000 | 0x00010000
assert active_style & required == required, hex(active_style)

controller.detach()
restored_hwnd = int(window.winId())
restored_style = int(user32.GetWindowLongPtrW(ctypes.c_void_p(restored_hwnd), -16)) & 0xFFFFFFFF
assert window.flags() == original_flags
assert restored_style & required == original_style & required, (
    hex(original_style), hex(restored_style)
)

fallback_adapter = _WindowsAdapter(build=0)
fallback = NativeWindowController(
    visual_effects="off", platform_name="win32", adapter=fallback_adapter
)
with mock.patch.object(
    type(fallback), "_install_windows_hit_filter", return_value=False
):
    assert fallback.attach(window)
assert not fallback.customChromeEnabled
fallback_hwnd = int(window.winId())
fallback_style = int(user32.GetWindowLongPtrW(ctypes.c_void_p(fallback_hwnd), -16)) & 0xFFFFFFFF
assert window.flags() == original_flags
assert fallback_style & required == original_style & required, (
    hex(original_style), hex(fallback_style)
)
fallback.detach()
window.deleteLater()
application.processEvents()
'''
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(sys.platform == "win32", "requires a real Win32 HWND")
    def test_production_main_button_native_maximizes_and_restores_exactly(self):
        repo = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repo)
        environment["QT_QPA_PLATFORM"] = "windows"
        environment["QT_QUICK_BACKEND"] = "software"
        code = r'''
import ctypes
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from speakr.native_window import NativeWindowController, _WindowsAdapter
from speakr.qt_ui import Bridge, _create_qml_root, _load_qt
from tests.test_qml_load import _App


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def pump(milliseconds=120):
    QTest.qWait(milliseconds)
    application.processEvents()


def native_rect(hwnd):
    value = wintypes.RECT()
    assert user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(value))
    return (value.left, value.top, value.right, value.bottom)


def work_rect(hwnd):
    monitor = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)
    assert monitor
    value = MONITORINFO()
    value.cbSize = ctypes.sizeof(value)
    assert user32.GetMonitorInfoW(monitor, ctypes.byref(value))
    return (
        value.rcWork.left,
        value.rcWork.top,
        value.rcWork.right,
        value.rcWork.bottom,
    )


def click_maximize_button(main):
    button = main.findChild(QObject, "maximizeWindowButton")
    assert button is not None
    scene = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    QTest.mouseClick(
        main,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(scene.x()), round(scene.y())),
    )
    pump(350)
    return button


QQuickStyle.setStyle("Basic")
application = QApplication([])
application.setQuitOnLastWindowClosed(False)
qt = _load_qt()
user32 = ctypes.windll.user32
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.MonitorFromWindow.restype = wintypes.HANDLE

fixture = _App()
bridge = Bridge(fixture)
controller = NativeWindowController(
    qt=qt,
    visual_effects="off",
    platform_name="win32",
    adapter=_WindowsAdapter(build=0),
)
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("bridge", bridge)
engine.rootContext().setContextProperty("nativeWindow", controller)
warnings = []
engine.warnings.connect(
    lambda values: warnings.extend(error.toString() for error in values)
)
main, component = _create_qml_root(
    qt,
    engine,
    Path.cwd() / "speakr" / "ui" / "qml" / "Main.qml",
    before_complete=controller.attach,
)
main.setX(120)
main.setY(80)
main.setWidth(960)
main.setHeight(700)
main.show()
pump(300)
assert controller.customChromeEnabled
assert not hasattr(main, "isMaximized")
hwnd = int(main.winId())
normal_geometry = tuple(main.geometry().getRect())
normal_native = native_rect(hwnd)

button = click_maximize_button(main)
assert user32.IsZoomed(ctypes.c_void_p(hwnd))
assert controller.maximized
assert button.property("windowAction") == "restore"
maximized_geometry = tuple(main.geometry().getRect())
maximized_native = native_rect(hwnd)
assert maximized_geometry != normal_geometry
assert maximized_native != normal_native

work = work_rect(hwnd)
horizontal_frame = user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92) + 2
vertical_frame = user32.GetSystemMetrics(33) + user32.GetSystemMetrics(92) + 2
assert maximized_native[0] >= work[0] - horizontal_frame, (maximized_native, work)
assert maximized_native[1] >= work[1] - vertical_frame, (maximized_native, work)
assert maximized_native[2] <= work[2] + horizontal_frame, (maximized_native, work)
assert maximized_native[3] <= work[3] + vertical_frame, (maximized_native, work)

button = click_maximize_button(main)
assert not user32.IsZoomed(ctypes.c_void_p(hwnd))
assert not controller.maximized
assert button.property("windowAction") == "maximize"
assert tuple(main.geometry().getRect()) == normal_geometry
assert native_rect(hwnd) == normal_native

# A normal system-framed QWindow keeps Qt's supported maximize path.
system_window = QQuickWindow()
system_window.resize(720, 540)
system_window.setPosition(180, 120)
system_controller = NativeWindowController(
    visual_effects="off",
    platform_name="win32",
    adapter=_WindowsAdapter(build=0),
)
assert system_controller.attach(system_window)
assert not system_controller.customChromeEnabled
system_window.show()
pump(200)
system_hwnd = int(system_window.winId())
system_normal_geometry = tuple(system_window.geometry().getRect())
system_controller.toggleMaximize()
pump(300)
assert user32.IsZoomed(ctypes.c_void_p(system_hwnd))
assert system_controller.maximized
system_controller.toggleMaximize()
pump(300)
assert not user32.IsZoomed(ctypes.c_void_p(system_hwnd))
assert not system_controller.maximized
assert tuple(system_window.geometry().getRect()) == system_normal_geometry

assert warnings == [], warnings
system_window.hide()
system_controller.detach()
main.hide()
controller.detach()
bridge.close()
system_window.deleteLater()
main.deleteLater()
component.deleteLater()
engine.deleteLater()
application.processEvents()
'''
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


class MacAdapterTests(unittest.TestCase):
    def test_capability_is_lazy_and_requires_visual_effect_view(self):
        available = native_window._MacAdapter(
            appkit=SimpleNamespace(NSVisualEffectView=object()),
            objc_module=object(),
            qpa_name="cocoa",
        )
        missing = native_window._MacAdapter(
            appkit=SimpleNamespace(),
            objc_module=object(),
            qpa_name="cocoa",
        )

        self.assertTrue(available.native_available())
        self.assertFalse(missing.native_available())

    def test_non_cocoa_qpa_refuses_before_objc_pointer_conversion(self):
        class Objc:
            def __init__(self):
                self.calls = 0

            def objc_object(self, **_kwargs):
                self.calls += 1
                raise AssertionError("non-Cocoa handles are not NSView pointers")

        class Window:
            def __init__(self):
                self.win_id_calls = 0

            def winId(self):
                self.win_id_calls += 1
                return 123

        for qpa_name in ("offscreen", "minimal", ""):
            with self.subTest(qpa_name=qpa_name):
                objc_module = Objc()
                window = Window()
                adapter = native_window._MacAdapter(
                    appkit=SimpleNamespace(NSVisualEffectView=object()),
                    objc_module=objc_module,
                    qpa_name=qpa_name,
                )

                self.assertFalse(adapter.native_available())
                self.assertIsNone(adapter._view_for(window))
                self.assertFalse(adapter.apply_material(window, "dark"))
                self.assertFalse(adapter.enable_custom_chrome(window))
                self.assertEqual(window.win_id_calls, 0)
                self.assertEqual(objc_module.calls, 0)

    def test_cocoa_qpa_allows_objc_pointer_conversion(self):
        converted = []
        expected_view = object()

        def convert(**values):
            converted.append(values)
            return expected_view

        adapter = native_window._MacAdapter(
            appkit=SimpleNamespace(NSVisualEffectView=object()),
            objc_module=SimpleNamespace(objc_object=convert),
            qpa_name=lambda: " Cocoa ",
        )

        self.assertTrue(adapter.native_available())
        self.assertIs(
            adapter._view_for(SimpleNamespace(winId=lambda: 456)), expected_view
        )
        self.assertEqual(len(converted), 1)
        self.assertEqual(converted[0]["c_void_p"], 456)

    def test_window_actions_use_exact_appkit_selectors_and_zoom_state(self):
        class Native:
            def __init__(self):
                self.calls = []
                self.zoomed = False

            def performClose_(self, sender):
                self.calls.append(("performClose:", sender))

            def performMiniaturize_(self, sender):
                self.calls.append(("performMiniaturize:", sender))

            def performZoom_(self, sender):
                self.calls.append(("performZoom:", sender))
                self.zoomed = not self.zoomed

            def toggleFullScreen_(self, sender):
                self.calls.append(("toggleFullScreen:", sender))

            def isZoomed(self):
                self.calls.append(("isZoomed", None))
                return self.zoomed

        native = Native()
        adapter = native_window._MacAdapter(
            appkit=object(), objc_module=object(), qpa_name="cocoa"
        )
        adapter._native_window = native
        window = object()

        self.assertTrue(adapter.close_window(window))
        self.assertTrue(adapter.minimize_window(window))
        self.assertFalse(adapter.is_maximized(window))
        self.assertTrue(adapter.set_maximized(window, True))
        self.assertTrue(adapter.is_maximized(window))
        zoom_calls = native.calls.count(("performZoom:", None))
        self.assertTrue(adapter.set_maximized(window, True))
        self.assertEqual(native.calls.count(("performZoom:", None)), zoom_calls)
        self.assertTrue(adapter.set_maximized(window, False))
        self.assertFalse(adapter.is_maximized(window))
        self.assertTrue(adapter.toggle_full_screen(window))

        self.assertIn(("performClose:", None), native.calls)
        self.assertIn(("performMiniaturize:", None), native.calls)
        self.assertEqual(native.calls.count(("performZoom:", None)), 2)
        self.assertIn(("toggleFullScreen:", None), native.calls)

    def test_window_action_failures_are_reported_for_qwindow_fallback(self):
        class Native:
            @staticmethod
            def _fail(*_args):
                raise RuntimeError("synthetic AppKit failure")

            performClose_ = _fail
            performMiniaturize_ = _fail
            performZoom_ = _fail
            toggleFullScreen_ = _fail
            isZoomed = _fail

        adapter = native_window._MacAdapter(
            appkit=object(), objc_module=object(), qpa_name="cocoa"
        )
        adapter._native_window = Native()
        window = object()

        self.assertFalse(adapter.close_window(window))
        self.assertFalse(adapter.minimize_window(window))
        self.assertIsNone(adapter.is_maximized(window))
        self.assertFalse(adapter.set_maximized(window, True))
        self.assertFalse(adapter.toggle_full_screen(window))

    def test_zoom_requires_a_known_prestate_before_using_toggle_selector(self):
        class Native:
            def __init__(self):
                self.zoom_calls = 0

            @staticmethod
            def isZoomed():
                raise RuntimeError("synthetic state-query failure")

            def performZoom_(self, _sender):
                self.zoom_calls += 1

        native = Native()
        adapter = native_window._MacAdapter(
            appkit=object(), objc_module=object(), qpa_name="cocoa"
        )
        adapter._native_window = native

        self.assertFalse(adapter.set_maximized(object(), True))
        self.assertEqual(native.zoom_calls, 0)

    def test_zoom_verifies_the_requested_postcondition(self):
        class Native:
            def __init__(self):
                self.zoom_calls = 0

            @staticmethod
            def isZoomed():
                return False

            def performZoom_(self, _sender):
                self.zoom_calls += 1

        native = Native()
        adapter = native_window._MacAdapter(
            appkit=object(), objc_module=object(), qpa_name="cocoa"
        )
        adapter._native_window = native

        self.assertFalse(adapter.set_maximized(object(), True))
        self.assertEqual(native.zoom_calls, 1)

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
            appkit=appkit, objc_module=objc_module, qpa_name="cocoa"
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
            qpa_name="cocoa",
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
            qpa_name="cocoa",
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
            self.assertTrue(callable(controller.toggleFullScreen))
        finally:
            controller.detach()
            window.deleteLater()

    def test_generic_qwindow_state_sync_never_requires_widget_api(self):
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="test",
        )
        window = QQuickWindow()
        try:
            self.assertFalse(hasattr(window, "isMaximized"))
            self.assertTrue(controller.attach(window))
            window.show()
            self.qapp.processEvents()

            controller.toggleMaximize()
            self.qapp.processEvents()
            self.assertTrue(
                bool(window.windowState() & self.qt.Qt.WindowState.WindowMaximized)
            )
            self.assertTrue(controller.maximized)

            controller.toggleMaximize()
            self.qapp.processEvents()
            self.assertFalse(
                bool(window.windowState() & self.qt.Qt.WindowState.WindowMaximized)
            )
            self.assertFalse(controller.maximized)
        finally:
            window.hide()
            controller.detach()
            window.deleteLater()
            self.qapp.processEvents()

    def test_failed_appkit_actions_use_supported_qwindow_fallbacks(self):
        class Native:
            @staticmethod
            def _fail(*_args):
                raise RuntimeError("synthetic AppKit failure")

            performClose_ = _fail
            performMiniaturize_ = _fail
            performZoom_ = _fail
            toggleFullScreen_ = _fail
            isZoomed = _fail

        adapter = native_window._MacAdapter(
            appkit=object(), objc_module=object(), qpa_name="cocoa"
        )
        adapter._native_window = Native()
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="darwin",
            adapter=adapter,
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        try:
            with mock.patch.object(adapter, "enable_custom_chrome", return_value=True):
                self.assertTrue(controller.attach(window))
            self.assertTrue(controller.customChromeEnabled)
            window.show()
            self.qapp.processEvents()

            controller.toggleMaximize()
            self.qapp.processEvents()
            self.assertTrue(controller.maximized)
            controller.toggleMaximize()
            self.qapp.processEvents()
            self.assertFalse(controller.maximized)

            controller.toggleFullScreen()
            self.qapp.processEvents()
            self.assertTrue(
                bool(window.windowState() & self.qt.Qt.WindowState.WindowFullScreen)
            )
            controller.toggleFullScreen()
            self.qapp.processEvents()
            self.assertFalse(
                bool(window.windowState() & self.qt.Qt.WindowState.WindowFullScreen)
            )

            controller.minimize()
            self.qapp.processEvents()
            self.assertTrue(
                bool(window.windowState() & self.qt.Qt.WindowState.WindowMinimized)
            )
            window.showNormal()
            self.qapp.processEvents()
            controller.closeMain()
            self.qapp.processEvents()
            self.assertFalse(window.isVisible())
        finally:
            window.hide()
            controller.detach()
            window.deleteLater()
            self.qapp.processEvents()

    def test_failed_windows_action_restores_system_frame_before_qt_fallback(self):
        class FailingActionAdapter(_FakeAdapter):
            def __init__(self):
                super().__init__()
                self.chrome_restores = 0

            @staticmethod
            def is_maximized(_window):
                return None

            @staticmethod
            def set_maximized(_window, _maximized):
                return False

            def restore_custom_chrome(self, _window):
                self.chrome_restores += 1
                return True

        adapter = FailingActionAdapter()
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        original_flags = window.flags()
        try:
            with mock.patch.object(
                type(controller), "_install_windows_hit_filter", return_value=True
            ):
                self.assertTrue(controller.attach(window))
            self.assertTrue(controller.customChromeEnabled)

            with self.assertLogs("speakr.native_window", level="WARNING") as logs:
                controller.toggleMaximize()
            self.qapp.processEvents()

            self.assertFalse(controller.customChromeEnabled)
            self.assertEqual(window.flags(), original_flags)
            self.assertEqual(adapter.chrome_restores, 1)
            self.assertTrue(
                bool(window.windowState() & self.qt.Qt.WindowState.WindowMaximized)
            )
            self.assertTrue(controller.maximized)
            self.assertIn("restoring the system frame", "\n".join(logs.output))
        finally:
            window.hide()
            controller.detach()
            window.deleteLater()
            self.qapp.processEvents()

    def test_failed_windows_frame_restore_keeps_custom_chrome_truthful(self):
        class UnrestorableAdapter(_FakeAdapter):
            def __init__(self):
                super().__init__()
                self.chrome_restores = 0

            @staticmethod
            def is_maximized(_window):
                return None

            @staticmethod
            def set_maximized(_window, _maximized):
                return False

            def restore_custom_chrome(self, _window):
                self.chrome_restores += 1
                return False

        adapter = UnrestorableAdapter()
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        try:
            with mock.patch.object(
                type(controller), "_install_windows_hit_filter", return_value=True
            ), mock.patch.object(
                type(controller), "_remove_windows_hit_filter"
            ) as remove_hit_filter:
                self.assertTrue(controller.attach(window))
                custom_flags = window.flags()
                self.assertTrue(controller.customChromeEnabled)
                remove_calls_before_action = remove_hit_filter.call_count

                with self.assertLogs("speakr.native_window", level="WARNING") as logs:
                    controller.toggleMaximize()
                self.qapp.processEvents()

                self.assertTrue(controller.customChromeEnabled)
                self.assertEqual(window.flags(), custom_flags)
                self.assertFalse(controller.maximized)
                self.assertEqual(adapter.chrome_restores, 1)
                self.assertEqual(
                    remove_hit_filter.call_count, remove_calls_before_action
                )
                self.assertIn(
                    "keeping custom chrome enabled", "\n".join(logs.output)
                )
        finally:
            window.hide()
            controller.detach()
            window.deleteLater()
            self.qapp.processEvents()

    def test_qml_can_publish_qt_rect_hit_regions_without_warnings(self):
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="test",
        )
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("nativeWindow", controller)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "HitRegionProbe.qml"
            path.write_text(
                """
import QtQuick
QtObject {
    Component.onCompleted: nativeWindow.setHitRegions(
        Qt.rect(8, 8, 620, 56),
        Qt.rect(760, 8, 44, 44),
        Qt.rect(808, 8, 44, 44),
        Qt.rect(856, 8, 44, 44),
        8)
}
""",
                encoding="utf-8",
            )
            component = self.qt.QQmlComponent(
                engine,
                QUrl.fromLocalFile(str(path)),
                self.qt.QQmlComponent.PreferSynchronous,
            )
            probe = component.create()
            try:
                self.assertIsNotNone(
                    probe, [error.toString() for error in component.errors()]
                )
                self.qapp.processEvents()
                self.assertEqual(warnings, [])
                self.assertEqual(
                    controller._hit_regions,
                    {
                        "titlebar": (8.0, 8.0, 620.0, 56.0),
                        "minimize": (760.0, 8.0, 44.0, 44.0),
                        "maximize": (808.0, 8.0, 44.0, 44.0),
                        "close": (856.0, 8.0, 44.0, 44.0),
                        "resize_border": 8.0,
                    },
                )
                # QML publishes logical coordinates; Windows hit testing converts
                # physical message coordinates back by DPR before comparison.
                self.assertEqual(
                    native_window.windows_hit_test(
                        830, 20, 960, 700, controller._hit_regions
                    ),
                    native_window.HTMAXBUTTON,
                )
            finally:
                if probe is not None:
                    probe.deleteLater()
                component.deleteLater()
                self.qapp.processEvents()
        engine.deleteLater()
        self.qapp.processEvents()

    def test_qml_invalid_hit_regions_degrade_to_safe_client_geometry(self):
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="test",
        )
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("nativeWindow", controller)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(error.toString() for error in values)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "InvalidHitRegionProbe.qml"
            path.write_text(
                """
import QtQuick
QtObject {
    Component.onCompleted: nativeWindow.setHitRegions(
        Qt.rect(0, 0, 0, 56),
        null,
        "not a rectangle",
        Qt.rect(100, 8, 44, 44),
        -4)
}
""",
                encoding="utf-8",
            )
            component = self.qt.QQmlComponent(
                engine,
                QUrl.fromLocalFile(str(path)),
                self.qt.QQmlComponent.PreferSynchronous,
            )
            probe = component.create()
            try:
                self.assertIsNotNone(
                    probe, [error.toString() for error in component.errors()]
                )
                self.qapp.processEvents()
                self.assertEqual(warnings, [])
                self.assertEqual(
                    controller._hit_regions,
                    {
                        "titlebar": None,
                        "minimize": None,
                        "maximize": None,
                        "close": (100.0, 8.0, 44.0, 44.0),
                        "resize_border": 0.0,
                    },
                )
                self.assertEqual(
                    native_window.windows_hit_test(
                        20, 20, 200, 100, controller._hit_regions
                    ),
                    native_window.HTCLIENT,
                )
            finally:
                if probe is not None:
                    probe.deleteLater()
                component.deleteLater()
                self.qapp.processEvents()
        engine.deleteLater()
        self.qapp.processEvents()

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

    def test_windows_hit_filter_failure_restores_native_style_and_qt_frame(self):
        original_style = 0x86000000
        user32 = WindowsAdapterTests._User32(original_style)
        adapter = native_window._WindowsAdapter(build=0, user32=user32)
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        original_flags = window.flags()
        try:
            with mock.patch.object(
                type(controller), "_install_windows_hit_filter", return_value=False
            ):
                self.assertTrue(controller.attach(window))
            self.assertFalse(controller.customChromeEnabled)
            self.assertEqual(window.flags(), original_flags)
            self.assertEqual(user32.style, original_style)
            self.assertIsNone(adapter._original_style)
            self.assertEqual(adapter._chrome_hwnd, 0)
        finally:
            controller.detach()
            window.deleteLater()

    def test_attach_aborts_before_show_when_system_frame_cannot_be_restored(self):
        class UnrestorableAdapter(_FakeAdapter):
            @staticmethod
            def restore_custom_chrome(_window):
                return False

        adapter = UnrestorableAdapter(chrome_succeeds=True)
        controller = native_window.NativeWindowController(
            qt=self.qt,
            visual_effects="off",
            platform_name="win32",
            adapter=adapter,
        )
        window = QQuickWindow()
        window.setProperty("customChromeReady", True)
        chrome_publications = []
        controller.customChromeEnabledChanged.connect(
            lambda: chrome_publications.append(controller.customChromeEnabled)
        )
        try:
            with mock.patch.object(
                type(controller), "_install_windows_hit_filter", return_value=False
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "system frame could not be restored"
                ):
                    controller.attach(window)

            self.assertFalse(window.isVisible())
            self.assertFalse(controller.customChromeEnabled)
            self.assertEqual(chrome_publications, [])
            self.assertTrue(
                bool(window.flags() & self.qt.Qt.WindowType.FramelessWindowHint)
            )
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
        ) as preferences, mock.patch.object(
            native_window,
            "_adapter_for_platform",
            return_value=native_window._NullAdapter(),
        ):
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

    def test_run_native_ui_custom_chrome_fails_closed_under_offscreen_qpa(self):
        if self.qapp.platformName().lower() != "offscreen":
            self.skipTest("the regression targets the offscreen QPA")

        class Objc:
            def __init__(self):
                self.calls = 0

            def objc_object(self, **_kwargs):
                self.calls += 1
                raise AssertionError("offscreen winId must never reach PyObjC")

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
                        "visual_effects": "full",
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

        objc_module = Objc()
        adapter = native_window._MacAdapter(
            appkit=SimpleNamespace(NSVisualEffectView=object()),
            objc_module=objc_module,
        )
        controllers = []
        roots = []
        real_factory = native_window.NativeWindowController
        real_create = qt_ui._create_qml_root

        def controller_factory(**kwargs):
            kwargs.update(platform_name="darwin", adapter=adapter)
            controller = real_factory(**kwargs)
            controllers.append(controller)
            return controller

        def create_root(qt, engine, path, before_complete=None):
            if Path(path).name != "Main.qml":
                return real_create(qt, engine, path, before_complete=before_complete)
            root = QQuickWindow()
            root.setObjectName("mainWindow")
            root.setProperty("customChromeReady", True)
            original_flags = root.flags()
            if before_complete is not None:
                before_complete(root)
            roots.append((root, original_flags))
            return root, qt.QObject()

        accessibility = {
            "system_high_contrast": False,
            "system_reduced_motion": False,
            "system_reduce_transparency": False,
        }
        with mock.patch.object(
            qt_ui, "NativeWindowController", side_effect=controller_factory
        ), mock.patch.object(
            qt_ui, "_create_qml_root", side_effect=create_root
        ), mock.patch.object(
            qt_ui,
            "_system_accessibility_preferences",
            return_value=accessibility,
        ):
            self.assertEqual(qt_ui.run_native_ui(App()), 0)

        self.assertEqual(len(controllers), 1)
        self.assertFalse(controllers[0].customChromeEnabled)
        self.assertEqual(controllers[0].material, "scene_glass")
        self.assertEqual(objc_module.calls, 0)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0][0].flags(), roots[0][1])


if __name__ == "__main__":
    unittest.main()
