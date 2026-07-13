"""Pure presentation helpers for Speakr's existing hotkey behavior.

The Windows listener has always used toggle behavior for key combinations,
because combinations cannot be held reliably.  These helpers expose that
existing behavior to local UI surfaces without adding it to InterfaceState.
"""

from __future__ import annotations


def resolve_hotkey_mode(
    hotkey: object,
    requested_toggle_mode: object,
    *,
    platform: str,
) -> dict[str, bool]:
    """Return the effective UI mode without changing listener semantics."""

    forced = str(platform).casefold().startswith("win") and "+" in str(
        hotkey or ""
    )
    return {
        "effective_toggle_mode": bool(requested_toggle_mode) or forced,
        "toggle_mode_forced": forced,
    }


__all__ = ["resolve_hotkey_mode"]
