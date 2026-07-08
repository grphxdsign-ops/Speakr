"""Platform dispatch for hotkey listening and text injection."""

from __future__ import annotations

import sys

IS_MAC = sys.platform == "darwin"

if IS_MAC:
    from speakr.mac_input import (
        HotkeyListener, capture_next_key, send_copy, send_paste, type_text,
    )
else:
    from speakr.win_input import (
        HotkeyListener, capture_next_key, send_copy, send_paste, type_text,
    )

__all__ = [
    "HotkeyListener", "capture_next_key", "send_copy", "send_paste", "type_text", "IS_MAC",
]
