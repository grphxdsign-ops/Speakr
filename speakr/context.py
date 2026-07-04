"""Foreground-app detection for per-app tone. Read locally, used locally."""

import logging
import sys

log = logging.getLogger("speakr.context")

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
