"""Windows input backend: global hotkey via the `keyboard` library,
injection keystrokes via Ctrl+V / simulated typing."""

import logging

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


def send_paste():
    keyboard.send("ctrl+v")


def send_copy():
    keyboard.send("ctrl+c")


def type_text(text):
    keyboard.write(text, delay=0.002)
