"""Native PySide6/QML frontend for Speakr.

PySide6 is imported only when :func:`run_native_ui` or :func:`Bridge` is
called.  Importing this module therefore remains safe on source installs
that intentionally use the legacy loopback panel.

This module deliberately does not import QtNetwork or QtWebEngine.
"""

from __future__ import annotations

import copy
import ctypes
import inspect
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from speakr.interface_state import InterfaceState
from speakr.native_window import NativeWindowController

log = logging.getLogger("speakr.qt_ui")


class QtUnavailable(RuntimeError):
    """Raised when the native frontend cannot be initialized safely."""


# Older callers used the longer name while the native UI was experimental.
NativeUIUnavailable = QtUnavailable

_QT = None
_BRIDGE_TYPE = None


def _load_qt():
    """Import the small, approved Qt surface on demand."""
    global _QT
    if _QT is not None:
        return _QT
    try:
        from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot, Qt
        from PySide6.QtGui import (
            QAction,
            QAccessible,
            QAccessibleAnnouncementEvent,
            QCursor,
            QGuiApplication,
            QIcon,
        )
        from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        from PySide6.QtQuickControls2 import QQuickStyle
        from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
    except (ImportError, OSError) as exc:
        raise QtUnavailable("PySide6-Essentials is not available") from exc
    _QT = SimpleNamespace(
        QAction=QAction,
        QAccessible=QAccessible,
        QAccessibleAnnouncementEvent=QAccessibleAnnouncementEvent,
        QApplication=QApplication,
        QCursor=QCursor,
        QGuiApplication=QGuiApplication,
        QIcon=QIcon,
        QMenu=QMenu,
        QObject=QObject,
        Property=Property,
        QQmlApplicationEngine=QQmlApplicationEngine,
        QQmlComponent=QQmlComponent,
        QQuickWindow=QQuickWindow,
        QQuickStyle=QQuickStyle,
        QSGRendererInterface=QSGRendererInterface,
        QSystemTrayIcon=QSystemTrayIcon,
        QTimer=QTimer,
        Qt=Qt,
        QUrl=QUrl,
        Signal=Signal,
        Slot=Slot,
    )
    return _QT


def qt_available() -> bool:
    """Return whether the approved Qt imports can be resolved and loaded."""
    try:
        _load_qt()
    except QtUnavailable:
        return False
    return True


def _prefer_software_renderer() -> bool:
    """Use Qt's local software scene graph in known remote-display sessions."""
    if os.environ.get("SPEAKR_QT_SOFTWARE", "").lower() in {"1", "true", "yes"}:
        return True
    if os.environ.get("QT_QUICK_BACKEND", "").lower() == "software":
        return True
    if os.environ.get("QSG_RHI_BACKEND", "").lower() == "software":
        return True
    session = os.environ.get("SESSIONNAME", "").upper()
    return session.startswith("RDP-") or bool(os.environ.get("SSH_CONNECTION"))


_SYSTEM_ACCESSIBILITY = None


def _system_accessibility_preferences() -> dict[str, bool]:
    """Read the OS contrast and animation preferences without user content."""
    global _SYSTEM_ACCESSIBILITY
    if _SYSTEM_ACCESSIBILITY is not None:
        return dict(_SYSTEM_ACCESSIBILITY)
    result = {
        "system_high_contrast": False,
        "system_reduced_motion": False,
        "system_reduce_transparency": False,
    }
    try:
        if sys.platform == "win32":
            from ctypes import wintypes

            class HIGHCONTRASTW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("dwFlags", wintypes.DWORD),
                    ("lpszDefaultScheme", wintypes.LPWSTR),
                ]

            high_contrast = HIGHCONTRASTW()
            high_contrast.cbSize = ctypes.sizeof(HIGHCONTRASTW)
            if ctypes.windll.user32.SystemParametersInfoW(
                0x0042, high_contrast.cbSize, ctypes.byref(high_contrast), 0
            ):
                result["system_high_contrast"] = bool(high_contrast.dwFlags & 0x1)
            animations = wintypes.BOOL(True)
            if ctypes.windll.user32.SystemParametersInfoW(
                0x1042, 0, ctypes.byref(animations), 0
            ):
                result["system_reduced_motion"] = not bool(animations.value)
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                ) as key:
                    transparency, _kind = winreg.QueryValueEx(key, "EnableTransparency")
                    result["system_reduce_transparency"] = not bool(transparency)
            except (FileNotFoundError, OSError):
                pass
        elif sys.platform == "darwin":
            try:
                from AppKit import NSWorkspace

                workspace = NSWorkspace.sharedWorkspace()
                result["system_high_contrast"] = bool(
                    workspace.accessibilityDisplayShouldIncreaseContrast()
                )
                result["system_reduced_motion"] = bool(
                    workspace.accessibilityDisplayShouldReduceMotion()
                )
                result["system_reduce_transparency"] = bool(
                    workspace.accessibilityDisplayShouldReduceTransparency()
                )
                _SYSTEM_ACCESSIBILITY = result
                return dict(result)
            except Exception:
                log.debug("Could not read macOS accessibility through AppKit", exc_info=True)
                pass

            def read_default(key: str) -> bool:
                completed = subprocess.run(
                    ["defaults", "read", "com.apple.universalAccess", key],
                    capture_output=True,
                    text=True,
                    timeout=0.75,
                    check=False,
                )
                return completed.stdout.strip().lower() in {"1", "true", "yes"}

            result["system_high_contrast"] = read_default("increaseContrast")
            result["system_reduced_motion"] = read_default("reduceMotion")
            result["system_reduce_transparency"] = read_default("reduceTransparency")
    except Exception:
        log.debug("Could not read system accessibility preferences", exc_info=True)
    _SYSTEM_ACCESSIBILITY = result
    return dict(result)


def _copy_mapping(value: Any, default: dict | None = None) -> dict:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    try:
        return copy.deepcopy(dict(value))
    except (TypeError, ValueError):
        return copy.deepcopy(default or {})


def _copy_list(value: Any) -> list:
    if isinstance(value, (list, tuple)):
        return copy.deepcopy(list(value))
    return []


def _with_system_accessibility(value: Any) -> dict[str, Any]:
    """Merge current non-content OS accessibility state into a snapshot."""

    settings = _copy_mapping(value)
    settings.update(_system_accessibility_preferences())
    return settings


def _callable(app: Any, *names: str):
    for name in names:
        candidate = getattr(app, name, None)
        if callable(candidate):
            return candidate
    return None


def _invoke_optional(app: Any, names: tuple[str, ...], *args: Any) -> Any:
    method = _callable(app, *names)
    if method is None:
        return None
    return method(*args)


def _legacy_settings_snapshot(app: Any) -> dict[str, Any]:
    """Create the QML settings shape for an unadapted SpeakrApp."""
    config = getattr(app, "config", None)
    raw = copy.deepcopy(getattr(config, "data", {}) or {})
    ui = copy.deepcopy(raw.get("ui", {}))
    ui_defaults = {
        "onboarding_complete": False,
        "open_window_on_start": True,
        "theme": "system",
        "visual_effects": "system",
        "density": "comfortable",
        "text_scale": "system",
        "reduced_motion": "system",
        "hud_visibility": "while_dictating",
        "hud_size": "standard",
        "hud_edge": "bottom",
        "background_announcements": False,
    }
    ui_defaults.update(ui)
    raw["ui"] = ui_defaults
    raw.setdefault(
        "dictation",
        {
            "enabled": bool(getattr(app, "enabled", True)),
            "hotkey": raw.get("hotkey", ""),
            "toggle_mode": bool(raw.get("toggle_mode", False)),
        },
    )
    raw.setdefault(
        "audio",
        {
            "input_device": raw.get("input_device"),
            "keep_microphone_ready": bool(raw.get("keep_mic_stream_open", True)),
            "preroll_seconds": raw.get("preroll_seconds", 0.4),
            "sample_rate": raw.get("sample_rate", 16000),
            "vad_threshold": raw.get("vad_threshold", 0.35),
        },
    )
    raw.setdefault(
        "transcription",
        {
            "model": raw.get("model", "auto"),
            "device": raw.get("device", "auto"),
            "compute_type": raw.get("compute_type", "auto"),
            "language": raw.get("language"),
            "beam_size": raw.get("beam_size", "auto"),
            "streaming": copy.deepcopy(raw.get("streaming", {})),
        },
    )
    raw.setdefault(
        "privacy",
        {
            "keep_microphone_ready": bool(raw.get("keep_mic_stream_open", True)),
            "preroll_seconds": raw.get("preroll_seconds", 0.4),
            "screen_context": bool(raw.get("screen_context", {}).get("enabled", True)),
            "edit_selection": bool(raw.get("edit_mode", {}).get("enabled", True)),
            "recent_context": bool(
                raw.get("formatting", {}).get("include_recent_context", True)
            ),
            "transcript_logging": bool(raw.get("log_transcripts", False)),
            "restore_clipboard": bool(raw.get("restore_clipboard", True)),
        },
    )
    raw.setdefault(
        "injection",
        {
            "method": raw.get("injection", "paste"),
            "restore_clipboard": bool(raw.get("restore_clipboard", True)),
        },
    )
    return raw


def _legacy_manual_words(app: Any) -> list[dict[str, Any]]:
    dictionary = getattr(app, "dictionary", None)
    path = getattr(dictionary, "path", None)
    if not path:
        return []
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    result = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            heard, _, intended = line.partition("=>")
            heard, intended = heard.strip(), intended.strip()
            if heard and intended:
                result.append(
                    {
                        "id": f"line:{index}",
                        "kind": "replacement",
                        "heard": heard,
                        "intended": intended,
                        "label": f"{heard} → {intended}",
                    }
                )
        else:
            result.append(
                {
                    "id": f"line:{index}",
                    "kind": "word",
                    "word": line,
                    "label": line,
                }
            )
    return result


def _legacy_learned_words(app: Any) -> list[dict[str, Any]]:
    learner = getattr(app, "learner", None)
    entries = getattr(learner, "_entries", {})
    lock = getattr(learner, "_lock", None)

    def build() -> list[dict[str, Any]]:
        ranked = sorted(
            entries.items(), key=lambda item: (-int(item[1].get("count", 0)), item[0])
        )
        return [
            {
                "id": lower,
                "word": str(entry.get("form", lower)),
                "count": int(entry.get("count", 0)),
            }
            for lower, entry in ranked
        ]

    if lock is None:
        return build()
    with lock:
        return build()


def _bridge_type(qt):
    global _BRIDGE_TYPE
    if _BRIDGE_TYPE is not None:
        return _BRIDGE_TYPE

    QObject = qt.QObject
    Property = qt.Property
    Signal = qt.Signal
    Slot = qt.Slot
    Qt = qt.Qt

    class _Bridge(QObject):
        """QObject boundary between QML and Speakr's non-Qt orchestrator."""

        stateChanged = Signal()
        settingsChanged = Signal()
        practiceChanged = Signal()
        manualWordsChanged = Signal()
        learnedWordsChanged = Signal()
        capturingHotkeyChanged = Signal()
        quittingChanged = Signal()

        _stateQueued = Signal(object)
        _settingsQueued = Signal(object)
        _practiceQueued = Signal(object)
        _refreshQueued = Signal()
        _captureFinished = Signal(int, object, object)
        _showRequested = Signal()
        _quitRequested = Signal()

        def __init__(self, app, interface_state=None, parent=None):
            super().__init__(parent)
            self._app = app
            self._interface_state = interface_state or getattr(
                app, "interface_state", None
            )
            if self._interface_state is None:
                self._interface_state = InterfaceState(
                    {
                        "enabled": bool(getattr(app, "enabled", True)),
                        "availability": "starting",
                        "hotkey": self._config_get("hotkey", default=""),
                        "model": self._config_get("model", default="auto"),
                    }
                )
                try:
                    app.interface_state = self._interface_state
                except Exception:
                    pass
            if not isinstance(self._interface_state, InterfaceState):
                raise TypeError("app.interface_state must be an InterfaceState")

            self._state = self._interface_state.snapshot()
            self._settings = self._read_settings()
            self._practice = self._read_practice()
            self._manual_words = self._read_manual_words()
            self._learned_words = self._read_learned_words()
            self._capturing_hotkey = False
            self._quitting = False
            self._pending_hotkey = str(self._settings.get("pending_hotkey") or "")
            if self._pending_hotkey:
                self._state["pending_hotkey"] = self._pending_hotkey
            self._capture_generation = 0
            self._capture_cancel = threading.Event()
            self._main_window = None
            self._hud_window = None
            self._tray = None
            self._closed = False
            self._announced_processing_job = None
            self._announced_final_job = None

            queued = getattr(Qt, "QueuedConnection", Qt.ConnectionType.QueuedConnection)
            self._stateQueued.connect(self._accept_state, queued)
            self._settingsQueued.connect(self._accept_settings, queued)
            self._practiceQueued.connect(self._accept_practice, queued)
            self._refreshQueued.connect(self._refresh_all_now, queued)
            self._captureFinished.connect(self._finish_hotkey_capture, queued)
            self._showRequested.connect(self._show_main_now, queued)
            self._quitRequested.connect(self._request_quit_now, queued)
            self._unsubscribe = self._interface_state.subscribe(self._queue_state)
            self._aux_unsubscribers = []
            auxiliary = (
                ("subscribe_settings", self._settingsQueued),
                ("subscribe_practice", self._practiceQueued),
            )
            for subscribe_name, signal in auxiliary:
                subscribe = getattr(self._app, subscribe_name, None)
                if callable(subscribe):
                    try:
                        unsubscribe = subscribe(signal.emit)
                        if callable(unsubscribe):
                            self._aux_unsubscribers.append(unsubscribe)
                    except Exception:
                        log.exception("Could not subscribe to %s", subscribe_name)

        # ----- QML properties ---------------------------------------------

        def _get_state(self):
            return copy.deepcopy(self._state)

        state = Property("QVariantMap", _get_state, notify=stateChanged)

        def _get_settings(self):
            return copy.deepcopy(self._settings)

        settings = Property("QVariantMap", _get_settings, notify=settingsChanged)

        def _get_practice(self):
            return copy.deepcopy(self._practice)

        practice = Property("QVariantMap", _get_practice, notify=practiceChanged)

        def _get_manual_words(self):
            return copy.deepcopy(self._manual_words)

        manualWords = Property("QVariantList", _get_manual_words, notify=manualWordsChanged)

        def _get_learned_words(self):
            return copy.deepcopy(self._learned_words)

        learnedWords = Property("QVariantList", _get_learned_words, notify=learnedWordsChanged)

        def _get_capturing_hotkey(self):
            return self._capturing_hotkey

        capturingHotkey = Property(
            bool, _get_capturing_hotkey, notify=capturingHotkeyChanged
        )

        def _get_quitting(self):
            return self._quitting

        quitting = Property(bool, _get_quitting, notify=quittingChanged)

        # ----- lifecycle and queued refreshes -----------------------------

        def attach_frontend(self, main_window, hud_window, tray):
            self._main_window = main_window
            self._hud_window = hud_window
            self._tray = tray

        def show_main(self):
            """Thread-safe entry point used by the single-instance watcher."""
            if not self._closed:
                self._showRequested.emit()

        def request_quit(self):
            if not self._closed:
                self._quitRequested.emit()

        quit = request_quit

        def close(self):
            if self._closed:
                return
            self._closed = True
            self._capture_cancel.set()
            unsubscribe, self._unsubscribe = self._unsubscribe, None
            if unsubscribe:
                unsubscribe()
            for unsubscribe in self._aux_unsubscribers:
                try:
                    unsubscribe()
                except Exception:
                    log.exception("Could not remove a Qt UI subscription")
            self._aux_unsubscribers.clear()

        def refresh(self):
            if not self._closed:
                self._refreshQueued.emit()

        def _queue_state(self, snapshot):
            if not self._closed:
                self._stateQueued.emit(snapshot)

        @Slot(object)
        def _accept_state(self, snapshot):
            snapshot = _copy_mapping(snapshot)
            previous = self._state
            capture_started = (
                snapshot.get("capture") == "listening"
                and previous.get("capture") != "listening"
            )
            new_attempt = (
                bool(snapshot.get("capture_job_id"))
                and snapshot.get("capture_job_id") != previous.get("capture_job_id")
            )
            if capture_started or new_attempt:
                screen = qt.QGuiApplication.screenAt(qt.QCursor.pos())
                if screen is None:
                    screen = qt.QGuiApplication.primaryScreen()
                if screen is not None:
                    geometry = screen.availableGeometry()
                    monitor = {
                        "active_monitor_x": geometry.x(),
                        "active_monitor_y": geometry.y(),
                        "active_monitor_width": geometry.width(),
                        "active_monitor_height": geometry.height(),
                    }
                    snapshot.update(monitor)
                    try:
                        self._interface_state.update(**monitor)
                    except Exception:
                        log.exception("Could not latch the active HUD monitor")
            if self._pending_hotkey:
                snapshot["pending_hotkey"] = self._pending_hotkey
            if snapshot != self._state:
                self._state = snapshot
                self.stateChanged.emit()
                self._announce_state(previous, snapshot)
                issue_code = str((snapshot.get("last_issue") or {}).get("code", ""))
                if snapshot.get("capture") == "listening" or (
                    snapshot.get("capture_job_id")
                    and issue_code in {"microphone_unavailable", "microphone_reconnected"}
                ):
                    qt.QTimer.singleShot(60, self._verify_hud_focus)

        def _announcements_enabled(self):
            ui = self._settings.get("ui", {}) if isinstance(self._settings, dict) else {}
            return bool(ui.get("background_announcements", False))

        def _announce(self, message, *, assertive=False):
            if not message or not self._announcements_enabled():
                return
            try:
                event = qt.QAccessibleAnnouncementEvent(self, str(message))
                politeness = qt.QAccessible.AnnouncementPoliteness
                event.setPoliteness(
                    politeness.Assertive if assertive else politeness.Polite
                )
                qt.QAccessible.updateAccessibility(event)
            except Exception:
                log.debug("Accessibility announcement was unavailable", exc_info=True)

        def _announce_state(self, previous, snapshot):
            capture_started = (
                snapshot.get("capture") == "listening"
                and previous.get("capture") != "listening"
            )
            if capture_started:
                self._announce("Listening", assertive=True)
                return
            pipeline = snapshot.get("pipeline")
            job_id = snapshot.get("pipeline_job_id")
            if pipeline in {
                "queued", "waiting_model", "transcribing", "formatting", "injecting"
            }:
                if job_id and self._announced_processing_job != job_id:
                    self._announced_processing_job = job_id
                    self._announce("Processing locally")
                return
            final = pipeline in {"success", "error"} or snapshot.get("status_code") in {
                "no_speech", "edit_failure", "mic_recovery"
            }
            if final and self._announced_final_job != job_id:
                self._announced_final_job = job_id
                self._announce(snapshot.get("primary_text") or "Finished")

        def _verify_hud_focus(self):
            hud = self._hud_window
            if hud is None or bool(hud.property("focusGuardSuppressed")):
                return
            try:
                stole_focus = qt.QGuiApplication.focusWindow() is hud or hud.isActive()
            except (AttributeError, RuntimeError):
                stole_focus = False
            if not stole_focus:
                return
            try:
                hud.setProperty("focusGuardSuppressed", True)
                hud.hide()
            except (AttributeError, RuntimeError):
                pass
            try:
                self._interface_state.latch_issue(
                    "hud_focus_guard",
                    "The dictation HUD was hidden to protect keyboard focus.",
                    "open_speakr",
                    blocking=False,
                )
            except Exception:
                log.exception("Could not publish the HUD focus safeguard")

        @Slot(object)
        def _accept_settings(self, snapshot):
            settings = _with_system_accessibility(snapshot)
            if settings != self._settings:
                self._settings = settings
                self.settingsChanged.emit()
            # Vocabulary operations use the settings notification as their
            # low-frequency data-changed signal.
            manual_words = self._read_manual_words()
            learned_words = self._read_learned_words()
            if manual_words != self._manual_words:
                self._manual_words = manual_words
                self.manualWordsChanged.emit()
            if learned_words != self._learned_words:
                self._learned_words = learned_words
                self.learnedWordsChanged.emit()

        @Slot(object)
        def _accept_practice(self, snapshot):
            practice = self._normalize_practice(snapshot)
            if practice != self._practice:
                self._practice = practice
                self.practiceChanged.emit()

        @Slot()
        def _refresh_all_now(self):
            snapshot = self._interface_state.snapshot()
            if self._pending_hotkey:
                snapshot["pending_hotkey"] = self._pending_hotkey
            if snapshot != self._state:
                self._state = snapshot
                self.stateChanged.emit()
            self._refresh_auxiliary_now()

        def _refresh_auxiliary_now(self):
            settings = self._read_settings()
            practice = self._read_practice()
            manual_words = self._read_manual_words()
            learned_words = self._read_learned_words()
            if settings != self._settings:
                self._settings = settings
                self.settingsChanged.emit()
            if practice != self._practice:
                self._practice = practice
                self.practiceChanged.emit()
            if manual_words != self._manual_words:
                self._manual_words = manual_words
                self.manualWordsChanged.emit()
            if learned_words != self._learned_words:
                self._learned_words = learned_words
                self.learnedWordsChanged.emit()

        @Slot()
        def _show_main_now(self):
            window = self._main_window
            if window is None:
                return
            try:
                window.show()
                window.raise_()
                window.requestActivate()
            except (AttributeError, RuntimeError):
                log.exception("Could not show the Speakr window")

        @Slot()
        def _request_quit_now(self):
            if self._quitting:
                return
            self._quitting = True
            self.quittingChanged.emit()
            self._capture_cancel.set()
            try:
                _invoke_optional(self._app, ("clear_practice",))
            except Exception:
                log.exception("Could not clear Practice while quitting")
            try:
                _invoke_optional(self._app, ("quit", "shutdown"))
            except Exception:
                log.exception("Speakr core shutdown failed")
            qt.QApplication.instance().quit()

        # ----- app operations consumed by QML -----------------------------

        @Slot()
        def toggleDictation(self):
            try:
                _invoke_optional(
                    self._app, ("toggle_dictation", "toggle_enabled")
                )
            except Exception:
                log.exception("Could not toggle dictation")
            self.refresh()

        @Slot()
        def beginHotkeyCapture(self):
            if self._capturing_hotkey:
                return
            self._capture_generation += 1
            generation = self._capture_generation
            self._capture_cancel = threading.Event()
            self._capturing_hotkey = True
            self.capturingHotkeyChanged.emit()

            adapted = _callable(self._app, "begin_hotkey_capture")
            if adapted is not None:
                def completed(candidate):
                    self._captureFinished.emit(generation, candidate, None)

                try:
                    accepted = adapted(completed)
                except Exception as exc:
                    self._captureFinished.emit(generation, None, exc)
                    return
                if accepted is False:
                    self._captureFinished.emit(
                        generation,
                        None,
                        RuntimeError("hotkey capture is busy"),
                    )
                return

            def capture():
                candidate = None
                error = None
                try:
                    method = _callable(
                        self._app,
                        "capture_hotkey_candidate",
                        "capture_hotkey",
                    )
                    if method is None:
                        raise RuntimeError("hotkey capture is unavailable")
                    # Adapted apps may accept the cancel event.  The legacy
                    # capture method accepts only an optional timeout.
                    name = getattr(method, "__name__", "")
                    if name == "capture_hotkey":
                        candidate = method(timeout=None)
                    else:
                        try:
                            parameters = inspect.signature(method).parameters
                        except (TypeError, ValueError):
                            parameters = {}
                        candidate = (
                            method(self._capture_cancel) if parameters else method()
                        )
                except Exception as exc:
                    error = exc
                self._captureFinished.emit(generation, candidate, error)

            threading.Thread(
                target=capture,
                name="qt-hotkey-capture",
                daemon=True,
            ).start()

        # Compatibility alias for an early QML prototype.
        startHotkeyCapture = beginHotkeyCapture

        @Slot()
        def cancelHotkeyCapture(self):
            if not self._capturing_hotkey:
                return
            self._capture_cancel.set()
            self._capture_generation += 1
            try:
                _invoke_optional(self._app, ("cancel_hotkey_capture",))
            except Exception:
                log.exception("Could not cancel hotkey capture")
            self._capturing_hotkey = False
            self._pending_hotkey = ""
            self.capturingHotkeyChanged.emit()
            self.refresh()

        @Slot(int, object, object)
        def _finish_hotkey_capture(self, generation, candidate, error):
            if generation != self._capture_generation or self._capture_cancel.is_set():
                return
            if error is not None:
                log.error("Hotkey capture failed: %s", error)
            self._pending_hotkey = str(candidate or "").strip()
            # Keep the capture flow active while the candidate is awaiting
            # explicit confirmation; this is not active key listening.
            self._capturing_hotkey = bool(self._pending_hotkey)
            self.capturingHotkeyChanged.emit()
            self._state = self._interface_state.snapshot()
            if self._pending_hotkey:
                self._state["pending_hotkey"] = self._pending_hotkey
            self.stateChanged.emit()
            self._settings = self._read_settings()
            if self._pending_hotkey:
                self._settings["pending_hotkey"] = self._pending_hotkey
            self.settingsChanged.emit()

        @Slot()
        def confirmHotkey(self):
            if not self._pending_hotkey:
                return
            method = _callable(self._app, "confirm_hotkey")
            succeeded = True
            try:
                if method is not None:
                    try:
                        parameters = inspect.signature(method).parameters
                    except (TypeError, ValueError):
                        parameters = {"candidate": None}
                    if parameters:
                        result = method(self._pending_hotkey)
                    else:
                        result = method()
                    succeeded = result is not False
                else:
                    config = getattr(self._app, "config", None)
                    if config is not None:
                        config.set("hotkey", value=self._pending_hotkey)
                    _invoke_optional(self._app, ("reload_config",))
            except Exception:
                log.exception("Could not confirm hotkey")
                succeeded = False
            if not succeeded:
                self.refresh()
                return
            self._pending_hotkey = ""
            self._capturing_hotkey = False
            self.capturingHotkeyChanged.emit()
            self.refresh()

        @Slot(str, "QVariant", result=bool)
        def setSetting(self, path, value):
            try:
                method = _callable(self._app, "set_setting")
                if method is not None:
                    result = method(str(path), value)
                else:
                    result = self._legacy_set_setting(str(path), value)
                self.refresh()
                return result is not False
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Rejected setting %r: %s", path, exc)
            except Exception:
                log.exception("Could not save setting %r", path)
            return False

        @Slot(result=bool)
        def startPractice(self):
            try:
                method = _callable(self._app, "start_practice")
                if method is None:
                    return False
                result = method()
                self.refresh()
                return result is not False
            except Exception:
                log.exception("Could not start Practice")
                self.refresh()
                return False

        @Slot()
        def stopPractice(self):
            self._run_action(("stop_practice",))

        @Slot()
        def clearPractice(self):
            self._run_action(("clear_practice",))

        @Slot(result=bool)
        def completeOnboarding(self):
            method = _callable(self._app, "complete_onboarding")
            if method:
                try:
                    result = method()
                    self.refresh()
                    return result is not False
                except Exception:
                    log.exception("Could not complete onboarding")
                    self.refresh()
                    return False
            return self.setSetting("ui.onboarding_complete", True)

        @Slot(str, result=bool)
        def resetSettingsSection(self, section):
            try:
                method = _callable(self._app, "reset_settings_section")
                if method is None:
                    return False
                result = method(str(section))
                self.refresh()
                return result is not False
            except Exception:
                log.exception("Could not reset the %s settings section", section)
                return False

        @Slot(str)
        def navigate(self, page):
            try:
                method = _callable(self._app, "navigate")
                if method:
                    method(str(page))
                elif str(page).lower() != "practice":
                    _invoke_optional(self._app, ("clear_practice",))
            except Exception:
                log.exception("Could not leave the current page")
            self.refresh()

        @Slot(str, result=bool)
        def addWord(self, word):
            return self._run_action(("add_word",), str(word))

        @Slot(str, str, result=bool)
        def addReplacement(self, heard, intended):
            return self._run_action(("add_replacement",), str(heard), str(intended))

        @Slot(str)
        def removeManualWord(self, entry_id):
            self._run_action(("remove_manual_word",), str(entry_id))

        @Slot(str)
        def approveLearnedWord(self, word):
            self._run_action(("approve_learned_word",), str(word))

        @Slot(str)
        def forgetLearnedWord(self, word):
            self._run_action(("forget_learned_word",), str(word))

        @Slot(str)
        def openLocal(self, kind):
            kind = str(kind).lower()
            method = _callable(self._app, "open_local")
            try:
                if method:
                    method(kind)
                else:
                    fallbacks = {
                        "config": ("open_config",),
                        "dictionary": ("open_dictionary",),
                        "vocabulary": ("open_dictionary",),
                        "log": ("open_log",),
                    }
                    _invoke_optional(self._app, fallbacks.get(kind, ()))
            except Exception:
                log.exception("Could not open local %s", kind)

        @Slot()
        def openSystemSettings(self):
            method = _callable(self._app, "open_system_settings")
            try:
                if method:
                    method()
                elif sys.platform == "win32":
                    os.startfile("ms-settings:privacy-microphone")
                elif sys.platform == "darwin":
                    subprocess.Popen(
                        [
                            "open",
                            "x-apple.systempreferences:"
                            "com.apple.preference.security?Privacy_Microphone",
                        ]
                    )
            except Exception:
                log.exception("Could not open system privacy settings")

        @Slot()
        def openBrowserFallback(self):
            try:
                _invoke_optional(
                    self._app,
                    ("open_browser_fallback", "open_panel"),
                )
            except Exception:
                log.exception("Could not open browser fallback")

        @Slot()
        def dismissIssue(self):
            method = _callable(self._app, "dismiss_issue")
            try:
                if method:
                    method()
                else:
                    self._interface_state.dismiss_issue()
            except Exception:
                log.exception("Could not dismiss issue")
            self.refresh()

        @Slot()
        def retrySetup(self):
            try:
                method = _callable(self._app, "retry_setup")
                if method is not None:
                    method()
                else:
                    _invoke_optional(self._app, ("retry_model", "reload_config"))
            except Exception:
                log.exception("Could not retry local setup")
            self.refresh()

        @Slot(result=bool)
        def reloadLocalState(self):
            try:
                method = _callable(self._app, "reload_dictionary", "reload_config")
                if method is None:
                    return False
                result = method()
                self.refresh()
                return result is not False
            except Exception:
                log.exception("Could not reload local configuration")
                self.refresh()
                return False

        @Slot()
        def quitApp(self):
            self.request_quit()

        # ----- snapshot and fallback helpers ------------------------------

        def _run_action(self, names, *args):
            succeeded = False
            try:
                method = _callable(self._app, *names)
                if method is not None:
                    succeeded = method(*args) is not False
            except Exception:
                log.exception("UI action %s failed", names[0])
            self.refresh()
            return succeeded

        def _read_settings(self):
            method = _callable(self._app, "settings_snapshot")
            if method:
                try:
                    return _with_system_accessibility(method())
                except Exception:
                    log.exception("Could not read settings snapshot")
            return _with_system_accessibility(_legacy_settings_snapshot(self._app))

        def _read_practice(self):
            method = _callable(self._app, "practice_snapshot")
            if method:
                try:
                    return self._normalize_practice(method())
                except Exception:
                    log.exception("Could not read Practice snapshot")
            return {
                "active": False,
                "text": "",
                "mic_level_band": "silent",
                "sound_detected": False,
                "busy": False,
                "error": "",
            }

        @staticmethod
        def _normalize_practice(value):
            snapshot = _copy_mapping(value)
            snapshot.setdefault("mic_level_band", snapshot.get("level", "silent"))
            snapshot.setdefault(
                "sound_detected",
                bool(snapshot.get("heard"))
                or snapshot.get("mic_level_band") not in {"silent", ""},
            )
            snapshot.setdefault("busy", bool(snapshot.get("processing", False)))
            snapshot.setdefault(
                "text", snapshot.get("wouldType") or snapshot.get("heard") or ""
            )
            snapshot.setdefault("error", snapshot.get("message", ""))
            return snapshot

        def _read_manual_words(self):
            method = _callable(self._app, "list_manual_words")
            if method:
                try:
                    return _copy_list(method())
                except Exception:
                    log.exception("Could not read manual vocabulary")
            return _legacy_manual_words(self._app)

        def _read_learned_words(self):
            method = _callable(self._app, "list_learned_words")
            if method:
                try:
                    return _copy_list(method())
                except Exception:
                    log.exception("Could not read learned vocabulary")
            return _legacy_learned_words(self._app)

        def _config_get(self, *keys, default=None):
            config = getattr(self._app, "config", None)
            if config is None:
                return default
            try:
                return config.get(*keys, default=default)
            except Exception:
                return default

        def _legacy_set_setting(self, path, value):
            config = getattr(self._app, "config", None)
            if config is None:
                return False
            parts = tuple(part for part in path.split(".") if part)
            aliases = {
                ("dictation", "toggle_mode"): ("toggle_mode",),
                ("audio", "keep_microphone_ready"): ("keep_mic_stream_open",),
                ("privacy", "keep_microphone_ready"): ("keep_mic_stream_open",),
                ("privacy", "screen_context"): ("screen_context", "enabled"),
                ("privacy", "edit_selection"): ("edit_mode", "enabled"),
                ("privacy", "recent_context"): (
                    "formatting",
                    "include_recent_context",
                ),
                ("privacy", "transcript_logging"): ("log_transcripts",),
                ("privacy", "restore_clipboard"): ("restore_clipboard",),
                ("injection", "method"): ("injection",),
                ("injection", "restore_clipboard"): ("restore_clipboard",),
                ("transcription", "model"): ("model",),
                ("transcription", "device"): ("device",),
                ("transcription", "compute_type"): ("compute_type",),
                ("transcription", "language"): ("language",),
                ("transcription", "beam_size"): ("beam_size",),
            }
            parts = aliases.get(parts, parts)
            if not parts:
                raise KeyError("empty setting path")
            # The adapted app owns full typed validation.  This compatibility
            # path only accepts existing keys plus the isolated ui namespace.
            if parts[0] != "ui":
                node = getattr(config, "data", {})
                for part in parts:
                    if not isinstance(node, dict) or part not in node:
                        raise KeyError(path)
                    node = node[part]
            config.set(*parts, value=value)
            if parts == ("model",):
                _invoke_optional(self._app, ("change_model",), value)
            elif parts in {("toggle_mode",), ("hotkey",)}:
                _invoke_optional(self._app, ("reload_config",))
            return True

    _Bridge.__name__ = "Bridge"
    _Bridge.__qualname__ = "Bridge"
    _BRIDGE_TYPE = _Bridge
    return _BRIDGE_TYPE


def Bridge(app, interface_state=None, parent=None):
    """Construct the runtime QObject bridge without importing Qt at module load."""
    qt = _load_qt()
    if _prefer_software_renderer():
        try:
            graphics_api = qt.QSGRendererInterface.GraphicsApi.Software
            qt.QQuickWindow.setGraphicsApi(graphics_api)
            log.info("Using Qt's software renderer for this remote display session")
        except (AttributeError, RuntimeError) as exc:
            raise QtUnavailable("Qt's software renderer could not be enabled") from exc
    return _bridge_type(qt)(app, interface_state=interface_state, parent=parent)


def _resource_path(*parts: str) -> Path:
    """Resolve source-tree and PyInstaller onedir resources."""
    candidates = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root).joinpath(*parts))
    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root.joinpath(*parts))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _find_windows(roots):
    main = hud = None
    for root in roots:
        name = str(root.objectName() or "")
        if name == "mainWindow":
            main = root
        elif name == "hudWindow":
            hud = root
    if main is None and roots:
        main = roots[0]
    if hud is None and len(roots) > 1:
        hud = roots[1]
    return main, hud


def _component_errors(component) -> str:
    try:
        return "; ".join(error.toString() for error in component.errors())
    except (AttributeError, RuntimeError):
        return "unknown QML component error"


def _create_qml_root(qt, engine, path: Path, *, before_complete=None):
    """Create a QML root in two phases and retain its component.

    ``Component.onCompleted`` may show an ApplicationWindow.  The optional
    callback therefore runs after object construction but before completion,
    which is the safe point for native material and window-chrome setup.
    """

    component = qt.QQmlComponent(engine, qt.QUrl.fromLocalFile(str(path)))
    root = None
    try:
        if component.isError():
            raise QtUnavailable(f"QML failed to load: {path}: {_component_errors(component)}")
        root = component.beginCreate(engine.rootContext())
        if root is None:
            raise QtUnavailable(f"QML failed to create: {path}: {_component_errors(component)}")
        if before_complete is not None:
            before_complete(root)
        component.completeCreate()
        if component.isError():
            try:
                root.deleteLater()
            except (AttributeError, RuntimeError):
                pass
            raise QtUnavailable(
                f"QML failed to complete: {path}: {_component_errors(component)}"
            )
        return root, component
    except QtUnavailable:
        if root is not None:
            try:
                root.deleteLater()
            except (AttributeError, RuntimeError):
                pass
        component.deleteLater()
        raise
    except Exception as exc:
        if root is not None:
            try:
                root.deleteLater()
            except (AttributeError, RuntimeError):
                pass
        component.deleteLater()
        raise QtUnavailable(f"QML failed to create: {path}") from exc


def _native_preferences(app) -> tuple[dict[str, Any], dict[str, bool]]:
    method = _callable(app, "settings_snapshot")
    if method is not None:
        try:
            settings = _copy_mapping(method())
        except Exception:
            log.exception("Could not read settings for native window effects")
            settings = _legacy_settings_snapshot(app)
    else:
        settings = _legacy_settings_snapshot(app)
    accessibility = _system_accessibility_preferences()
    return settings, accessibility


def _effective_native_theme(qt, preference: object) -> str:
    value = str(preference or "system").lower()
    if value in {"light", "dark"}:
        return value
    try:
        scheme = qt.QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == qt.Qt.ColorScheme.Dark else "light"
    except (AttributeError, RuntimeError):
        return "light"


def _apply_native_preferences(
    native_window, qt, settings: Any, accessibility: Any = None
) -> None:
    """Apply user and OS preferences with explicit High Contrast priority."""

    snapshot = _copy_mapping(settings)
    ui = _copy_mapping(snapshot.get("ui"))
    environment = snapshot if accessibility is None else _copy_mapping(accessibility)
    theme_preference = str(ui.get("theme", "system")).lower()
    native_window.update_environment(
        high_contrast=(
            theme_preference == "high_contrast"
            or bool(environment.get("system_high_contrast", False))
        ),
        reduce_transparency=bool(
            environment.get("system_reduce_transparency", False)
        ),
    )
    native_window.applyVisualPreferences(
        _effective_native_theme(qt, theme_preference),
        str(ui.get("visual_effects", "system")),
    )


def _disconnect_signal_callbacks(connections: list[tuple[Any, Any]]) -> None:
    """Disconnect registered Qt callbacks before their captured state closes."""

    while connections:
        signal, callback = connections.pop()
        try:
            signal.disconnect(callback)
        except (AttributeError, RuntimeError, TypeError):
            pass


def _build_tray(qt, app, bridge, icon):
    tray = qt.QSystemTrayIcon(icon)
    menu = qt.QMenu()
    open_action = qt.QAction("Open Speakr", menu)
    status_action = qt.QAction("Getting Speakr ready", menu)
    status_action.setEnabled(False)
    toggle_action = qt.QAction("Dictation on", menu)
    toggle_action.setCheckable(True)
    browser_action = qt.QAction("Open browser fallback", menu)
    quit_action = qt.QAction("Quit Speakr", menu)

    open_action.triggered.connect(bridge.show_main)
    toggle_action.triggered.connect(bridge.toggleDictation)
    browser_action.triggered.connect(bridge.openBrowserFallback)
    quit_action.triggered.connect(bridge.quitApp)
    menu.addAction(open_action)
    menu.addAction(status_action)
    menu.addSeparator()
    menu.addAction(toggle_action)
    menu.addAction(browser_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.setToolTip("Speakr")

    def update_tray():
        state = bridge.state
        status = str(state.get("primary_text") or state.get("primary") or "Speakr")
        issue = state.get("last_issue") or {}
        if (
            state.get("capture") == "idle"
            and state.get("pipeline") == "idle"
            and issue.get("message")
        ):
            status = str(issue["message"])
        status_action.setText(status)
        toggle_action.blockSignals(True)
        toggle_action.setChecked(bool(state.get("enabled", True)))
        toggle_action.setText(
            "Dictation on" if state.get("enabled", True) else "Dictation off"
        )
        toggle_action.blockSignals(False)
        tray.setToolTip(f"Speakr — {status}")

    bridge.stateChanged.connect(update_tray)
    update_tray()
    try:
        double_click = qt.QSystemTrayIcon.ActivationReason.DoubleClick
        trigger = qt.QSystemTrayIcon.ActivationReason.Trigger
    except AttributeError:
        double_click = qt.QSystemTrayIcon.DoubleClick
        trigger = qt.QSystemTrayIcon.Trigger

    def activated(reason):
        if reason in (double_click, trigger):
            bridge.show_main()

    tray.activated.connect(activated)
    # Keep Python references alive for the lifetime of QSystemTrayIcon.
    tray._speakr_menu = menu
    tray._speakr_actions = (
        open_action,
        status_action,
        toggle_action,
        browser_action,
        quit_action,
    )
    return tray


def run_native_ui(app):
    """Run the native frontend and return the Qt event-loop exit code.

    Import, resource, or QML failures raise :class:`QtUnavailable` before a
    Qt tray is shown so the caller can start the legacy frontend without ever
    running two trays. Core startup is queued only after the local window is
    constructed, allowing the privacy explanation to render before any
    microphone permission prompt.
    """
    if threading.current_thread() is not threading.main_thread():
        raise QtUnavailable("the native UI must run on the main thread")
    qt = _load_qt()
    # Windows/macOS native control styles deliberately reject customized
    # backgrounds/content.  Quiet Signal supplies those accessible visuals,
    # so select Qt's supported customizable base before any QML is loaded.
    try:
        if qt.QQuickStyle.name() != "Basic":
            qt.QQuickStyle.setStyle("Basic")
    except RuntimeError as exc:
        raise QtUnavailable("the Qt Quick control style could not be selected") from exc
    qml_dir = _resource_path("speakr", "ui", "qml")
    main_qml = qml_dir / "Main.qml"
    hud_qml = qml_dir / "Hud.qml"
    icon_path = _resource_path("assets", "icon.png")
    missing = [str(path) for path in (main_qml, hud_qml, icon_path) if not path.is_file()]
    if missing:
        raise QtUnavailable("native UI resource missing: " + ", ".join(missing))

    qapp = qt.QApplication.instance()
    if qapp is None:
        try:
            qapp = qt.QApplication(sys.argv[:1])
        except Exception as exc:
            raise QtUnavailable("could not create QApplication") from exc
    elif not isinstance(qapp, qt.QApplication):
        raise QtUnavailable("an incompatible QCoreApplication already exists")
    qapp.setApplicationName("Speakr")
    qapp.setApplicationDisplayName("Speakr")
    qapp.setQuitOnLastWindowClosed(False)
    icon = qt.QIcon(str(icon_path))
    if icon.isNull():
        raise QtUnavailable("the local Speakr icon could not be loaded")
    qapp.setWindowIcon(icon)

    engine = qt.QQmlApplicationEngine()
    bridge = None
    native_window = None
    tray = None
    qml_roots = []
    qml_components = []
    system_preference_connections = []
    try:
        bridge = Bridge(app, getattr(app, "interface_state", None))
        engine.rootContext().setContextProperty("bridge", bridge)

        native_settings, accessibility = _native_preferences(app)
        native_ui = _copy_mapping(native_settings.get("ui"))
        explicit_high_contrast = (
            str(native_ui.get("theme", "system")).lower() == "high_contrast"
        )
        native_window = NativeWindowController(
            qt=qt,
            theme=_effective_native_theme(qt, native_ui.get("theme", "system")),
            visual_effects=str(native_ui.get("visual_effects", "system")),
            high_contrast=(
                explicit_high_contrast
                or bool(accessibility.get("system_high_contrast", False))
            ),
            reduce_transparency=bool(
                accessibility.get("system_reduce_transparency", False)
            ),
            software_renderer=_prefer_software_renderer(),
        )
        engine.rootContext().setContextProperty("nativeWindow", native_window)

        def sync_native_preferences(*_args):
            _apply_native_preferences(native_window, qt, bridge.settings)

        bridge.settingsChanged.connect(sync_native_preferences)

        def refresh_system_preferences(*_args):
            global _SYSTEM_ACCESSIBILITY
            _SYSTEM_ACCESSIBILITY = None
            current = _system_accessibility_preferences()
            _apply_native_preferences(native_window, qt, bridge.settings, current)
            bridge.refresh()

        qapp.paletteChanged.connect(refresh_system_preferences)
        system_preference_connections.append(
            (qapp.paletteChanged, refresh_system_preferences)
        )
        application_state_callback = (
            lambda state: refresh_system_preferences()
            if state == qt.Qt.ApplicationState.ApplicationActive
            else None
        )
        qapp.applicationStateChanged.connect(application_state_callback)
        system_preference_connections.append(
            (qapp.applicationStateChanged, application_state_callback)
        )

        main_root, main_component = _create_qml_root(
            qt, engine, main_qml, before_complete=native_window.attach
        )
        qml_roots.append(main_root)
        qml_components.append(main_component)
        hud_root, hud_component = _create_qml_root(qt, engine, hud_qml)
        qml_roots.append(hud_root)
        qml_components.append(hud_component)

        main_window, hud_window = _find_windows(qml_roots)
        if main_window is None or hud_window is None:
            raise QtUnavailable("QML did not create the main and HUD windows")

        tray = _build_tray(qt, app, bridge, icon)
        bridge.attach_frontend(main_window, hud_window, tray)
        app._qt_frontend = bridge
        tray.show()
        start_core = _callable(app, "_start_core")
        if start_core is not None:
            qt.QTimer.singleShot(120, start_core)
    except QtUnavailable:
        _disconnect_signal_callbacks(system_preference_connections)
        if tray is not None:
            tray.hide()
        if bridge is not None:
            bridge.close()
        if native_window is not None:
            native_window.detach()
        if getattr(app, "_qt_frontend", None) is bridge:
            app._qt_frontend = None
        for root in qml_roots:
            root.deleteLater()
        for component in qml_components:
            component.deleteLater()
        engine.deleteLater()
        raise
    except Exception as exc:
        _disconnect_signal_callbacks(system_preference_connections)
        if tray is not None:
            tray.hide()
        if bridge is not None:
            bridge.close()
        if native_window is not None:
            native_window.detach()
        if getattr(app, "_qt_frontend", None) is bridge:
            app._qt_frontend = None
        for root in qml_roots:
            root.deleteLater()
        for component in qml_components:
            component.deleteLater()
        engine.deleteLater()
        raise QtUnavailable("native UI initialization failed") from exc

    try:
        return int(qapp.exec())
    finally:
        _disconnect_signal_callbacks(system_preference_connections)
        if tray is not None:
            tray.hide()
        if bridge is not None:
            bridge.close()
        if native_window is not None:
            native_window.detach()
        if getattr(app, "_qt_frontend", None) is bridge:
            app._qt_frontend = None
        for root in qml_roots:
            root.deleteLater()
        for component in qml_components:
            component.deleteLater()
        engine.deleteLater()


__all__ = [
    "Bridge",
    "NativeUIUnavailable",
    "QtUnavailable",
    "qt_available",
    "run_native_ui",
]
