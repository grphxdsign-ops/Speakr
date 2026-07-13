#!/usr/bin/env python3
"""Capture deterministic, platform-labelled Luminous Orbit UI evidence.

The PNGs produced here are review artifacts, not pixel-perfect golden files.
Every scenario disables motion so repeated captures on the same host are
stable, while the manifest records the platform and rendering backend that
produced them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_QPA_WAS_EXPLICIT = "QT_QPA_PLATFORM" in os.environ
_REQUESTED_QPA = os.environ.get("QT_QPA_PLATFORM")

# Keep the native QPA by default so Windows/macOS captures include their real
# platform typography and window geometry. Software Qt Quick rendering makes
# repeated layout captures stable; native compositor material remains a
# separate manual platform gate and is never inferred from these PNGs.
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QSG_RHI_BACKEND", "software")
os.environ.setdefault("SPEAKR_QT_SOFTWARE", "1")

ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "speakr" / "ui" / "qml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QMetaObject, QObject, QUrl, qVersion  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from speakr.qt_ui import Bridge  # noqa: E402
from tests.qml_lifecycle import dispose_qml_fixture  # noqa: E402
from tests.test_hud_qml import _NativeWindow  # noqa: E402
from tests.test_qml_load import _App  # noqa: E402
from tests.test_shell_home import _WindowController  # noqa: E402

# Test fixtures default themselves to offscreen at import time. Preserve the
# caller's actual QPA request so a native screenshot run remains native; unit
# tests that explicitly requested offscreen keep that deterministic backend.
if _QPA_WAS_EXPLICIT:
    os.environ["QT_QPA_PLATFORM"] = _REQUESTED_QPA or ""
else:
    os.environ.pop("QT_QPA_PLATFORM", None)


@dataclass(frozen=True)
class Scenario:
    name: str
    surface: str
    width: int
    height: int
    text_scale: int
    theme: str
    visual_effects: str
    page: str = "home"
    onboarding: bool = False
    hud_size: str = "standard"
    hud_state: str = ""


SCENARIOS = (
    Scenario(
        "home-light-full-960x700-100",
        "main",
        960,
        700,
        100,
        "light",
        "full",
    ),
    Scenario(
        "home-dark-full-960x700-100",
        "main",
        960,
        700,
        100,
        "dark",
        "full",
    ),
    Scenario(
        "practice-dark-reduced-960x700-100",
        "main",
        960,
        700,
        100,
        "dark",
        "reduced",
        page="practice",
    ),
    Scenario(
        "settings-dark-reduced-640x520-150",
        "main",
        640,
        520,
        150,
        "dark",
        "reduced",
        page="settings",
    ),
    Scenario(
        "help-light-off-640x520-200",
        "main",
        640,
        520,
        200,
        "light",
        "off",
        page="help",
    ),
    Scenario(
        "vocabulary-high-contrast-640x520-200",
        "main",
        640,
        520,
        200,
        "high_contrast",
        "off",
        page="vocabulary",
    ),
    Scenario(
        "onboarding-light-reduced-640x520-200",
        "main",
        640,
        520,
        200,
        "light",
        "reduced",
        onboarding=True,
    ),
    Scenario(
        "hud-listening-dark-large-150",
        "hud",
        0,
        0,
        150,
        "dark",
        "reduced",
        hud_size="large",
        hud_state="listening",
    ),
    Scenario(
        "hud-concurrent-dark-large-150",
        "hud",
        0,
        0,
        150,
        "dark",
        "reduced",
        hud_size="large",
        hud_state="concurrent",
    ),
    Scenario(
        "hud-error-high-contrast-large-200",
        "hud",
        0,
        0,
        200,
        "high_contrast",
        "off",
        hud_size="large",
        hud_state="error",
    ),
)
SCENARIO_BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}


class _ArtifactApp(_App):
    def __init__(self, scenario: Scenario):
        super().__init__(text_scale=scenario.text_scale)
        self._scenario = scenario

    def settings_snapshot(self):
        settings = super().settings_snapshot()
        settings["ui"].update(
            {
                "onboarding_complete": not self._scenario.onboarding,
                "theme": self._scenario.theme,
                "visual_effects": self._scenario.visual_effects,
                "text_scale": self._scenario.text_scale,
                "motion": "reduced",
                "reduced_motion": "reduce",
                "hud_visibility": "while_dictating",
                "hud_size": self._scenario.hud_size,
                "hud_scale": self._scenario.text_scale,
            }
        )
        return settings


def _application() -> QApplication:
    if QQuickStyle.name() != "Basic":
        QQuickStyle.setStyle("Basic")
    return QApplication.instance() or QApplication([])


def _pump(application: QApplication, count: int = 8) -> None:
    for _ in range(count):
        application.processEvents()


def _close(
    application: QApplication,
    bridge: Bridge,
    engine: QQmlApplicationEngine,
    native_window: QObject,
) -> None:
    dispose_qml_fixture(
        application,
        engine,
        context_objects=(bridge, native_window),
    )


def _save_window(window: QObject, destination: Path) -> tuple[int, int]:
    image = window.grabWindow()
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise RuntimeError(f"Qt returned an empty image for {destination.stem}")
    if not image.save(str(destination), "PNG"):
        raise RuntimeError(f"Qt could not save {destination}")
    return image.width(), image.height()


def _capture_main(
    application: QApplication,
    scenario: Scenario,
    destination: Path,
) -> tuple[int, int, list[str]]:
    app = _ArtifactApp(scenario)
    bridge = Bridge(app)
    native_window = _WindowController()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("nativeWindow", native_window)
    warnings: list[str] = []
    engine.warnings.connect(
        lambda values: warnings.extend(error.toString() for error in values)
    )
    captured: tuple[int, int] | None = None
    try:
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        _pump(application)
        if len(engine.rootObjects()) != 1 or warnings:
            raise RuntimeError(
                "Main.qml did not load cleanly: " + "; ".join(warnings)
            )
        window = engine.rootObjects()[0]
        window.setWidth(scenario.width)
        window.setHeight(scenario.height)
        if not scenario.onboarding:
            window.setProperty("currentPage", scenario.page)
            QMetaObject.invokeMethod(window, "focusCurrentPage")
        window.show()
        _pump(application, 12)
        captured = _save_window(window, destination)
    finally:
        _close(application, bridge, engine, native_window)
    if warnings:
        raise RuntimeError(
            "Main.qml emitted warnings during rendering or teardown: "
            + "; ".join(warnings)
        )
    if captured is None:
        raise RuntimeError(f"Main.qml did not capture {scenario.name}")
    return (*captured, warnings)


def _set_hud_state(app: _ArtifactApp, state: str) -> None:
    common = {
        "active_monitor_x": 0,
        "active_monitor_y": 0,
        "active_monitor_width": 960,
        "active_monitor_height": 700,
    }
    if state == "listening":
        app.interface_state.update(
            **common,
            capture="listening",
            capture_job_id=11,
            mic_level_band="good",
        )
    elif state == "concurrent":
        app.interface_state.update(
            **common,
            pipeline="formatting",
            pipeline_job_id=21,
            status_code="formatting",
        )
        app.interface_state.update(
            capture="listening",
            capture_job_id=22,
            mic_level_band="low",
        )
    elif state == "error":
        app.interface_state.update(
            **common,
            pipeline="error",
            pipeline_job_id=31,
            status_code="pipeline_error",
        )
    else:
        raise ValueError(f"unsupported HUD state: {state}")


def _capture_hud(
    application: QApplication,
    scenario: Scenario,
    destination: Path,
) -> tuple[int, int, list[str]]:
    app = _ArtifactApp(scenario)
    bridge = Bridge(app)
    native_window = _NativeWindow()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("nativeWindow", native_window)
    warnings: list[str] = []
    engine.warnings.connect(
        lambda values: warnings.extend(error.toString() for error in values)
    )
    captured: tuple[int, int] | None = None
    try:
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Hud.qml")))
        _pump(application)
        if len(engine.rootObjects()) != 1 or warnings:
            raise RuntimeError(
                "Hud.qml did not load cleanly: " + "; ".join(warnings)
            )
        window = engine.rootObjects()[0]
        _set_hud_state(app, scenario.hud_state)
        _pump(application, 12)
        if not bool(window.property("shouldShow")):
            raise RuntimeError(f"HUD scenario did not become visible: {scenario.name}")
        captured = _save_window(window, destination)
    finally:
        _close(application, bridge, engine, native_window)
    if warnings:
        raise RuntimeError(
            "Hud.qml emitted warnings during rendering or teardown: "
            + "; ".join(warnings)
        )
    if captured is None:
        raise RuntimeError(f"Hud.qml did not capture {scenario.name}")
    return (*captured, warnings)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _clear_managed_artifacts(output: Path) -> None:
    """Remove only files this tool owns before starting a fresh capture."""

    manifest_path = output / "manifest.json"
    managed = {output / f"{scenario.name}.png" for scenario in SCENARIOS}
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
        previous = {}
    if isinstance(previous, dict) and previous.get("schema_version") == 1:
        artifacts = previous.get("scenarios", [])
        if not isinstance(artifacts, list):
            artifacts = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            name = artifact.get("name")
            filename = artifact.get("file")
            if not isinstance(name, str) or not isinstance(filename, str):
                continue
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
                continue
            if filename != f"{name}.png":
                continue
            managed.add(output / filename)

    manifest_path.unlink(missing_ok=True)
    for destination in managed:
        if destination.parent != output or destination.suffix.casefold() != ".png":
            continue
        destination.unlink(missing_ok=True)


def capture_scenarios(
    output: Path,
    names: Iterable[str] | None = None,
) -> dict[str, object]:
    requested = list(names) if names is not None else [item.name for item in SCENARIOS]
    unknown = sorted(set(requested) - set(SCENARIO_BY_NAME))
    if unknown:
        raise ValueError("unknown scenarios: " + ", ".join(unknown))
    if len(set(requested)) != len(requested):
        raise ValueError("scenario names must be unique")

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _clear_managed_artifacts(output)
    application = _application()
    artifacts = []
    for name in requested:
        scenario = SCENARIO_BY_NAME[name]
        destination = output / f"{scenario.name}.png"
        if scenario.surface == "main":
            width, height, warnings = _capture_main(
                application, scenario, destination
            )
        else:
            width, height, warnings = _capture_hud(
                application, scenario, destination
            )
        artifacts.append(
            {
                "name": scenario.name,
                "surface": scenario.surface,
                "file": destination.name,
                "width": width,
                "height": height,
                "text_scale": scenario.text_scale,
                "theme": scenario.theme,
                "visual_effects": scenario.visual_effects,
                "qml_warnings": warnings,
                "sha256": _sha256(destination),
            }
        )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "purpose": "platform layout evidence; not a pixel-perfect golden",
        "capture_scope": {
            "proves": (
                "QML layout, platform typography, and labelled renderer output"
            ),
            "does_not_prove": (
                "native Mica/Vibrancy, an active OS High Contrast palette, "
                "focus retention, or accessibility technology behavior"
            ),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "qt": qVersion(),
            "qpa": application.platformName(),
            "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", ""),
            "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", ""),
        },
        "scenarios": artifacts,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "ui-verification" / "screenshots",
        help="directory for PNGs and manifest.json",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=tuple(SCENARIO_BY_NAME),
        help="capture only this scenario; repeat for more than one",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list scenario names without starting Qt",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(argv)
    if arguments.list:
        for scenario in SCENARIOS:
            print(scenario.name)
        return 0
    manifest = capture_scenarios(arguments.output, arguments.scenario)
    print(
        f"Captured {len(manifest['scenarios'])} UI scenarios in "
        f"{Path(arguments.output).resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
