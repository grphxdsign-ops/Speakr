"""Platform dispatch for hotkey listening and text injection."""

import sys

IS_MAC = sys.platform == "darwin"

if IS_MAC:
    from speakr.mac_input import HotkeyListener, send_paste, type_text
else:
    from speakr.win_input import HotkeyListener, send_paste, type_text

__all__ = ["HotkeyListener", "send_paste", "type_text", "IS_MAC"]
