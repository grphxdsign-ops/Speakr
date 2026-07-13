#!/usr/bin/env python3
"""Validate Speakr's fixed-schema exact-artifact core proof receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_RECEIPT = {
    "blocked_attempts": 0,
    "cleanup_path": "rules",
    "core_ready": True,
    "guard_active": True,
    "model_ready": True,
    "model_source": "preseeded_local",
    "network_policy": "loopback_only",
    "offline_mode": True,
    "ollama": "disabled",
    "schema": 1,
}


def validate_receipt(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["receipt must be a JSON object"]

    errors = []
    expected_keys = set(EXPECTED_RECEIPT)
    actual_keys = set(payload)
    for key in sorted(expected_keys - actual_keys):
        errors.append(f"missing field: {key}")
    for key in sorted(actual_keys - expected_keys):
        errors.append(f"unexpected field: {key}")
    for key in sorted(expected_keys & actual_keys):
        expected = EXPECTED_RECEIPT[key]
        actual = payload[key]
        if type(actual) is not type(expected):
            errors.append(f"wrong type: {key}")
        elif actual != expected:
            errors.append(f"wrong value: {key}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("release core receipt invalid: unreadable JSON")
        return 1

    errors = validate_receipt(payload)
    if errors:
        print("release core receipt invalid: " + "; ".join(errors))
        return 1
    print("release core receipt valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
