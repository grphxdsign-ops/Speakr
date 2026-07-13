#!/usr/bin/env python3
"""Verify that a release is built from Essentials without PySide6-Addons."""

from __future__ import annotations

import importlib.metadata as metadata
import sys


EXPECTED_ESSENTIALS = "6.11.1"


def boundary_violations() -> list[str]:
    violations: list[str] = []
    try:
        essentials = metadata.version("PySide6-Essentials")
    except metadata.PackageNotFoundError:
        violations.append("PySide6-Essentials is not installed")
    else:
        if essentials != EXPECTED_ESSENTIALS:
            violations.append(
                f"PySide6-Essentials must be {EXPECTED_ESSENTIALS}, found {essentials}"
            )

    try:
        addons = metadata.version("PySide6-Addons")
    except metadata.PackageNotFoundError:
        pass
    else:
        violations.append(
            f"PySide6-Addons {addons} is installed; use an Essentials-only build environment"
        )
    return violations


def main() -> int:
    violations = boundary_violations()
    if violations:
        print("Qt release dependency boundary FAILED:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1
    print(f"Qt release dependency boundary passed: Essentials {EXPECTED_ESSENTIALS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
