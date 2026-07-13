# Luminous Orbit integration and persona consensus

Status: PASS. Product fixes, independent review, the clean committed-source
aggregate, and required Windows/macOS hosted checks are complete. The
explicitly interactive platform and signed-artifact evidence remains a PR-13
release gate and is never inferred from offscreen output.

This record is the controller-owned audit for the complete interface. It does
not treat an isolated screenshot, mocked native call, or one persona's
preference as product approval. A material veto reopens the interface for all
five personas and requires the complete audit to run again.

## Audit round 1: structure and truthful interaction

The PR-11 verification lane routed eleven material product vetoes into PR-12.
Each is resolved at the owning contract rather than hidden by different copy
on one screen.

| ID | Veto | Resolution | Executable proof |
|---:|---|---|---|
| 1 | Hold/release copy appeared while effective behavior was Toggle. | All native and recovery surfaces resolve the effective mode. Home changes its instruction while recording; HUD keeps concurrent-job copy on its reserved second line. | Home mode table, HUD state table, browser source tests. |
| 2 | Windows key combinations forced Toggle while setup exposed an impossible Hold choice; capture promised combinations but records one key. | A pure helper derives `effective_toggle_mode` and `toggle_mode_forced` in settings presentation only. Forced controls show Press mode, are disabled with an explanation, and never rewrite the stored preference. Capture consistently says one key, untimed, Cancel or Escape. | `test_hotkey_presentation`, Settings, onboarding, and listener-parity tests. |
| 3 | Browser recovery claimed shortcut capture had no hidden background access. | Recovery copy says the native listener waits system-wide and the browser page never receives the key. | Browser markup contract test. |
| 4 | The title-bar privacy cue disappeared at narrow width or large text. | The cue is always present: full copy when space permits and `Local only` visually when compact, while its accessible name remains `Everything stays on this device`. | 640 by 520 at 200% geometry and native-Windows non-overlap tests. |
| 5 | Recovery privacy switches all read `Enabled` and did not expose their current truth. | Each switch has its own label and description association plus a visible `On` or `Off` value updated from settings and restored after rejection. | Browser accessibility and rendering-source tests. |
| 6 | Practice offered Retry before any attempt and reported waiting for sound while idle. | Initial, listening, processing, result, and recoverable-message states have an explicit action/meter table. The five-segment meter is absent outside active capture; only listening can expose it, fill it, or report Low/Good/High. | Onboarding and standalone Practice state-table tests. |
| 7 | Onboarding Practice offered competing primary completion paths. | Initial Practice has Start plus secondary Skip; active capture has Stop; processing has no enabled primary; an outcome has secondary Try again plus primary Finish. | One-primary-action and Skip-to-Finish tests. |
| 8 | Shared section titles were grouped text rather than screen-reader headings. | `SectionHeading` itself owns the Heading role/name/description; its visible text children are ignored to avoid duplicate nodes. | Shared-component accessibility test. |
| 9 | Four equal Home summary cards obscured hierarchy and pushed Latest outcome below the default fold. | Home now has one readiness surface and one flat five-row status surface. Latest outcome is the fifth row and is inside the initial 960 by 700 viewport. | Home structure, accessibility, and default-fold geometry tests. |
| 10 | Disabled future onboarding steps announced that users could return to them. | Steps announce Completed/Current/Upcoming explicitly; only completed and current steps are enabled. | Five-step accessibility table test. |
| 11 | QML live regions and Python emitted duplicate, over-detailed HUD announcements. | The HUD QML subtree is ignored. One opt-in bridge channel emits at most Listening, one Processing locally per job, and the final result. Capture suppresses an older processing job, and retiring an attempt cannot replay its result. | QAccessible tree and job-keyed announcement tests. |

Structural checks also reject local page colors, one-off glass, nested glass,
idle animation, clipped focus, unlabeled controls, QML warnings, horizontal
page scrolling, and transcript content in runtime state.

The first low-vision rerun found one additional material veto beyond the
eleven routed findings: Large HUD error copy was elided at 200% text. The
resolution wraps both reserved lines, uses concise mode-truthful generic error
copy, and omits the nonessential processing rail for warning/error outcomes.
Standard listening copy was shortened without changing meaning so its rail
also remains inside the 96 px capsule. Geometry tests exercise every outcome
on a 640 by 520 monitor at 150% and 200%; any truncation or out-of-bounds label
is now a failure. Because this was material, all five persona votes were reset.

## Audit round 2: cross-platform and fallback behavior

This round combines real-host evidence with explicit capability limits. It
never upgrades offscreen evidence into a native-compositor claim.

| Environment | Required result | Evidence status |
|---|---|---|
| Windows native QPA | Main window visible; custom chrome, resize, work area, system menu, Snap region, title cue, 100/150/200% layout, and HUD focus gate. | Required hosted and native-QPA checks pass; physical Snap/NVDA evidence remains interactive-only. |
| Windows High Contrast | Opaque canonical system roles, visible focus, meaningful borders, and shape-redundant state. | Pending final manual/automated evidence review. |
| Older Windows / unavailable DWM backdrop | `scene_glass`, or `solid` after graphics failure, without blocking the window. | Focused fallback tests and final aggregate pass. |
| RDP / forced software renderer | Renderer is proven before QML; one guarded fresh-process handoff or visible recovery; never two trays or two cores. | Focused renderer/handoff tests and final aggregate pass. |
| macOS hosted tests | Cocoa lifecycle, full-size content, custom action routing, fallback, QML, and unit suite. | Current required hosted check passes. |
| macOS interactive compositor | Vibrancy/solid fallback, Reduce Transparency, VoiceOver, zoom/fullscreen, and HUD focus identity. | Must be attached as platform evidence; never inferred from Windows or offscreen output. |
| Browser recovery | Numeric loopback only, token-authenticated mutation, hostile Host/Origin rejection, CSP, no-store, no remote asset, and temporary Practice exclusion. | Live, focused security, and final aggregate tests pass. |

## Audit round 3: five-persona vote

The complete current product passed an independent five-persona rerun after
the last material fix. A later product change invalidates every vote below.

| Persona | Acceptance question | Vote |
|---|---|---|
| New user | Can setup, recover, optionally Practice, and reach Home without tray knowledge, jargon, or competing primary actions? | PASS |
| Expert user | Can work tray-first, navigate by keyboard, search Advanced, inspect exact hardware/material truth, and tune HUD/effects without losing familiar window behavior? | PASS |
| Variable or unclear speech | Are mic feedback, language/model controls, and vocabulary correction neutral and useful without clarity grades or blame? | PASS |
| Low-vision user | Are High Contrast, 44 px targets, visible focus, heading navigation, 200% reflow, persistent privacy, and Large HUD complete? | PASS |
| Elderly user | Is every step untimed, recovery persistent, deletion guarded, copy familiar, and each view organized around one dominant action? | PASS |

The privacy reviewer must separately confirm that compositor pixels never
enter Python/QML state and no user-derived data leaves the machine. The
feasibility reviewer must confirm that unsupported material and custom-chrome
failure still yield a visible, system-framed window. Neither review may be
substituted by a persona vote.

Both independent reviews record PASS. The exact committed-source automated
run completed 240 tests with one expected host-specific skip, then passed
compileall, the Qt Essentials boundary, qmllint, committed and working-tree
diff checks, 11 platform-labelled screenshots, raw runtime-warning scanning,
schema-3 evidence identity validation, and source-identity stability. The
generated report and screenshot manifest both bind to the same clean HEAD.

## Completion rule

Change this document to `PASS` only after all of the following are bound to
the exact clean PR-12 commit:

1. compileall, the full unittest suite, Qt dependency boundary, qmllint, and
   both diff checks pass;
2. the schema-3 verification report and screenshot manifest match the exact
   source identity and report every automated gate passed;
3. Windows and macOS required checks pass, with interactive-only limits
   recorded honestly;
4. privacy and feasibility reviews record no material veto; and
5. all five persona votes read `PASS` after the last material fix.

All five conditions are satisfied for PR-12. Interactive compositor,
assistive-technology, signing, notarization, and installed-artifact proof
remain explicit PR-13 gates.
