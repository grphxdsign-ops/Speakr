#!/usr/bin/env python3
"""Fail a release build when its artifact violates Speakr's UI boundary.

The scanner intentionally uses only the Python standard library so it can run
inside release jobs before an app is signed or wrapped in an installer.  It
supports both PyInstaller's Windows ``onedir`` layout and a macOS ``.app``
bundle (including the source-oriented bundle produced by ``package_mac.sh``).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


_FORBIDDEN_NAME_MARKERS = (
    "webview2",
    "qtwebengine",
    "qtwebview",
    "qtwebchannel",
    "chromium",
    "pyside6_addons",
    "pyside6-addons",
)
_FORBIDDEN_EXACT_PARTS = {"addons"}
# PySide6-Addons does not install under an ``Addons`` directory. Its normal
# layout uses concrete modules such as ``PySide6/QtCharts.pyd`` plus native
# libraries such as ``Qt6Charts.dll`` or ``libQt6Charts.so``. Match those real
# module families instead of relying on the distribution name appearing in
# the frozen artifact.
_FORBIDDEN_ADDON_FAMILIES = (
    "3danimation",
    "3dcore",
    "3dextras",
    "3dinput",
    "3dlogic",
    "3drender",
    "bluetooth",
    "charts",
    "datavisualization",
    "graphs",
    "httpserver",
    "location",
    "multimedia",
    "networkauth",
    "nfc",
    "pdf",
    "positioning",
    "quick3d",
    "scxml",
    "sensors",
    "spatialaudio",
    "statemachine",
    "texttospeech",
    "webchannel",
    "webengine",
    "websockets",
)
_REQUIRED_SUFFIXES = (
    "speakr/ui/qml/main.qml",
    "speakr/ui/qml/hud.qml",
    "assets/icon.png",
)
_TEXT_UI_SUFFIXES = {
    ".qml",
    ".svg",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".json",
}
_URL_PATTERN = re.compile(r"\b(?:https?|wss?)://[^\s\"'<>)}]+", re.IGNORECASE)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_UI_ASSET_BYTES = 4 * 1024 * 1024


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_forbidden_name(relative_path: str) -> bool:
    lowered = relative_path.casefold()
    if any(marker in lowered for marker in _FORBIDDEN_NAME_MARKERS):
        return True
    if any(
        part.casefold() in _FORBIDDEN_EXACT_PARTS
        for part in Path(relative_path).parts
    ):
        return True
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    return any(
        f"qt{family}" in compact or f"qt6{family}" in compact
        for family in _FORBIDDEN_ADDON_FAMILIES
    )


def _is_ui_asset(relative_path: str, path: Path) -> bool:
    lowered = relative_path.casefold()
    return path.suffix.casefold() in _TEXT_UI_SUFFIXES and (
        "/speakr/ui/" in f"/{lowered}" or "/assets/" in f"/{lowered}"
    )


def _remote_urls(path: Path) -> list[str]:
    try:
        if path.stat().st_size > _MAX_UI_ASSET_BYTES:
            return ["UI asset is unexpectedly larger than 4 MiB"]
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"UI asset could not be inspected as UTF-8: {exc}"]

    violations: list[str] = []
    for raw_url in _URL_PATTERN.findall(text):
        # QML may display/configure the user's local Ollama endpoint.  That is
        # the only URL class allowed by Speakr's local-only product contract.
        try:
            host = (urlsplit(raw_url.rstrip(".,;:")).hostname or "").casefold()
        except ValueError:
            host = ""
        if host not in _LOOPBACK_HOSTS:
            violations.append(raw_url)
    return violations


def scan_artifact(artifact: str | Path) -> list[str]:
    """Return human-readable violations found below *artifact*.

    An empty list means the release has the required native UI resources and
    contains no filename or UI URL that suggests an embedded/remote browser.
    """

    root = Path(artifact).resolve()
    if not root.exists():
        return [f"artifact does not exist: {root}"]
    if not root.is_dir():
        return [f"artifact must be an unpacked onedir or .app directory: {root}"]

    violations: list[str] = []
    relative_files: list[str] = []

    for path in root.rglob("*"):
        relative = _relative_posix(path, root)
        if _is_forbidden_name(relative):
            violations.append(f"forbidden embedded-browser/Addons name: {relative}")
        if not path.is_file():
            continue
        lowered = relative.casefold()
        relative_files.append(lowered)
        if _is_ui_asset(relative, path):
            for finding in _remote_urls(path):
                violations.append(f"remote URL in shipped UI asset {relative}: {finding}")

    for suffix in _REQUIRED_SUFFIXES:
        if not any(relative.endswith(suffix) for relative in relative_files):
            violations.append(f"required native UI resource is missing: {suffix}")

    return sorted(set(violations))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an unpacked Speakr release artifact before packaging."
    )
    parser.add_argument("artifact", help="Windows onedir or macOS Speakr.app path")
    args = parser.parse_args(argv)

    violations = scan_artifact(args.artifact)
    if violations:
        print("Speakr artifact privacy scan FAILED:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print(f"Speakr artifact privacy scan passed: {Path(args.artifact).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
