"""Windows input backend: global hotkey via the `keyboard` library,
injection keystrokes via Ctrl+V / simulated typing."""

from __future__ import annotations

import logging
import threading
import time

import keyboard

log = logging.getLogger("speakr.win_input")


class HotkeyListener:
    def __init__(self, hotkey, toggle_mode, on_press, on_release, on_toggle):
        self.hotkey = hotkey
        # Combos can't be held-to-talk reliably; they force toggle mode.
        self.toggle_mode = toggle_mode or "+" in hotkey
        self.on_press = on_press
        self.on_release = on_release
        self.on_toggle = on_toggle

    def start(self):
        if self.toggle_mode:
            keyboard.add_hotkey(self.hotkey, self.on_toggle)
            log.info("Registered toggle hotkey: %s", self.hotkey)
        else:
            keyboard.hook_key(self.hotkey, self._event)
            log.info("Registered hold-to-talk hotkey: %s", self.hotkey)

    def _event(self, event):
        if event.event_type == "down":
            self.on_press()
        elif event.event_type == "up":
            self.on_release()

    def stop(self):
        keyboard.unhook_all()


def capture_next_key(timeout=10.0, cancel_event=None):
    """Block until the next key-down anywhere and return its `keyboard`-style
    name — the same names hook_key accepts — or None on timeout. "esc" comes
    back as-is so callers can treat it as cancel. The active HotkeyListener
    must be stopped first: its hook would react to the key being sampled."""
    captured = {}
    done = threading.Event()

    def on_event(event):
        if event.event_type == "down" and event.name:
            captured["name"] = event.name.lower()
            done.set()

    hook = keyboard.hook(on_event)
    try:
        if timeout is None:
            while not done.wait(0.05):
                if cancel_event is not None and cancel_event.is_set():
                    break
        else:
            deadline = time.monotonic() + timeout
            while not done.wait(min(0.05, max(0.0, deadline - time.monotonic()))):
                if cancel_event is not None and cancel_event.is_set():
                    break
                if time.monotonic() >= deadline:
                    break
    finally:
        keyboard.unhook(hook)
    if cancel_event is not None and cancel_event.is_set():
        return None
    return captured.get("name")


def send_paste():
    keyboard.send("ctrl+v")


def send_copy():
    keyboard.send("ctrl+c")


def type_text(text):
    keyboard.write(text, delay=0.002)
