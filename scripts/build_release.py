#!/usr/bin/env python3
"""Build Speakr with one auditable PyInstaller contract on every platform.

The release workflow and ``package_mac.sh`` both call this module.  Keeping
the argument list here prevents the two distributable artifacts from quietly
drifting apart.  It intentionally does not exclude QtNetwork: Qt Essentials
may load that library transitively even though Speakr adds no Qt networking.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_QT_MODULES = (
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebView",
    "PySide6.QtWebChannel",
    # Concrete module families installed by the PySide6-Addons distribution.
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQuick3D",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSpatialAudio",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebSockets",
)


def pyinstaller_arguments(icon: Path | None = None) -> list[str]:
    """Return the complete PyInstaller arguments for the host platform."""

    data_separator = os.pathsep
    arguments = [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Speakr",
        "--paths",
        str(ROOT),
        "--collect-all",
        "ctranslate2",
        "--collect-all",
        "faster_whisper",
        "--collect-all",
        "onnxruntime",
        "--hidden-import",
        "PySide6.QtQuick",
        "--hidden-import",
        "PySide6.QtQuickControls2",
        "--add-data",
        f"{ROOT / 'speakr' / 'ui' / 'qml'}{data_separator}speakr/ui/qml",
        "--add-data",
        f"{ROOT / 'assets' / 'icon.png'}{data_separator}assets",
        "--add-data",
        (
            f"{ROOT / 'speakr' / 'ui' / 'native_interface_capabilities.json'}"
            f"{data_separator}speakr/ui"
        ),
    ]

    if sys.platform == "darwin":
        arguments.extend(
            [
                "--osx-bundle-identifier",
                "com.speakr.dictation",
                "--hidden-import",
                "pystray._darwin",
            ]
        )
    elif sys.platform == "win32":
        arguments.extend(
            [
                "--hidden-import",
                "pystray._win32",
                "--hidden-import",
                "comtypes.stream",
            ]
        )
    else:
        raise RuntimeError(f"release builds are unsupported on {sys.platform!r}")

    if icon is not None:
        arguments.extend(["--icon", str(icon.resolve())])

    for module in FORBIDDEN_QT_MODULES:
        arguments.extend(["--exclude-module", module])

    arguments.append(str(ROOT / "scripts" / "frozen_entry.py"))
    return arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icon", type=Path, help="platform icon produced by the caller")
    parser.add_argument(
        "--print-args",
        action="store_true",
        help="print one shell-quoted argument per line without building",
    )
    args = parser.parse_args(argv)

    if sys.version_info[:2] != (3, 11):
        raise SystemExit(
            "release builds require Python 3.11; found "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )

    arguments = pyinstaller_arguments(args.icon)
    if args.print_args:
        for argument in arguments:
            print(repr(argument))
        return 0

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", *arguments],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
