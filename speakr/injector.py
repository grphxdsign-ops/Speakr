"""System-wide text insertion into the focused control, plus clipboard-based
selection reading for Edit Mode."""

import logging
import time

import pyperclip

from speakr.inputs import send_copy, send_paste, type_text

log = logging.getLogger("speakr.injector")

# Invisible-separator wrapped sentinel: never something a user would have
# in their clipboard.
_SENTINEL = "⁣speakr-no-selection⁣"


def read_selection_via_clipboard(timeout: float = 0.5) -> str:
    """Read the current selection by planting a sentinel, sending copy, and
    watching whether the clipboard changes. The original clipboard is
    restored before returning, whatever happens.

    Fallback for apps whose controls don't expose selection via UI Automation
    (e.g. classic Win32 Edit controls like Notepad's). Callers must NOT use
    this on terminal-like apps, where Ctrl+C is an interrupt."""
    try:
        original = pyperclip.paste()
    except pyperclip.PyperclipException:
        original = None
    selection = ""
    try:
        pyperclip.copy(_SENTINEL)
        time.sleep(0.03)
        send_copy()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.05)
            try:
                current = pyperclip.paste()
            except pyperclip.PyperclipException:
                continue
            if current != _SENTINEL:
                selection = current
                break
    finally:
        try:
            pyperclip.copy(original if original is not None else "")
        except pyperclip.PyperclipException:
            pass
    return selection


def inject(text: str, method: str = "paste", restore_clipboard: bool = True):
    if not text:
        return
    if method == "type":
        type_text(text)
        return

    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            previous = None
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        log.warning("Clipboard unavailable (%s), falling back to typing", exc)
        type_text(text)
        return
    time.sleep(0.05)  # let the clipboard settle before pasting
    send_paste()
    if restore_clipboard and previous is not None:
        # Give the target app time to read the clipboard before restoring.
        time.sleep(0.3)
        try:
            pyperclip.copy(previous)
        except pyperclip.PyperclipException:
            pass
