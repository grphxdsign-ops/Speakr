# Luminous Orbit verification harness

PR-11 verifies the integrated native interface without using a single
cross-platform pixel-perfect golden. The harness combines focused behavioral
tests, runtime QML-warning rejection, static effect/privacy boundaries, and
platform-labelled screenshot artifacts.

## One-command audit

Run from the repository root with the active Python 3.11 environment:

```powershell
python scripts/verify_luminous_interface.py
```

The command fails at the first broken gate and writes evidence below
`build/ui-verification/`:

- `verification-report.json` records every command, the exact tests that
  satisfy each automated audit area, and a separate `manual_platform_status`
  that remains `required` after the automated run passes. Machine-local roots
  are represented as `<repo>`, `<output>`, and `<home>` in shareable evidence.
- Numbered logs retain complete diagnostic stdout and stderr with only
  machine-local root paths redacted.
- `screenshots/manifest.json` records the OS, QPA, Qt version, renderer,
  dimensions, SHA-256, and the explicit limits of what every PNG proves.
- Screenshot PNGs are platform review artifacts, not golden comparison files.

The audit runs, in order:

```text
python -m compileall -q speakr tests scripts
python -m unittest discover -s tests -v
python scripts/check_qt_build_environment.py
pyside6-qmllint -I speakr/ui/qml speakr/ui/qml/*.qml
git diff --check <merge-base>...HEAD
git diff --check
python scripts/capture_ui_verification.py
```

The committed-diff check uses `SPEAKR_VERIFY_BASE`, then the pull request's
`GITHUB_BASE_REF`, then `origin/main` when one of those bases resolves. If no
base is discoverable, the report labels the remaining command as a working-tree
fallback instead of claiming that committed changes were checked.

The runner sets the unit-test process to Qt offscreen/software mode and forces
Hugging Face and Transformers offline. The screenshot process keeps the host's
native QPA by default so platform typography and window geometry are visible,
while software Qt Quick rendering keeps repeated captures stable. PNGs do not
prove Mica, Vibrancy, an active operating-system High Contrast palette, focus
retention, or assistive-technology behavior; those remain explicit manual
platform gates.

## Runtime warning gate

A zero exit from either the unittest or screenshot process is not sufficient
evidence. The runner rejects every source-located
`.qml:<line>[:<column>]:` diagnostic in those runtime-process outputs, plus
unsourced binding-loop, missing-font/alias, and ignored scenegraph-backend
messages. This includes:

- QML `TypeError`, `ReferenceError`, `RangeError`, and runtime `Error` lines;
- binding loops;
- deprecated QML handler syntax;
- null-property access, failed assignment, and missing QML types;
- anchor, connection, nonexistent-property, and failed local-asset warnings;
- missing Qt font-family aliases and ignored renderer-backend selection.

This gate is separate from `qmllint`. Static lint findings remain in their own
log for review; runtime warnings during component creation, rendering, or
teardown make the aggregate audit fail.

## Screenshot capture

List or select scenarios without editing the script:

```powershell
python scripts/capture_ui_verification.py --list
python scripts/capture_ui_verification.py --scenario home-dark-full-960x700-100
```

The default set covers light and dark Home, Practice, Settings, Help,
Vocabulary, onboarding, Large HUD, concurrent HUD work, High Contrast, effect
tiers, and 100/150/200% text. Every scenario disables motion so repeated
captures on one host are deterministic.

For a deterministic hosted/offscreen artifact:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_BACKEND = "software"
python scripts/capture_ui_verification.py --output build/ui-verification/offscreen
```

For platform layout review, leave `QT_QPA_PLATFORM` unset. Run once on Windows
and once on macOS, preserving each output directory as a CI or PR artifact.
Review native material and focus behavior separately through the manual gates.

## Automated coverage

| Area | Automated proof |
|---|---|
| QML health | Main, HUD, and shared components load warning-free; every QML file is reachable from Main or HUD. |
| Effects and contrast | Full/reduced/off, software rendering, Reduce Transparency, light/dark composited contrast, and opaque High Contrast system-role mapping. |
| Motion | Reduced-motion zero-duration tokens; no infinite, idle, or unconditional running animation mechanism. |
| Geometry | Every primary page at 960×700 and 640×520 with 100%, 150%, and 200% text; Large HUD at 150% and 200%. |
| Chrome | Logical hit regions, accessible 44 px controls, custom-chrome fallback, visible system frame, and Windows 10 scene glass. |
| Lifecycle | Close hides to a live tray; queued relaunch restores hidden and minimized windows. |
| HUD | Input-transparent/non-focusable flags, concurrency, stale-job safety, fail-closed focus guard, High Contrast, and software fallback. |
| Keyboard | Navigation, heading focus, visible focused controls, and untimed hotkey cancellation. |
| Privacy | Sanitized interface state, loopback-only behavior, hostile-markup isolation, no remote QML assets, and artifact privacy scans. |

## Manual platform gates

The following require an interactive platform and are never inferred from an
offscreen or mocked pass:

- Windows `WM_NCHITTEST` with physical mixed-DPI coordinates;
- Windows 11 maximize-button Snap Layout hover and Win+Z;
- foreground window and caret identity while every HUD state appears;
- Windows High Contrast with NVDA;
- macOS Vibrancy/solid fallback, zoom/fullscreen, Reduce Transparency, and
  VoiceOver;
- native screenshots at the supported scale matrix.

The Windows foreground/caret probe may report `skipped` when an interactive
desktop cannot supply stable identities. The aggregate harness rejects that
skip on Windows, records the missing proof, and leaves the manual
focus-retention gate open.
