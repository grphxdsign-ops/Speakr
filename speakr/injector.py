"""System-wide text insertion into the focused control."""

import logging
import time

import pyperclip

from speakr.inputs import send_paste, type_text

log = logging.getLogger("speakr.injector")


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
