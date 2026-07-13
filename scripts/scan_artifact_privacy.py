#!/usr/bin/env python3
"""Fail a release build when its unpacked artifact violates Speakr's boundary.

The scanner uses the Python standard library for files/ZIPs and, when it sees
the PyInstaller executable, the already-installed release-build PyInstaller
reader for that proprietary container.  It inspects both Windows ``onedir``
and macOS ``.app`` shapes before either is wrapped or signed.  Findings contain
only artifact-relative names: host paths and exception messages are never
emitted.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

try:  # Present in release builds; optional for source-only fake-artifact tests.
    from PyInstaller.archive.readers import CArchiveReader as _CArchiveReader
except ImportError:  # pragma: no cover - exercised by ordinary dependency CI.
    _CArchiveReader = None


_FORBIDDEN_BROWSER_NAME_MARKERS = (
    "webview2",
    "msedgewebview2",
    "qtwebengine",
    "qtwebview",
    "qtwebchannel",
    "chromium",
    "libcef",
    "cef_sandbox",
    "chrome_elf",
)
_FORBIDDEN_BROWSER_BASENAMES = {
    "cef.pak",
    "cef_100_percent.pak",
    "cef_200_percent.pak",
    "chrome_100_percent.pak",
    "chrome_200_percent.pak",
    "devtools_resources.pak",
    "icudtl.dat",
    "resources.pak",
    "snapshot_blob.bin",
    "v8_context_snapshot.bin",
}
_FORBIDDEN_EXACT_PARTS = {"addons"}

# PySide6-Addons installs concrete Qt modules rather than an ``Addons``
# directory.  Match those families in filenames such as ``QtCharts.pyd``,
# ``Qt6Charts.dll``, and ``libQt6Charts.so.6``.
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

_FORBIDDEN_SDK_NAME_MARKERS = (
    "sentry_sdk",
    "sentry-native",
    "sentry.framework",
    "bugsnag",
    "rollbar",
    "crashlytics",
    "crashpad",
    "breakpad",
    "appcenter",
    "datadog",
    "newrelic",
    "new_relic",
    "mixpanel",
    "amplitude",
    "posthog",
    "segment_analytics",
    "opentelemetry",
    "winsparkle",
    "sparkle.framework",
    "squirrel",
    "pyupdater",
    "auto_updater",
    "autoupdater",
    "updatechecker",
)
_FORBIDDEN_SDK_BASENAMES = {
    "update.exe",
    "updater.exe",
    "crashpad_handler",
    "crashpad_handler.exe",
}

_BINARY_MARKER_GROUPS = {
    "embedded-browser engine": (
        b"qtwebengineprocess",
        b"qtwebenginecore",
        b"webview2loader",
        b"msedgewebview2",
        b"cef_sandbox",
        b"chrome_elf",
        b"libcef",
    ),
    "telemetry/crash-report SDK": (
        b"sentry_sdk",
        b"crashpad_handler",
        b"bugsnag.notify",
        b"rollbar.com/api",
        b"api.mixpanel.com",
        b"api.segment.io",
        b"api2.amplitude.com",
        b"app.posthog.com",
        b"datadoghq.com",
        b"newrelic.com",
    ),
    "updater SDK": (
        b"winsparkle",
        b"spuupdater",
        b"pyupdater",
        b"squirrelawareversion",
    ),
}

_REQUIRED_SUFFIXES = {
    "main_qml": "speakr/ui/qml/main.qml",
    "hud_qml": "speakr/ui/qml/hud.qml",
    "icon": "assets/icon.png",
    "native_marker": "speakr/ui/native_interface_capabilities.json",
}
_NOTICE_PATHS = {
    "third_party_notices.txt",
    "contents/resources/third_party_notices.txt",
}
_EXPECTED_NATIVE_MARKER = {
    "controller": "NativeWindowController",
    "schema": 1,
}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_UI_SUFFIXES = {".qml", ".svg", ".html", ".htm", ".css", ".js", ".mjs"}
_CONFIG_SUFFIXES = {
    ".cfg",
    ".conf",
    ".ini",
    ".json",
    ".plist",
    ".properties",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
_APP_CONFIG_BASENAMES = {
    "appsettings.json",
    "config.json",
    "preferences.json",
    "release.json",
    "settings.json",
    "update.json",
    "updates.json",
}
_TEXT_SUFFIXES = _UI_SUFFIXES | _CONFIG_SUFFIXES | {".md", ".txt"}
_APP_CODE_SUFFIXES = _TEXT_SUFFIXES | {".py"}
_URL_PATTERN = re.compile(r"\b(?:https?|wss?)://[^\s\"'<>)}]+", re.IGNORECASE)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_INERT_SCHEMA_URLS = {"http://www.apple.com/DTDs/PropertyList-1.0.dtd"}
_QT_NETWORK_API_PATTERNS = (
    re.compile(r"(?m)^\s*import\s+QtNetwork(?:\s|$)"),
    re.compile(r"\bPySide6\.QtNetwork\b"),
    re.compile(r"(?m)^\s*from\s+PySide6\s+import[^\n]*\bQtNetwork\b"),
    re.compile(r"\bQNetworkAccessManager\b"),
)
_SDK_SOURCE_PATTERNS = (
    re.compile(
        r"(?mi)^\s*(?:from|import)\s+"
        r"(?:sentry_sdk|bugsnag|rollbar|datadog|newrelic|mixpanel|"
        r"amplitude|posthog|opentelemetry)\b"
    ),
    re.compile(
        r"\b(?:Sentry|bugsnag|rollbar|mixpanel|posthog|amplitude)\."
        r"(?:init|configure|notify|capture|track)\s*\(",
        re.IGNORECASE,
    ),
)

_MAX_TEXT_BYTES = 4 * 1024 * 1024
_MAX_NOTICE_BYTES = 512 * 1024
_MAX_MARKER_BYTES = 4096
_MAX_ARCHIVE_ENTRIES = 20_000
_MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_DEPTH = 2
_BINARY_CHUNK_BYTES = 1024 * 1024


@dataclass
class _ScanState:
    seen: set[str] = field(default_factory=set)
    valid: set[str] = field(default_factory=set)
    violations: list[str] = field(default_factory=list)

    def add(self, finding: str) -> None:
        self.violations.append(finding)


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _normalise_relative(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _compact_basename(relative_path: str) -> str:
    basename = PurePosixPath(_normalise_relative(relative_path)).name.casefold()
    return re.sub(r"[^a-z0-9]", "", basename)


def _name_findings(relative_path: str) -> list[str]:
    """Return policy categories triggered by an artifact-relative name."""

    normalised = _normalise_relative(relative_path)
    lowered = normalised.casefold()
    basename = PurePosixPath(normalised).name.casefold()
    parts = {part.casefold() for part in PurePosixPath(normalised).parts}
    compact = _compact_basename(normalised)
    findings: list[str] = []

    browser_name = (
        any(marker in lowered for marker in _FORBIDDEN_BROWSER_NAME_MARKERS)
        or basename in _FORBIDDEN_BROWSER_BASENAMES
        or (basename.endswith(".pak") and "qtwebengine" in lowered)
    )
    if browser_name:
        findings.append("embedded-browser/WebView module")

    addons_name = (
        "pyside6_addons" in lowered
        or "pyside6-addons" in lowered
        or bool(parts & _FORBIDDEN_EXACT_PARTS)
        or any(
            compact.startswith((f"qt{family}", f"qt6{family}", f"libqt6{family}"))
            for family in _FORBIDDEN_ADDON_FAMILIES
        )
    )
    if addons_name:
        findings.append("PySide6-Addons module family")

    sdk_name = basename in _FORBIDDEN_SDK_BASENAMES or any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])",
            lowered,
        )
        for marker in _FORBIDDEN_SDK_NAME_MARKERS
    )
    if sdk_name:
        findings.append("updater/telemetry/crash-report SDK")

    return findings


def _safe_member_name(name: str) -> tuple[str | None, bool]:
    normalised = name.replace("\\", "/")
    pure = PurePosixPath(normalised)
    unsafe = (
        normalised.startswith("/")
        or bool(re.match(r"^[A-Za-z]:", normalised))
        or ".." in pure.parts
    )
    if unsafe:
        return None, True
    cleaned = "/".join(part for part in pure.parts if part not in {"", "."})
    return cleaned[:300], False


def _display_url(raw_url: str) -> str:
    """Strip credentials/query/fragment before a URL reaches build logs."""

    candidate = raw_url.rstrip(".,;:")
    try:
        parsed = urlsplit(candidate)
        host = parsed.hostname or "invalid-host"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        safe = urlunsplit((parsed.scheme, f"{host}{port}", parsed.path, "", ""))
    except (TypeError, ValueError):
        safe = "unparseable remote URL"
    if len(safe) > 200:
        safe = safe[:197] + "..."
    return safe


def _remote_urls(text: str) -> list[str]:
    violations: list[str] = []
    for raw_url in _URL_PATTERN.findall(text):
        candidate = raw_url.rstrip(".,;:")
        if candidate in _INERT_SCHEMA_URLS:
            continue
        try:
            host = (urlsplit(candidate).hostname or "").casefold()
        except ValueError:
            host = ""
        if host not in _LOOPBACK_HOSTS:
            violations.append(_display_url(candidate))
    return violations


def _strip_bundle_prefix(parts: tuple[str, ...]) -> tuple[str, ...]:
    lowered = tuple(part.casefold() for part in parts)
    if lowered[:2] == ("contents", "resources"):
        return parts[2:]
    if lowered[:1] == ("_internal",):
        return parts[1:]
    return parts


def _is_app_owned_text(relative_path: str) -> bool:
    """Select app UI/config/text without scanning dependency licenses/QML."""

    normalised = _normalise_relative(relative_path)
    pure = PurePosixPath(normalised)
    lowered_parts = tuple(part.casefold() for part in pure.parts)
    suffix = pure.suffix.casefold()
    if suffix not in _TEXT_SUFFIXES:
        return False

    lowered = "/".join(lowered_parts)
    if "/speakr/ui/" in f"/{lowered}" or "/assets/" in f"/{lowered}":
        return True
    if lowered == "contents/info.plist":
        return True
    if lowered in _NOTICE_PATHS:
        return True
    if pure.name.casefold() in _APP_CONFIG_BASENAMES:
        return True
    if suffix in {".cfg", ".conf", ".ini", ".plist", ".toml", ".yaml", ".yml"}:
        return True

    app_parts = _strip_bundle_prefix(pure.parts)
    app_lowered = tuple(part.casefold() for part in app_parts)
    if not app_lowered:
        return False
    if len(app_lowered) == 1:
        return True
    if app_lowered[0] == "speakr":
        return True
    return False


def _is_app_owned_code(relative_path: str) -> bool:
    normalised = _normalise_relative(relative_path)
    pure = PurePosixPath(normalised)
    if pure.suffix.casefold() not in _APP_CODE_SUFFIXES:
        return False
    if _is_app_owned_text(normalised):
        return True
    app_parts = tuple(part.casefold() for part in _strip_bundle_prefix(pure.parts))
    return len(app_parts) > 1 and app_parts[0] == "speakr"


def _decode_utf8(data: bytes, relative_path: str, state: _ScanState) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeError:
        state.add(f"app-owned text is not UTF-8: {relative_path}")
        return None


def _inspect_app_text(
    data: bytes,
    relative_path: str,
    state: _ScanState,
    *,
    logical_path: str | None = None,
) -> None:
    if len(data) > _MAX_TEXT_BYTES:
        state.add(f"app-owned text exceeds the 4 MiB inspection limit: {relative_path}")
        return
    text = _decode_utf8(data, relative_path, state)
    if text is None:
        return

    ownership_path = logical_path or relative_path
    if _is_app_owned_text(ownership_path):
        for remote_url in _remote_urls(text):
            state.add(f"remote URL in shipped UI/config/text {relative_path}: {remote_url}")

    if _is_app_owned_code(ownership_path):
        if any(pattern.search(text) for pattern in _QT_NETWORK_API_PATTERNS):
            state.add(
                "app-owned code imports/uses QtNetwork instead of the permitted "
                f"transitive runtime binding: {relative_path}"
            )
        if any(pattern.search(text) for pattern in _SDK_SOURCE_PATTERNS):
            state.add(f"telemetry/crash-report SDK use in app-owned code: {relative_path}")


def _binary_patterns() -> tuple[tuple[str, bytes], ...]:
    patterns: list[tuple[str, bytes]] = []
    for category, markers in _BINARY_MARKER_GROUPS.items():
        for marker in markers:
            patterns.append((category, marker.lower()))
            patterns.append((category, marker.decode("ascii").encode("utf-16le").lower()))
    return tuple(patterns)


_BINARY_PATTERNS = _binary_patterns()
_MAX_BINARY_MARKER_BYTES = max(len(marker) for _, marker in _BINARY_PATTERNS)


def _binary_marker_findings(chunks: Iterable[bytes]) -> set[str]:
    """Scan an iterable of byte chunks while preserving cross-chunk matches."""

    findings: set[str] = set()
    overlap = b""
    for raw in chunks:
        lowered = (overlap + raw).lower()
        for category, marker in _BINARY_PATTERNS:
            if marker in lowered:
                findings.add(category)
        overlap = lowered[-(_MAX_BINARY_MARKER_BYTES - 1) :]
    return findings


def _bytes_chunks(data: bytes) -> Iterator[bytes]:
    return (data[offset : offset + _BINARY_CHUNK_BYTES] for offset in range(0, len(data), _BINARY_CHUNK_BYTES))


def _file_chunks(path: Path) -> Iterator[bytes]:
    def iterator() -> Iterator[bytes]:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_BINARY_CHUNK_BYTES)
                if not chunk:
                    return
                yield chunk

    return iterator()


def _read_file(path: Path, limit: int, relative_path: str, state: _ScanState) -> bytes | None:
    try:
        size = path.stat().st_size
        if size > limit:
            state.add(f"required/app-owned resource exceeds its inspection limit: {relative_path}")
            return None
        return path.read_bytes()
    except OSError as exc:
        state.add(f"artifact file could not be inspected ({type(exc).__name__}): {relative_path}")
        return None


def _requirement_key(relative_path: str) -> str | None:
    lowered = _normalise_relative(relative_path).casefold()
    if lowered in _NOTICE_PATHS:
        return "qt_notice"
    for key, suffix in _REQUIRED_SUFFIXES.items():
        if lowered.endswith(suffix):
            return key
    return None


def _inspect_requirement(
    path: Path, relative_path: str, key: str, state: _ScanState
) -> bytes | None:
    state.seen.add(key)
    limit = _MAX_NOTICE_BYTES if key == "qt_notice" else _MAX_TEXT_BYTES
    if key == "native_marker":
        limit = _MAX_MARKER_BYTES
    if key == "icon":
        limit = _MAX_TEXT_BYTES
    data = _read_file(path, limit, relative_path, state)
    if data is None:
        return None

    valid = False
    if key in {"main_qml", "hud_qml"}:
        text = _decode_utf8(data, relative_path, state)
        valid = bool(text and "import QtQuick" in text)
    elif key == "icon":
        valid = data.startswith(_PNG_SIGNATURE)
    elif key == "qt_notice":
        text = _decode_utf8(data, relative_path, state)
        lowered = text.casefold() if text is not None else ""
        valid = "qt for python" in lowered and "lgpl" in lowered
    elif key == "native_marker":
        try:
            marker = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            marker = None
        valid = marker == _EXPECTED_NATIVE_MARKER

    if valid:
        state.valid.add(key)
    else:
        labels = {
            "main_qml": "Main.qml with a QtQuick import",
            "hud_qml": "Hud.qml with a QtQuick import",
            "icon": "local PNG icon",
            "qt_notice": "Qt LGPL third-party notice",
            "native_marker": "exact NativeWindowController capability marker",
        }
        state.add(f"required {labels[key]} is invalid: {relative_path}")
    return data


def _inspect_archive_bytes(
    data: bytes,
    archive_label: str,
    state: _ScanState,
    *,
    depth: int,
) -> None:
    if depth > _MAX_ARCHIVE_DEPTH:
        state.add(f"nested archive exceeds safe inspection depth: {archive_label}")
        return
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile):
        state.add(f"archive could not be safely inspected: {archive_label}")
        return
    _inspect_zip(archive, archive_label, state, depth=depth)


def _inspect_zip(
    archive: zipfile.ZipFile,
    archive_label: str,
    state: _ScanState,
    *,
    depth: int,
) -> None:
    try:
        members = archive.infolist()
    except (OSError, zipfile.BadZipFile):
        state.add(f"archive directory could not be inspected: {archive_label}")
        return

    if len(members) > _MAX_ARCHIVE_ENTRIES:
        state.add(f"archive exceeds safe entry-count limit: {archive_label}")
        return
    if sum(info.file_size for info in members) > _MAX_ARCHIVE_TOTAL_BYTES:
        state.add(f"archive exceeds safe expanded-size limit: {archive_label}")
        return

    for info in members:
        member_name, unsafe = _safe_member_name(info.filename)
        if unsafe:
            state.add(f"archive contains an unsafe member path: {archive_label}")
            continue
        if not member_name or info.is_dir():
            continue
        display = f"{archive_label}!{member_name}"
        for category in _name_findings(member_name):
            state.add(f"forbidden {category} in archive: {display}")
        if info.flag_bits & 0x1:
            state.add(f"encrypted archive member cannot be inspected: {display}")
            continue
        if info.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
            state.add(f"archive member exceeds safe inspection limit: {display}")
            continue
        if info.file_size > 1024 * 1024 and info.compress_size > 0:
            if info.file_size / info.compress_size > 1000:
                state.add(f"archive member has an unsafe compression ratio: {display}")
                continue
        try:
            member_data = archive.read(info)
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            state.add(
                f"archive member could not be inspected ({type(exc).__name__}): {display}"
            )
            continue

        if _is_app_owned_code(member_name):
            _inspect_app_text(member_data, display, state, logical_path=member_name)
        for category in _binary_marker_findings(_bytes_chunks(member_data)):
            state.add(f"forbidden {category} marker in archive member: {display}")

        nested = io.BytesIO(member_data)
        if zipfile.is_zipfile(nested):
            _inspect_archive_bytes(member_data, display, state, depth=depth + 1)


def _inspect_archive_path(path: Path, relative_path: str, state: _ScanState) -> bool:
    try:
        is_zip = zipfile.is_zipfile(path)
    except OSError as exc:
        state.add(f"archive probe failed ({type(exc).__name__}): {relative_path}")
        return False
    if not is_zip:
        if path.suffix.casefold() in {".egg", ".whl", ".zip"}:
            state.add(f"archive could not be safely inspected: {relative_path}")
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            _inspect_zip(archive, relative_path, state, depth=0)
    except (OSError, zipfile.BadZipFile) as exc:
        state.add(f"archive could not be inspected ({type(exc).__name__}): {relative_path}")
    return True


def _is_main_pyinstaller_executable(relative_path: str) -> bool:
    lowered = _normalise_relative(relative_path).casefold()
    return lowered == "speakr.exe" or lowered == "contents/macos/speakr"


def _inspect_pyinstaller_executable(
    path: Path, relative_path: str, state: _ScanState
) -> None:
    """Inspect CArchive/PYZ module names without extracting either archive."""

    if not _is_main_pyinstaller_executable(relative_path):
        return
    if _CArchiveReader is None:
        state.add(
            "PyInstaller reader is unavailable; embedded module names cannot be "
            f"proved clean: {relative_path}"
        )
        return
    try:
        reader = _CArchiveReader(str(path))
        top_level_names = tuple(reader.toc)
    except Exception as exc:  # PyInstaller has version-specific reader errors.
        state.add(
            "PyInstaller executable could not be inspected "
            f"({type(exc).__name__}): {relative_path}"
        )
        return

    for name in top_level_names:
        safe_name, unsafe = _safe_member_name(str(name))
        if unsafe or not safe_name:
            state.add(f"PyInstaller executable has an unsafe member name: {relative_path}")
            continue
        for category in _name_findings(safe_name.replace(".", "/")):
            state.add(
                f"forbidden {category} in PyInstaller executable: "
                f"{relative_path}!{safe_name}"
            )
        if not safe_name.casefold().endswith(".pyz"):
            continue
        try:
            embedded = reader.open_embedded_archive(name)
            module_names = tuple(embedded.toc)
        except Exception as exc:
            state.add(
                "embedded PyInstaller PYZ could not be inspected "
                f"({type(exc).__name__}): {relative_path}!{safe_name}"
            )
            continue
        for module_name in module_names:
            safe_module, module_unsafe = _safe_member_name(
                str(module_name).replace(".", "/")
            )
            if module_unsafe or not safe_module:
                state.add(
                    f"embedded PyInstaller PYZ has an unsafe module name: "
                    f"{relative_path}!{safe_name}"
                )
                continue
            for category in _name_findings(safe_module):
                state.add(
                    f"forbidden {category} in embedded PyInstaller module: "
                    f"{relative_path}!{safe_name}!{safe_module}"
                )


def _validate_symlink(path: Path, root: Path, relative_path: str, state: _ScanState) -> bool:
    if not path.is_symlink():
        return True
    try:
        target = path.resolve(strict=False)
        target.relative_to(root)
    except (OSError, ValueError):
        state.add(f"symlink escapes the artifact boundary: {relative_path}")
        return False
    # Internal framework symlinks are legitimate. Their targets are reached by
    # normal traversal, so do not read through the alias here.
    return False


def _walk_entries(root: Path, state: _ScanState) -> Iterator[Path]:
    def on_error(exc: OSError) -> None:
        state.add(f"artifact directory could not be enumerated ({type(exc).__name__})")

    for current, directories, files in os.walk(root, followlinks=False, onerror=on_error):
        current_path = Path(current)
        for name in sorted(directories + files, key=str.casefold):
            yield current_path / name


def _finalise_requirements(state: _ScanState) -> None:
    labels = {
        "main_qml": "speakr/ui/qml/Main.qml",
        "hud_qml": "speakr/ui/qml/Hud.qml",
        "icon": "assets/icon.png",
        "qt_notice": "THIRD_PARTY_NOTICES.txt with the Qt LGPL notice",
        "native_marker": "speakr/ui/native_interface_capabilities.json",
    }
    for key, label in labels.items():
        if key not in state.seen:
            state.add(f"required native UI resource is missing: {label}")


def scan_artifact(artifact: str | Path) -> list[str]:
    """Return artifact-relative policy violations found below *artifact*.

    An empty list means the unpacked release contains the required native UI
    resources and no detected embedded browser, Addons module, non-loopback
    app URL, updater, telemetry, or crash-report SDK.  This is a static release
    gate; runtime launch/readiness proof is intentionally separate.
    """

    try:
        root = Path(artifact).resolve()
    except (OSError, RuntimeError):
        return ["artifact path could not be resolved"]
    if not root.exists():
        return ["artifact does not exist"]
    if not root.is_dir():
        return ["artifact must be an unpacked Windows onedir or macOS .app directory"]

    state = _ScanState()
    for path in _walk_entries(root, state):
        relative = _relative_posix(path, root)
        for category in _name_findings(relative):
            state.add(f"forbidden {category} name: {relative}")

        if not _validate_symlink(path, root, relative, state):
            continue
        if not path.is_file():
            continue

        requirement = _requirement_key(relative)
        requirement_data = None
        if requirement is not None:
            requirement_data = _inspect_requirement(path, relative, requirement, state)

        if _is_app_owned_code(relative):
            data = requirement_data
            if data is None:
                data = _read_file(path, _MAX_TEXT_BYTES, relative, state)
            if data is not None:
                _inspect_app_text(data, relative, state)

        _inspect_archive_path(path, relative, state)
        _inspect_pyinstaller_executable(path, relative, state)
        try:
            binary_findings = _binary_marker_findings(_file_chunks(path))
        except OSError as exc:
            state.add(f"artifact binary could not be inspected ({type(exc).__name__}): {relative}")
        else:
            for category in binary_findings:
                state.add(f"forbidden {category} marker in artifact file: {relative}")

    _finalise_requirements(state)
    return sorted(set(state.violations))


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

    print("Speakr artifact privacy scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
