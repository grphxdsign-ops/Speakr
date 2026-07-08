"""macOS input backend: fn-key push-to-talk via a Quartz event tap,
injection via Cmd+V / typed unicode events.

Permissions (System Settings -> Privacy & Security), granted to the app you
launch Speakr from (Terminal, iTerm, ...):
  - Microphone        (recording)
  - Input Monitoring  (seeing the hotkey)
  - Accessibility     (posting the paste keystroke)

The fn key never arrives as a normal key event — only as a flagsChanged
modifier event carrying keycode 63 and the SecondaryFn flag — hence the
event tap instead of an ordinary key hook.
"""

from __future__ import annotations

import logging
import threading
import time

import Quartz

log = logging.getLogger("speakr.mac_input")

# flagsChanged keycodes for modifier-style keys.
MODIFIER_KEYCODES = {
    "fn": 63,
    "globe": 63,
    "right cmd": 54,
    "left cmd": 55,
    "left shift": 56,
    "caps lock": 57,
    "left option": 58,
    "left ctrl": 59,
    "right shift": 60,
    "right option": 61,
    "right ctrl": 62,
}
MODIFIER_FLAGS = {
    63: Quartz.kCGEventFlagMaskSecondaryFn,
    54: Quartz.kCGEventFlagMaskCommand,
    55: Quartz.kCGEventFlagMaskCommand,
    56: Quartz.kCGEventFlagMaskShift,
    57: Quartz.kCGEventFlagMaskAlphaShift,
    58: Quartz.kCGEventFlagMaskAlternate,
    59: Quartz.kCGEventFlagMaskControl,
    60: Quartz.kCGEventFlagMaskShift,
    61: Quartz.kCGEventFlagMaskAlternate,
    62: Quartz.kCGEventFlagMaskControl,
}

KEY_V = 9  # kVK_ANSI_V
KEY_C = 8  # kVK_ANSI_C


class HotkeyListener:
    """Watches one modifier-style key (default: fn) system-wide."""

    def __init__(self, hotkey, toggle_mode, on_press, on_release, on_toggle):
        name = hotkey.strip().lower()
        if name not in MODIFIER_KEYCODES:
            log.warning(
                "Hotkey %r is not supported on macOS; using 'fn'. Supported: %s",
                hotkey, ", ".join(sorted(MODIFIER_KEYCODES)),
            )
            name = "fn"
        self.keycode = MODIFIER_KEYCODES[name]
        self.flag = MODIFIER_FLAGS[self.keycode]
        self.name = name
        self.toggle_mode = toggle_mode
        self.on_press = on_press
        self.on_release = on_release
        self.on_toggle = on_toggle
        self._pressed = False
        self._tap = None
        self._loop = None

    def start(self):
        threading.Thread(target=self._run, name="hotkey-tap", daemon=True).start()

    def _run(self):
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged),
            self._callback,
            None,
        )
        if self._tap is None:
            log.error(
                "Could not create the event tap. Grant Input Monitoring permission "
                "(System Settings -> Privacy & Security -> Input Monitoring) to the "
                "app you launch Speakr from, then restart Speakr."
            )
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        log.info("Registered %s hotkey: %s", "toggle" if self.toggle_mode else "hold-to-talk", self.name)
        Quartz.CFRunLoopRun()

    def _callback(self, proxy, type_, event, refcon):
        if type_ in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        if keycode != self.keycode:
            return event
        pressed = bool(Quartz.CGEventGetFlags(event) & self.flag)
        if pressed == self._pressed:
            return event
        self._pressed = pressed
        try:
            if self.toggle_mode:
                if pressed:
                    self.on_toggle()
            elif pressed:
                self.on_press()
            else:
                self.on_release()
        except Exception:
            log.exception("Hotkey callback failed")
        return event

    def stop(self):
        if self._loop is not None:
            Quartz.CFRunLoopStop(self._loop)


# Capture preference order: both "fn" and "globe" map to 63; report "fn".
_CAPTURE_NAMES = [
    "fn", "right cmd", "right option", "right ctrl", "right shift",
    "caps lock", "left option", "left ctrl", "left shift", "left cmd",
]


def capture_next_key(timeout=10.0):
    """Wait for the next modifier-style key press (the only hotkeys the Mac
    backend supports) and return its config name, or None on timeout. Runs
    its own short-lived listen-only event tap, so the active HotkeyListener
    should be stopped first to keep the sampled press from also dictating."""
    result = {}
    done = threading.Event()
    holder = {}

    def callback(proxy, type_, event, refcon):
        if type_ in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            return event
        keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        for name in _CAPTURE_NAMES:
            code = MODIFIER_KEYCODES[name]
            if keycode == code and flags & MODIFIER_FLAGS[code]:
                result["name"] = name
                done.set()
                break
        return event

    def run():
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged),
            callback,
            None,
        )
        if tap is None:
            log.error("capture_next_key: could not create event tap (Input Monitoring permission?)")
            done.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        holder["loop"] = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(holder["loop"], source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        Quartz.CFRunLoopRun()

    thread = threading.Thread(target=run, name="hotkey-capture", daemon=True)
    thread.start()
    done.wait(timeout)
    if holder.get("loop") is not None:
        Quartz.CFRunLoopStop(holder["loop"])
    return result.get("name")


def _send_cmd_key(keycode):
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(source, keycode, down)
        Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.01)


def send_paste():
    _send_cmd_key(KEY_V)


def send_copy():
    _send_cmd_key(KEY_C)


def type_text(text):
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for i in range(0, len(text), 20):
        chunk = text[i : i + 20]
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(source, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(chunk), chunk)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.005)
