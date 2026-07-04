"""Foreground-app detection and focused-control text capture.
Read locally, used in memory for one dictation, never persisted or logged."""

import logging
import sys
import threading

log = logging.getLogger("speakr.context")


def get_screen_context(max_chars=1200, timeout=1.0) -> str:
    """Text of the focused control, budgeted: runs in a side thread with a
    hard timeout so a stalled accessibility call can never block dictation.
    One query per dictation — no polling, no tree walking."""
    result = {}

    def worker():
        result["text"] = _read_focused_text(max_chars)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    return result.get("text", "")


def get_selected_text(max_chars=4000, timeout=1.0) -> str:
    """Currently selected text in the focused control (for Edit Mode), with
    the same thread+timeout budget as get_screen_context."""
    result = {}

    def worker():
        result["text"] = _read_selected_text(max_chars)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    return result.get("text", "")

if sys.platform == "darwin":

    def get_active_app() -> dict:
        """Return {"exe": "slack", "title": "..."} for the frontmost app.
        The title needs Screen Recording permission; empty without it."""
        result = {"exe": "", "title": ""}
        try:
            import Quartz
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return result
            result["exe"] = (app.localizedName() or "").lower()
            pid = app.processIdentifier()
            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly
                | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            ) or []
            for info in windows:
                if info.get("kCGWindowOwnerPID") == pid and info.get("kCGWindowLayer", 1) == 0:
                    result["title"] = info.get("kCGWindowName") or ""
                    break
        except Exception as exc:
            log.warning("Active-app detection failed: %s", exc)
        return result

    def _read_focused_text(max_chars) -> str:
        # macOS equivalent (AXUIElement) not implemented yet.
        return ""

    def _read_selected_text(max_chars) -> str:
        # macOS equivalent (AXSelectedText) not implemented yet.
        return ""

else:
    import ctypes
    import ctypes.wintypes
    import os

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def get_active_app() -> dict:
        """Return {"exe": "slack.exe", "title": "..."} for the foreground window."""
        result = {"exe": "", "title": ""}
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return result

            length = user32.GetWindowTextLengthW(hwnd)
            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buf, length + 1)
            result["title"] = title_buf.value

            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if handle:
                try:
                    size = ctypes.wintypes.DWORD(1024)
                    path_buf = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, path_buf, ctypes.byref(size)):
                        result["exe"] = os.path.basename(path_buf.value).lower()
                finally:
                    kernel32.CloseHandle(handle)
        except Exception as exc:
            log.warning("Active-app detection failed: %s", exc)
        return result

    def _read_focused_text(max_chars) -> str:
        """Focused control's text via UI Automation (what Wispr Flow's
        'context awareness' reads). Single element query, size-capped."""
        try:
            import comtypes
            import comtypes.client

            try:
                comtypes.CoInitialize()
            except OSError:
                pass
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import (
                CUIAutomation,
                IUIAutomation,
                IUIAutomationTextPattern,
                IUIAutomationValuePattern,
            )

            uia = comtypes.CoCreateInstance(
                CUIAutomation._reg_clsid_, interface=IUIAutomation,
                clsctx=comtypes.CLSCTX_INPROC_SERVER,
            )
            element = uia.GetFocusedElement()
            if not element:
                return ""
            UIA_TEXT_PATTERN, UIA_VALUE_PATTERN = 10014, 10002
            try:
                pattern = element.GetCurrentPattern(UIA_TEXT_PATTERN)
                if pattern:
                    text_pattern = pattern.QueryInterface(IUIAutomationTextPattern)
                    text = text_pattern.DocumentRange.GetText(max_chars)
                    if text and text.strip():
                        return text
            except Exception:
                pass
            try:
                pattern = element.GetCurrentPattern(UIA_VALUE_PATTERN)
                if pattern:
                    value_pattern = pattern.QueryInterface(IUIAutomationValuePattern)
                    return (value_pattern.CurrentValue or "")[:max_chars]
            except Exception:
                pass
            return (element.CurrentName or "")[:max_chars]
        except Exception as exc:
            log.debug("Screen-text capture unavailable: %s", exc)
            return ""

    def _read_selected_text(max_chars) -> str:
        """Selected text of the focused control via UIA TextPattern."""
        try:
            import comtypes
            import comtypes.client

            try:
                comtypes.CoInitialize()
            except OSError:
                pass
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import (
                CUIAutomation,
                IUIAutomation,
                IUIAutomationTextPattern,
            )

            uia = comtypes.CoCreateInstance(
                CUIAutomation._reg_clsid_, interface=IUIAutomation,
                clsctx=comtypes.CLSCTX_INPROC_SERVER,
            )
            element = uia.GetFocusedElement()
            if not element:
                return ""
            UIA_TEXT_PATTERN = 10014
            pattern = element.GetCurrentPattern(UIA_TEXT_PATTERN)
            if not pattern:
                return ""
            text_pattern = pattern.QueryInterface(IUIAutomationTextPattern)
            selection = text_pattern.GetSelection()
            if not selection or selection.Length == 0:
                return ""
            text = selection.GetElement(0).GetText(max_chars) or ""
            return text
        except Exception as exc:
            log.debug("Selection capture unavailable: %s", exc)
            return ""
