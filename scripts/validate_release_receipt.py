#!/usr/bin/env python3
"""Validate the sanitized native-readiness receipt from a packaged app."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXACT_FIELDS = {
    "schema": 1,
    "frontend": "native",
    "tray_visible": True,
    "main_window_required": True,
    "main_window_visible": True,
    "main_window_exposed": True,
}

ALLOWED_FIELDS = {
    "material": {"mica", "vibrancy", "scene_glass", "solid"},
    "effect_tier": {"full", "reduced", "off"},
    "chrome": {"custom", "system_frame"},
    "renderer": {"hardware", "software"},
}

EXPECTED_KEYS = set(EXACT_FIELDS) | set(ALLOWED_FIELDS) | {
    "native_material_available"
}


def validate_receipt(path: Path) -> dict[str, object]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("release receipt must be a JSON object")
    if set(receipt) != EXPECTED_KEYS:
        missing = sorted(EXPECTED_KEYS - set(receipt))
        extra = sorted(set(receipt) - EXPECTED_KEYS)
        raise ValueError(f"invalid release receipt keys; missing={missing}, extra={extra}")
    for key, expected in EXACT_FIELDS.items():
        if receipt.get(key) != expected:
            raise ValueError(f"invalid release receipt {key}: {receipt.get(key)!r}")
    for key, allowed in ALLOWED_FIELDS.items():
        if receipt.get(key) not in allowed:
            raise ValueError(f"invalid release receipt {key}: {receipt.get(key)!r}")
    if type(receipt.get("native_material_available")) is not bool:
        raise ValueError("invalid release receipt native_material_available: expected boolean")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        validate_receipt(args.receipt)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(
            f"Native readiness receipt failed validation ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    print("Native readiness receipt passed (fixed schema, sanitized vocabulary).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
