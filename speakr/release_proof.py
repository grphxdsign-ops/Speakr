"""Sanitized, opt-in readiness evidence for packaged-artifact smoke tests.

The installed application never writes this receipt unless the release job
sets ``SPEAKR_RELEASE_PROOF_PATH``.  Values are a fixed capability vocabulary;
no audio, transcript, selection, clipboard, screen, window-title, or machine
path data enters the payload.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


PROOF_PATH_ENV = "SPEAKR_RELEASE_PROOF_PATH"
PROOF_QUIT_ENV = "SPEAKR_RELEASE_PROOF_QUIT"
SCHEMA_VERSION = 1

_MATERIALS = {"mica", "vibrancy", "scene_glass", "solid"}
_EFFECT_TIERS = {"full", "reduced", "off"}
_RENDERERS = {"hardware", "software"}
_CHROME = {"custom", "system_frame"}


def proof_requested() -> bool:
    return bool(str(os.environ.get(PROOF_PATH_ENV, "")).strip())


def quit_after_proof_requested() -> bool:
    return str(os.environ.get(PROOF_QUIT_ENV, "")).strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _choice(value: object, allowed: set[str], fallback: str) -> str:
    candidate = str(value or "").strip().casefold()
    return candidate if candidate in allowed else fallback


def write_native_ready(
    *,
    tray_visible: object,
    main_window_visible: object,
    main_window_exposed: object,
    main_window_required: object,
    material: object,
    effect_tier: object,
    native_material_available: object,
    custom_chrome_enabled: object,
    software_renderer: object,
) -> bool:
    """Atomically write a fixed-vocabulary native-frontend receipt."""

    raw_path = str(os.environ.get(PROOF_PATH_ENV, "")).strip()
    if not raw_path:
        return False
    destination = Path(raw_path).expanduser()
    payload = {
        "schema": SCHEMA_VERSION,
        "frontend": "native",
        "tray_visible": bool(tray_visible),
        "main_window_visible": bool(main_window_visible),
        "main_window_exposed": bool(main_window_exposed),
        "main_window_required": bool(main_window_required),
        "material": _choice(material, _MATERIALS, "solid"),
        "effect_tier": _choice(effect_tier, _EFFECT_TIERS, "off"),
        "native_material_available": bool(native_material_available),
        "chrome": "custom" if bool(custom_chrome_enabled) else "system_frame",
        "renderer": "software" if bool(software_renderer) else "hardware",
    }
    temporary = destination.with_name(
        f".{destination.name}.{secrets.token_hex(8)}.tmp"
    )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink()
        except OSError:
            pass
        return False


__all__ = [
    "PROOF_PATH_ENV",
    "PROOF_QUIT_ENV",
    "SCHEMA_VERSION",
    "proof_requested",
    "quit_after_proof_requested",
    "write_native_ready",
]
