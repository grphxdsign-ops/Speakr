"""Import-safe native window effects and controls for the QML frontend.

The module intentionally imports neither PySide6 nor PyObjC at import time.
Source installs that use the browser recovery interface can therefore import
Speakr without loading a native UI runtime.  Platform APIs are reached only
after the Qt frontend has created its main window.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping

log = logging.getLogger("speakr.native_window")


# Windows non-client hit-test results.  They remain plain integers so the
# geometry helpers are fully testable on macOS, Linux, and Qt-free installs.
HTCLIENT = 1
HTCAPTION = 2
HTMINBUTTON = 8
HTMAXBUTTON = 9
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
HTCLOSE = 20

_VALID_EFFECT_PREFERENCES = {"system", "full", "reduced", "off"}
_VALID_MATERIALS = {"mica", "vibrancy", "scene_glass", "solid"}


@dataclass(frozen=True)
class EffectResolution:
    """The effective effects tier and material exposed to QML."""

    effect_tier: str
    material: str

    def __post_init__(self) -> None:
        if self.effect_tier not in {"full", "reduced", "off"}:
            raise ValueError(f"unsupported effect tier: {self.effect_tier}")
        if self.material not in _VALID_MATERIALS:
            raise ValueError(f"unsupported material: {self.material}")


def resolve_effects(
    visual_effects: object = "system",
    *,
    high_contrast: bool = False,
    reduce_transparency: bool = False,
    software_renderer: bool = False,
    platform_name: str | None = None,
    native_material_available: bool = False,
) -> EffectResolution:
    """Resolve a preference without reading user content or platform state.

    High contrast is always authoritative.  Reduced transparency and known
    software-rendered sessions retain local scene depth but never ask the OS
    compositor for a desktop-backed material.
    """

    preference = str(visual_effects or "system").strip().lower()
    if preference not in _VALID_EFFECT_PREFERENCES:
        preference = "system"
    if high_contrast or preference == "off":
        return EffectResolution("off", "solid")
    if reduce_transparency or software_renderer or preference == "reduced":
        return EffectResolution("reduced", "scene_glass")

    platform_key = str(platform_name or sys.platform).lower()
    if native_material_available and platform_key == "win32":
        return EffectResolution("full", "mica")
    if native_material_available and platform_key == "darwin":
        return EffectResolution("full", "vibrancy")
    return EffectResolution("full", "scene_glass")


def _rect_tuple(value: object) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        try:
            x = float(value.get("x", 0.0))
            y = float(value.get("y", 0.0))
            width = float(value.get("width", 0.0))
            height = float(value.get("height", 0.0))
        except (TypeError, ValueError):
            return None
    elif isinstance(value, (tuple, list)) and len(value) == 4:
        try:
            x, y, width, height = (float(part) for part in value)
        except (TypeError, ValueError):
            return None
    else:
        try:
            x = float(value.x())
            y = float(value.y())
            width = float(value.width())
            height = float(value.height())
        except (AttributeError, TypeError, ValueError):
            return None
    if width <= 0.0 or height <= 0.0:
        return None
    return (x, y, width, height)


def normalize_hit_regions(
    titlebar: object = None,
    minimize: object = None,
    maximize: object = None,
    close: object = None,
    resize_border: object = 8.0,
) -> dict[str, object]:
    """Normalize logical QML hit regions into immutable numeric values."""

    try:
        border = max(0.0, min(32.0, float(resize_border)))
    except (TypeError, ValueError):
        border = 8.0
    return {
        "titlebar": _rect_tuple(titlebar),
        "minimize": _rect_tuple(minimize),
        "maximize": _rect_tuple(maximize),
        "close": _rect_tuple(close),
        "resize_border": border,
    }


def _contains(rect: object, x: float, y: float) -> bool:
    if not isinstance(rect, tuple) or len(rect) != 4:
        return False
    left, top, width, height = rect
    return left <= x < left + width and top <= y < top + height


def windows_hit_test(
    x: object,
    y: object,
    width: object,
    height: object,
    regions: Mapping[str, object] | None,
    *,
    maximized: bool = False,
) -> int:
    """Return a Win32 HT* value for logical client coordinates."""

    try:
        px, py = float(x), float(y)
        window_width, window_height = float(width), float(height)
    except (TypeError, ValueError):
        return HTCLIENT
    normalized = dict(regions or {})
    try:
        border = max(0.0, float(normalized.get("resize_border", 0.0)))
    except (TypeError, ValueError):
        border = 0.0

    if not maximized and border > 0.0:
        left = px < border
        right = px >= window_width - border
        top = py < border
        bottom = py >= window_height - border
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM

    for name, result in (
        ("close", HTCLOSE),
        ("maximize", HTMAXBUTTON),
        ("minimize", HTMINBUTTON),
    ):
        if _contains(normalized.get(name), px, py):
            return result
    if _contains(normalized.get("titlebar"), px, py):
        return HTCAPTION
    return HTCLIENT


def _windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except (AttributeError, TypeError, ValueError):
        return 0


class _NullAdapter:
    material_name = "scene_glass"

    def native_available(self) -> bool:
        return False

    def apply_material(self, _window: Any, _theme: str) -> bool:
        return False

    def restore_material(self) -> None:
        return None

    def enable_custom_chrome(self, _window: Any) -> bool:
        return False

    def restore_custom_chrome(self, _window: Any) -> None:
        return None

    def show_system_menu(self, _window: Any, _x: float, _y: float) -> bool:
        return False

    def detach(self) -> None:
        return None


class _WindowsAdapter(_NullAdapter):
    """Small ctypes-only DWM adapter; never imported on other platforms."""

    material_name = "mica"
    _DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    _DWMWA_WINDOW_CORNER_PREFERENCE = 33
    _DWMWA_SYSTEMBACKDROP_TYPE = 38
    _DWMWCP_ROUND = 2
    _DWMSBT_NONE = 1
    _DWMSBT_MAINWINDOW = 2

    def __init__(self, *, build: int | None = None, dwmapi: Any = None, user32: Any = None):
        self._build = _windows_build() if build is None else int(build)
        self._dwmapi = dwmapi
        self._user32 = user32
        if self._dwmapi is None and sys.platform == "win32":
            try:
                self._dwmapi = ctypes.windll.dwmapi
            except (AttributeError, OSError):
                self._dwmapi = None
        if self._user32 is None and sys.platform == "win32":
            try:
                self._user32 = ctypes.windll.user32
            except (AttributeError, OSError):
                self._user32 = None
        if self._user32 is not None and sys.platform == "win32":
            try:
                from ctypes import wintypes

                self._user32.ClientToScreen.argtypes = [
                    wintypes.HWND, ctypes.POINTER(wintypes.POINT)
                ]
                self._user32.ClientToScreen.restype = wintypes.BOOL
                self._user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
                self._user32.GetSystemMenu.restype = wintypes.HMENU
                self._user32.TrackPopupMenu.argtypes = [
                    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
                ]
                self._user32.TrackPopupMenu.restype = wintypes.UINT
                self._user32.PostMessageW.argtypes = [
                    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
                ]
                self._user32.PostMessageW.restype = wintypes.BOOL
            except (AttributeError, TypeError):
                log.debug("Could not declare Windows system-menu prototypes", exc_info=True)
        self._hwnd = 0

    def native_available(self) -> bool:
        return self._build >= 22621 and callable(
            getattr(self._dwmapi, "DwmSetWindowAttribute", None)
        )

    def _set_int(self, hwnd: int, attribute: int, value: int) -> bool:
        if not self.native_available() or not hwnd:
            return False
        native_value = ctypes.c_int(int(value))
        try:
            result = self._dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(attribute),
                ctypes.byref(native_value),
                ctypes.sizeof(native_value),
            )
        except Exception:
            log.debug("DwmSetWindowAttribute failed", exc_info=True)
            return False
        return int(result) == 0

    def apply_material(self, window: Any, theme: str) -> bool:
        try:
            self._hwnd = int(window.winId())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            self._hwnd = 0
        if not self._hwnd:
            return False
        # Dark mode and rounded corners are best-effort.  The backdrop call
        # itself decides whether Mica is truthfully reported as active.
        self._set_int(
            self._hwnd,
            self._DWMWA_USE_IMMERSIVE_DARK_MODE,
            1 if str(theme).lower() == "dark" else 0,
        )
        self._set_int(
            self._hwnd,
            self._DWMWA_WINDOW_CORNER_PREFERENCE,
            self._DWMWCP_ROUND,
        )
        return self._set_int(
            self._hwnd,
            self._DWMWA_SYSTEMBACKDROP_TYPE,
            self._DWMSBT_MAINWINDOW,
        )

    def restore_material(self) -> None:
        if self._hwnd:
            self._set_int(
                self._hwnd,
                self._DWMWA_SYSTEMBACKDROP_TYPE,
                self._DWMSBT_NONE,
            )
            self._set_int(
                self._hwnd,
                self._DWMWA_WINDOW_CORNER_PREFERENCE,
                0,
            )
            self._set_int(
                self._hwnd,
                self._DWMWA_USE_IMMERSIVE_DARK_MODE,
                0,
            )

    def detach(self) -> None:
        try:
            self.restore_material()
        finally:
            self._hwnd = 0

    def enable_custom_chrome(self, _window: Any) -> bool:
        # Qt owns the frameless flag; this adapter supplies DWM behavior and
        # the controller installs the native non-client hit-test filter.
        return True

    def show_system_menu(self, window: Any, x: float, y: float) -> bool:
        if self._user32 is None:
            return False
        try:
            from ctypes import wintypes

            hwnd = int(window.winId())
            try:
                scale = max(0.01, float(window.devicePixelRatio()))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                scale = 1.0
            position = wintypes.POINT(int(float(x) * scale), int(float(y) * scale))
            if not self._user32.ClientToScreen(
                ctypes.c_void_p(hwnd), ctypes.byref(position)
            ):
                return False
            menu = self._user32.GetSystemMenu(ctypes.c_void_p(hwnd), False)
            if not menu:
                return False
            command = self._user32.TrackPopupMenu(
                ctypes.c_void_p(menu), 0x0100 | 0x0002, position.x, position.y, 0,
                ctypes.c_void_p(hwnd), None,
            )
            if command:
                self._user32.PostMessageW(hwnd, 0x0112, command, 0)
            return True
        except Exception:
            log.debug("Could not show the Windows system menu", exc_info=True)
            return False


class _MacAdapter(_NullAdapter):
    """Lazy PyObjC adapter for an NSVisualEffectView behind the Qt view."""

    material_name = "vibrancy"

    def __init__(self, *, appkit: Any = None, objc_module: Any = None):
        self._appkit = appkit
        self._objc = objc_module
        self._effect_view = None
        self._native_window = None
        self._was_opaque = None
        self._background_color = None
        self._chrome_state = None

    def _load(self) -> bool:
        if self._appkit is not None and self._objc is not None:
            return True
        if sys.platform != "darwin":
            return False
        try:
            import AppKit
            import objc
        except (ImportError, OSError):
            return False
        self._appkit, self._objc = AppKit, objc
        return True

    def native_available(self) -> bool:
        return self._load() and hasattr(self._appkit, "NSVisualEffectView")

    def _view_for(self, window: Any):
        pointer = int(window.winId())
        return self._objc.objc_object(c_void_p=pointer)

    def apply_material(self, window: Any, _theme: str) -> bool:
        if not self.native_available():
            return False
        try:
            qt_view = self._view_for(window)
            native_window = qt_view.window()
            if self._effect_view is not None and self._native_window is native_window:
                return True
            if not self.restore_material():
                return False
            content = native_window.contentView()
            effect = self._appkit.NSVisualEffectView.alloc().initWithFrame_(
                content.bounds()
            )
            effect.setAutoresizingMask_(
                self._appkit.NSViewWidthSizable | self._appkit.NSViewHeightSizable
            )
            effect.setBlendingMode_(self._appkit.NSVisualEffectBlendingModeBehindWindow)
            material = getattr(
                self._appkit,
                "NSVisualEffectMaterialUnderWindowBackground",
                getattr(self._appkit, "NSVisualEffectMaterialWindowBackground", 0),
            )
            effect.setMaterial_(material)
            effect.setState_(self._appkit.NSVisualEffectStateActive)
            self._effect_view = effect
            self._native_window = native_window
            self._was_opaque = bool(native_window.isOpaque())
            self._background_color = native_window.backgroundColor()
            content.addSubview_positioned_relativeTo_(
                effect, self._appkit.NSWindowBelow, None
            )
            native_window.setOpaque_(False)
            native_window.setBackgroundColor_(self._appkit.NSColor.clearColor())
            return True
        except Exception:
            log.debug("Could not attach macOS Vibrancy", exc_info=True)
            self.restore_material()
            return False

    def restore_material(self) -> bool:
        restored = True
        if self._effect_view is not None:
            try:
                self._effect_view.removeFromSuperview()
            except Exception:
                restored = False
                log.debug("Could not remove macOS Vibrancy view", exc_info=True)
        if self._was_opaque is not None:
            try:
                if self._native_window is None:
                    restored = False
                else:
                    self._native_window.setOpaque_(self._was_opaque)
            except Exception:
                restored = False
                log.debug("Could not restore macOS window opacity", exc_info=True)
        if self._background_color is not None:
            try:
                if self._native_window is None:
                    restored = False
                else:
                    self._native_window.setBackgroundColor_(self._background_color)
            except Exception:
                restored = False
                log.debug("Could not restore macOS window background", exc_info=True)
        if restored:
            self._effect_view = None
            self._was_opaque = None
            self._background_color = None
        return restored

    def enable_custom_chrome(self, window: Any) -> bool:
        if not self._load():
            return False
        try:
            native_window = self._view_for(window).window()
            style = native_window.styleMask()
            button_states = []
            for kind in (
                self._appkit.NSWindowCloseButton,
                self._appkit.NSWindowMiniaturizeButton,
                self._appkit.NSWindowZoomButton,
            ):
                button = native_window.standardWindowButton_(kind)
                button_states.append(
                    (kind, None if button is None else bool(button.isHidden()))
                )
            self._native_window = native_window
            self._chrome_state = (
                style,
                native_window.titlebarAppearsTransparent(),
                native_window.titleVisibility(),
                button_states,
            )
            required = (
                self._appkit.NSWindowStyleMaskTitled
                | self._appkit.NSWindowStyleMaskClosable
                | self._appkit.NSWindowStyleMaskMiniaturizable
                | self._appkit.NSWindowStyleMaskResizable
                | self._appkit.NSWindowStyleMaskFullSizeContentView
            )
            native_window.setStyleMask_(style | required)
            native_window.setTitlebarAppearsTransparent_(True)
            native_window.setTitleVisibility_(self._appkit.NSWindowTitleHidden)
            for kind in (
                self._appkit.NSWindowCloseButton,
                self._appkit.NSWindowMiniaturizeButton,
                self._appkit.NSWindowZoomButton,
            ):
                button = native_window.standardWindowButton_(kind)
                if button is not None:
                    button.setHidden_(True)
            return True
        except Exception:
            log.debug("Could not enable macOS custom chrome", exc_info=True)
            self.restore_custom_chrome(window)
            return False

    def restore_custom_chrome(self, _window: Any) -> bool:
        if self._chrome_state is None:
            return True
        if self._native_window is None:
            return False
        restored = True
        style, transparent, visibility, button_states = self._chrome_state
        for description, operation in (
            ("style", lambda: self._native_window.setStyleMask_(style)),
            (
                "titlebar transparency",
                lambda: self._native_window.setTitlebarAppearsTransparent_(transparent),
            ),
            (
                "title visibility",
                lambda: self._native_window.setTitleVisibility_(visibility),
            ),
        ):
            try:
                operation()
            except Exception:
                restored = False
                log.debug("Could not restore macOS %s", description, exc_info=True)
        for kind, was_hidden in button_states:
            try:
                button = self._native_window.standardWindowButton_(kind)
                if button is not None and was_hidden is not None:
                    button.setHidden_(was_hidden)
            except Exception:
                restored = False
                log.debug("Could not restore a macOS caption button", exc_info=True)
        if restored:
            self._chrome_state = None
        return restored

    def detach(self) -> bool:
        chrome_restored = self.restore_custom_chrome(None)
        material_restored = self.restore_material()
        if chrome_restored and material_restored:
            self._native_window = None
        return chrome_restored and material_restored


def _adapter_for_platform(platform_name: str):
    if platform_name == "win32":
        return _WindowsAdapter()
    if platform_name == "darwin":
        return _MacAdapter()
    return _NullAdapter()


_CONTROLLER_TYPES: dict[int, type] = {}


def create_native_window_controller_type(qt: Any) -> type:
    """Build the QObject type using an already-approved lazy Qt namespace."""

    cache_key = id(qt.QObject)
    cached = _CONTROLLER_TYPES.get(cache_key)
    if cached is not None:
        return cached

    QObject, Property = qt.QObject, qt.Property
    Signal, Slot, Qt = qt.Signal, qt.Slot, qt.Qt

    class NativeWindowController(QObject):
        materialChanged = Signal()
        effectTierChanged = Signal()
        customChromeEnabledChanged = Signal()
        nativeMaterialAvailableChanged = Signal()
        systemReduceTransparencyChanged = Signal()
        softwareRendererChanged = Signal()
        maximizedChanged = Signal()
        activeChanged = Signal()

        def __init__(
            self,
            *,
            theme: str = "system",
            visual_effects: str = "system",
            high_contrast: bool = False,
            reduce_transparency: bool = False,
            software_renderer: bool = False,
            platform_name: str | None = None,
            adapter: Any = None,
            parent: Any = None,
        ):
            super().__init__(parent)
            self._theme = str(theme or "system")
            self._visual_effects = str(visual_effects or "system")
            self._high_contrast = bool(high_contrast)
            self._system_reduce_transparency = bool(reduce_transparency)
            self._software_renderer = bool(software_renderer)
            self._platform_name = str(platform_name or sys.platform)
            self._adapter = adapter or _adapter_for_platform(self._platform_name)
            self._window = None
            self._material = "solid"
            self._effect_tier = "off"
            self._custom_chrome_enabled = False
            self._native_material_available = False
            self._maximized = False
            self._active = False
            self._hit_regions = normalize_hit_regions()
            self._original_flags = None
            self._native_event_filter = None
            self._apply_resolution(allow_native=False)

        def _get_material(self):
            return self._material

        material = Property(str, _get_material, notify=materialChanged)

        def _get_effect_tier(self):
            return self._effect_tier

        effectTier = Property(str, _get_effect_tier, notify=effectTierChanged)

        def _get_custom_chrome_enabled(self):
            return self._custom_chrome_enabled

        customChromeEnabled = Property(
            bool, _get_custom_chrome_enabled, notify=customChromeEnabledChanged
        )

        def _get_native_material_available(self):
            return self._native_material_available

        nativeMaterialAvailable = Property(
            bool,
            _get_native_material_available,
            notify=nativeMaterialAvailableChanged,
        )

        def _get_system_reduce_transparency(self):
            return self._system_reduce_transparency

        systemReduceTransparency = Property(
            bool,
            _get_system_reduce_transparency,
            notify=systemReduceTransparencyChanged,
        )

        def _get_software_renderer(self):
            return self._software_renderer

        softwareRenderer = Property(
            bool, _get_software_renderer, notify=softwareRendererChanged
        )

        def _get_maximized(self):
            return self._maximized

        maximized = Property(bool, _get_maximized, notify=maximizedChanged)

        def _get_active(self):
            return self._active

        active = Property(bool, _get_active, notify=activeChanged)

        def _set_value(self, attribute: str, value: object, signal: Any) -> None:
            if getattr(self, attribute) != value:
                setattr(self, attribute, value)
                signal.emit()

        def _sync_window_state(self, *_args) -> None:
            window = self._window
            if window is None:
                maximized = active = False
            else:
                try:
                    maximized = bool(window.isMaximized())
                except (AttributeError, RuntimeError):
                    maximized = False
                try:
                    active = bool(window.isActive())
                except (AttributeError, RuntimeError):
                    active = False
            self._set_value("_maximized", maximized, self.maximizedChanged)
            self._set_value("_active", active, self.activeChanged)

        def _install_windows_hit_filter(self) -> bool:
            if self._platform_name != "win32" or self._window is None:
                return True
            try:
                from ctypes import wintypes

                from PySide6.QtCore import QAbstractNativeEventFilter
                from PySide6.QtWidgets import QApplication

                controller = self
                hwnd = int(self._window.winId())
                user32 = ctypes.windll.user32

                class _HitFilter(QAbstractNativeEventFilter):
                    def nativeEventFilter(self, _event_type, message):
                        try:
                            msg = wintypes.MSG.from_address(int(message))
                            if int(msg.hWnd or 0) != hwnd or msg.message != 0x0084:
                                return False, 0
                            packed = int(msg.lParam)
                            screen_x = ctypes.c_short(packed & 0xFFFF).value
                            screen_y = ctypes.c_short((packed >> 16) & 0xFFFF).value
                            rect = wintypes.RECT()
                            if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
                                return False, 0
                            try:
                                scale = max(0.01, float(controller._window.devicePixelRatio()))
                            except (AttributeError, RuntimeError, TypeError, ValueError):
                                scale = 1.0
                            result = windows_hit_test(
                                (screen_x - rect.left) / scale,
                                (screen_y - rect.top) / scale,
                                (rect.right - rect.left) / scale,
                                (rect.bottom - rect.top) / scale,
                                controller._hit_regions,
                                maximized=controller._maximized,
                            )
                            if result != HTCLIENT:
                                return True, result
                        except Exception:
                            log.debug("Windows hit testing failed", exc_info=True)
                        return False, 0

                event_filter = _HitFilter()
                application = QApplication.instance()
                if application is None:
                    return False
                application.installNativeEventFilter(event_filter)
                self._native_event_filter = event_filter
                return True
            except (ImportError, OSError, AttributeError, RuntimeError):
                log.debug("Could not install Windows native hit testing", exc_info=True)
                return False

        def _remove_windows_hit_filter(self) -> None:
            event_filter = self._native_event_filter
            self._native_event_filter = None
            if event_filter is None:
                return
            try:
                from PySide6.QtWidgets import QApplication

                application = QApplication.instance()
                if application is not None:
                    application.removeNativeEventFilter(event_filter)
            except (ImportError, RuntimeError):
                log.debug("Could not remove Windows native hit testing", exc_info=True)

        def _apply_resolution(self, *, allow_native: bool = True) -> None:
            available = False
            if allow_native and self._window is not None:
                try:
                    available = bool(self._adapter.native_available())
                except Exception:
                    log.debug("Could not query native material capability", exc_info=True)
            resolution = resolve_effects(
                self._visual_effects,
                high_contrast=self._high_contrast,
                reduce_transparency=self._system_reduce_transparency,
                software_renderer=self._software_renderer,
                platform_name=self._platform_name,
                native_material_available=available,
            )
            native_requested = resolution.material in {"mica", "vibrancy"}
            native_active = False
            if native_requested and self._window is not None:
                try:
                    native_active = bool(
                        self._adapter.apply_material(self._window, self._theme)
                    )
                except Exception:
                    log.debug("Native material failed; using local scene glass", exc_info=True)
            else:
                try:
                    self._adapter.restore_material()
                except Exception:
                    log.debug("Could not restore the native material", exc_info=True)
            if native_requested and not native_active:
                resolution = resolve_effects(
                    self._visual_effects,
                    high_contrast=self._high_contrast,
                    reduce_transparency=self._system_reduce_transparency,
                    software_renderer=self._software_renderer,
                    platform_name=self._platform_name,
                    native_material_available=False,
                )
                available = False
            self._set_value(
                "_native_material_available",
                bool(available and (not native_requested or native_active)),
                self.nativeMaterialAvailableChanged,
            )
            self._set_value("_material", resolution.material, self.materialChanged)
            self._set_value("_effect_tier", resolution.effect_tier, self.effectTierChanged)

        def attach(self, window: Any) -> bool:
            """Attach while the QML root is hidden, before Component completion."""

            if window is None:
                return False
            if self._window is window:
                self._apply_resolution()
                return True
            self.detach()
            self._window = window
            try:
                self._original_flags = window.flags()
            except (AttributeError, RuntimeError):
                self._original_flags = None

            # A shell must opt in only after it supplies accessible custom
            # controls and hit regions.  The current Main.qml intentionally
            # has no customChromeReady property, so its system frame remains.
            try:
                custom_ready = bool(window.property("customChromeReady"))
            except (AttributeError, RuntimeError):
                custom_ready = False
            custom_enabled = False
            if custom_ready:
                try:
                    if self._platform_name == "win32":
                        window.setFlags(window.flags() | Qt.WindowType.FramelessWindowHint)
                    custom_enabled = bool(self._adapter.enable_custom_chrome(window))
                    if custom_enabled and self._platform_name == "win32":
                        custom_enabled = self._install_windows_hit_filter()
                except Exception:
                    log.exception("Custom chrome failed; restoring the system frame")
                    custom_enabled = False
                if not custom_enabled:
                    self._restore_system_frame()
            self._set_value(
                "_custom_chrome_enabled",
                custom_enabled,
                self.customChromeEnabledChanged,
            )
            for signal_name in ("windowStateChanged", "activeChanged", "visibilityChanged"):
                signal = getattr(window, signal_name, None)
                if signal is not None:
                    try:
                        signal.connect(self._sync_window_state)
                    except (AttributeError, RuntimeError):
                        pass
            self._sync_window_state()
            self._apply_resolution()
            return True

        def _restore_system_frame(self) -> None:
            window = self._window
            if window is None:
                return
            self._remove_windows_hit_filter()
            try:
                self._adapter.restore_custom_chrome(window)
            except Exception:
                log.debug("Could not restore platform chrome", exc_info=True)
            if self._original_flags is not None:
                try:
                    window.setFlags(self._original_flags)
                except (AttributeError, RuntimeError):
                    log.exception("Could not restore the normal system frame")

        def detach(self) -> None:
            self._remove_windows_hit_filter()
            if self._window is not None and self._custom_chrome_enabled:
                self._restore_system_frame()
            try:
                self._adapter.detach()
            except Exception:
                log.debug("Could not detach native window effects", exc_info=True)
            self._window = None
            self._original_flags = None
            self._set_value("_custom_chrome_enabled", False, self.customChromeEnabledChanged)
            self._set_value("_native_material_available", False, self.nativeMaterialAvailableChanged)
            self._sync_window_state()
            self._apply_resolution(allow_native=False)

        def update_environment(
            self, *, high_contrast: bool, reduce_transparency: bool
        ) -> None:
            self._high_contrast = bool(high_contrast)
            self._set_value(
                "_system_reduce_transparency",
                bool(reduce_transparency),
                self.systemReduceTransparencyChanged,
            )
            self._apply_resolution()

        @Slot(result=bool)
        def beginSystemMove(self):
            try:
                return bool(self._window and self._window.startSystemMove())
            except (AttributeError, RuntimeError):
                return False

        @Slot(object, result=bool)
        def beginSystemResize(self, edge_mask):
            if self._window is None:
                return False
            aliases = {
                "left": Qt.Edge.LeftEdge,
                "right": Qt.Edge.RightEdge,
                "top": Qt.Edge.TopEdge,
                "bottom": Qt.Edge.BottomEdge,
                "top_left": Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
                "top_right": Qt.Edge.TopEdge | Qt.Edge.RightEdge,
                "bottom_left": Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
                "bottom_right": Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
            }
            edges = aliases.get(str(edge_mask).lower())
            if edges is None:
                try:
                    edges = Qt.Edges(int(edge_mask))
                except (TypeError, ValueError):
                    return False
            try:
                return bool(self._window.startSystemResize(edges))
            except (AttributeError, RuntimeError):
                return False

        @Slot()
        def minimize(self):
            if self._window is not None:
                try:
                    self._window.showMinimized()
                except (AttributeError, RuntimeError):
                    log.debug("Could not minimize the main window", exc_info=True)

        @Slot()
        def toggleMaximize(self):
            if self._window is None:
                return
            try:
                if self._window.isMaximized():
                    self._window.showNormal()
                else:
                    self._window.showMaximized()
            except (AttributeError, RuntimeError):
                log.debug("Could not toggle main-window maximization", exc_info=True)

        @Slot()
        def closeMain(self):
            if self._window is not None:
                try:
                    self._window.close()
                except (AttributeError, RuntimeError):
                    log.debug("Could not close the main window", exc_info=True)

        @Slot(float, float, result=bool)
        def showSystemMenu(self, x, y):
            if self._window is None:
                return False
            try:
                return bool(self._adapter.show_system_menu(self._window, x, y))
            except Exception:
                log.debug("Could not show the platform system menu", exc_info=True)
                return False

        @Slot(object, object, object, object, object)
        def setHitRegions(self, titlebar, minimize, maximize, close, resize_border):
            self._hit_regions = normalize_hit_regions(
                titlebar, minimize, maximize, close, resize_border
            )

        @Slot(str, str)
        def applyVisualPreferences(self, theme, visual_effects):
            theme_value = str(theme or "system").lower()
            effects_value = str(visual_effects or "system").lower()
            self._theme = theme_value if theme_value else "system"
            self._visual_effects = (
                effects_value if effects_value in _VALID_EFFECT_PREFERENCES else "system"
            )
            self._apply_resolution()

    NativeWindowController.__name__ = "NativeWindowController"
    _CONTROLLER_TYPES[cache_key] = NativeWindowController
    return NativeWindowController


def NativeWindowController(*args: Any, qt: Any = None, **kwargs: Any):
    """Lazy factory kept callable without importing Qt at module import time."""

    if qt is None:
        from PySide6.QtCore import Property, QObject, Signal, Slot, Qt

        class _QtNamespace:
            pass

        qt = _QtNamespace()
        qt.Property, qt.QObject = Property, QObject
        qt.Signal, qt.Slot, qt.Qt = Signal, Slot, Qt
    return create_native_window_controller_type(qt)(*args, **kwargs)


__all__ = [
    "EffectResolution",
    "HTCAPTION",
    "HTCLIENT",
    "HTCLOSE",
    "HTMAXBUTTON",
    "HTMINBUTTON",
    "NativeWindowController",
    "create_native_window_controller_type",
    "normalize_hit_regions",
    "resolve_effects",
    "windows_hit_test",
]
