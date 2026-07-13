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
  It is replaced with a non-passed current-source report before the first gate.
- Numbered logs retain complete diagnostic stdout and stderr with only
  machine-local root paths redacted.
- `screenshots/manifest.json` records the OS, QPA, Qt version, requested
  renderer environment, effective renderer API observed after each capture,
  dimensions, SHA-256, source identity, and the explicit limits of what every
  PNG proves.
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
internal raw runtime stdout/stderr marker scan
internal source identity stability check
internal report/manifest identity validation
```

The committed-diff check uses `SPEAKR_VERIFY_BASE`, then the pull request's
`GITHUB_BASE_REF`, then `origin/main` when one of those bases resolves. If no
base is discoverable, the report labels the remaining command as a working-tree
fallback instead of claiming that committed changes were checked.

## Evidence freshness and source identity

Schema-3 reports and screenshot manifests bind evidence to the source that
actually produced it. Both contain the same path-safe identity:

- the full 40-character `HEAD` commit SHA;
- a SHA-256 working-tree fingerprint derived from the canonical staged and
  unstaged tracked diff plus relevant, non-ignored untracked source under
  `speakr/`, `tests/`, `scripts/`, and `assets/` (including QML and local UI
  assets);
- explicit clean/dirty state and counts for tracked changes and relevant
  untracked source.

The identity contains no repository path or source filename. Ignored build
output, virtual environments, caches, logs, runtime configuration, lock files,
personal dictionary data, learned words, and other private/runtime files do not
enter the fingerprint.

At aggregate startup, any prior green report is atomically replaced with
`initializing`, then a current-source `running` report. The screenshot manifest
is likewise marked current-source `pending`; standalone capture writes
`running` before Qt starts. Therefore interruption cannot leave an earlier
`passed` artifact looking current.

The screenshot subprocess recomputes identity after capture. The aggregate
recomputes identity after the command, warning-scan, and screenshot stages
complete. It then re-reads both persisted JSON documents and requires schema 3,
the expected
non-final/final status, and exact identity equality before changing the report
to `passed`. Missing identity, legacy schema-1/2 evidence, stale manifests,
mismatched fingerprints, or a source mutation during the run fail closed.

The runner sets the unit-test process to Qt offscreen/software mode and forces
Hugging Face and Transformers offline. The screenshot process keeps the host's
native QPA by default so platform typography and window geometry are visible,
while software Qt Quick rendering keeps repeated captures stable. PNGs do not
prove Mica, Vibrancy, an active operating-system High Contrast palette, focus
retention, or assistive-technology behavior; those remain explicit manual
platform gates. The divergent system-High-Contrast screenshot is explicitly
labelled as a deterministic palette fixture, not evidence that the OS setting
was active.

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

After every subprocess gate succeeds, the runner performs and records a second
aggregate scan over the original, unredacted in-memory unittest and screenshot
stdout/stderr. It rejects source-located QML diagnostics, ignored renderer
selection, scene-graph failures, and graphics/RHI initialization failures.
Raw machine paths are never persisted by that scan; only the separately
redacted numbered logs are written to disk.

## Screenshot capture

List or select scenarios without editing the script:

```powershell
python scripts/capture_ui_verification.py --list
python scripts/capture_ui_verification.py --scenario home-dark-full-960x700-100
```

The default set covers light and dark Home, Practice, Settings, Help,
Vocabulary, onboarding, Large HUD, concurrent HUD work, manual High Contrast,
a labelled divergent system-High-Contrast fixture, effect tiers, and
100/150/200% text. Every scenario disables motion so repeated captures on one
host are deterministic.

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
| QML health | Main and HUD render warning-free; every QML file independently compiles and is reachable from Main or HUD; raw runtime logs reject QML and renderer diagnostics. |
| Effects and contrast | Full/reduced/off, truthful effective software-renderer evidence, material failure, Reduce Transparency, light/dark contrast, manual High Contrast, and divergent system-palette canonical pairs. |
| Motion | Reduced-motion zero-duration tokens; no infinite, idle, or unconditional running animation mechanism. |
| Geometry | Every primary page at 960×700 and 640×520 with 100%, 150%, and 200% text; Large HUD at 150% and 200%. |
| Chrome | Logical hit regions, accessible 44 px controls, custom-chrome fallback, visible system frame, and Windows 10 scene glass. |
| Lifecycle | Close hides to a live tray; queued relaunch restores hidden and minimized windows. |
| HUD | Input-transparent/non-focusable flags, concurrency, stale-job safety, fail-closed focus guard, High Contrast, and software fallback. |
| Keyboard | Navigation order, page-title focus, visible focused controls, and untimed hotkey cancellation. Screen-reader heading navigation remains an open routed product finding below. |
| Privacy | Sanitized interface state, numeric-loopback-only behavior, hostile-markup isolation, no remote QML assets, an Essentials-only release boundary, and artifact privacy scans. |
| Evidence freshness | Full HEAD SHA, deterministic path-safe dirty-tree fingerprint, non-passed startup invalidation, schema-3 report/manifest equality, and end-of-run mutation detection. |

## Routed PR-12 product findings

These eleven findings are open product vetoes, not PR-11 harness defects and
not automated passes. PR-11 makes no production QML or behavior changes for
them; they are routed verbatim to their product owners for PR-12 integration:

1. **Shell/Home + HUD + browser recovery:** Toggle-mode Hold/release instructions are unsafe/contradictory across Home, HUD, browser — interaction truth.
2. **Settings + Onboarding + browser recovery:** Windows '+' hotkeys force Toggle while Settings/Onboarding show impossible Hold; capture promises combinations but captures one key — hotkey presentation.
3. **Browser recovery:** Browser shortcut capture falsely says 'no hidden background access' despite untimed global hook — privacy copy.
4. **Shell/Home:** Title-bar local privacy cue disappears below 720px/above 150% — low-vision/privacy.
5. **Browser recovery:** Browser privacy checkboxes are all labeled 'Enabled' and never show On/Off truth — browser a11y/privacy.
6. **Onboarding/Practice:** Practice idle shows Retry before an attempt and says Waiting for sound before listening — Practice truth.
7. **Onboarding/Practice:** Onboarding Practice has competing Start Practice + Finish setup primaries and duplicate Skip/Finish path — new/elderly hierarchy.
8. **Shared foundation accessibility:** SectionHeading titles are ignored/grouped, absent from screen-reader heading navigation — shared a11y.
9. **Shell/Home:** Home uses forbidden four-card summary and pushes status/privacy/latest outcome below default 960x700 fold — shell/Home hierarchy.
10. **Onboarding/Practice:** Future onboarding steps are disabled but announced as 'Return to…' — setup a11y.
11. **HUD:** HUD opt-in background announcements expose every pipeline stage instead of coalesced Listening / Processing locally / final — HUD a11y/privacy.

PR-12 implements resolutions for all eleven findings. Their owning contracts,
executable regression tests, repeated persona vote, and exact-source completion
rule are recorded in
[`luminous-orbit-consensus.md`](luminous-orbit-consensus.md). This historical
section remains the PR-11 routing record; it is not itself evidence that the
later fixes passed.

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
