# Quiet Signal implementation audit

This audit was repeated after the controller, QML, responsive-layout, motion,
privacy, and packaging passes. “Pass” means the implementation presents no
remaining material persona veto; it does not replace hands-on release testing
with the named assistive technologies and signed artifacts.

## Pass 1 — structure and comprehension

| Persona | Evidence | Decision |
|---|---|---|
| New user | Five plain-language setup frames, optional Practice and Skip, Home recovery actions, no JSON or tray requirement | Pass |
| Expert user | Tray-first preference, keyboard page shortcuts, searchable categorized settings, confirmed model/device changes, exact Advanced values | Pass |
| Variable or unclear speech | Hold or Toggle, coarse Low/Good/High mic feedback, model/language/vocabulary controls, no speech grading | Pass |
| Low-vision user | System/high-contrast colors, 44 px targets, 2 px focus, 100–200% text, independently scalable Large HUD | Pass |
| Elderly user | No timed setup or shortcut capture, literal labels, persistent recovery, guarded deletion, one primary next action | Pass |

## Pass 2 — truthful state and privacy

| Question | Resolution |
|---|---|
| Can a stale completion hide a newer recording? | No. Capture and pipeline have independent job IDs; settle timers verify the current job and inactive capture. |
| Can Practice leak into normal dictation? | No. It has a separate in-memory result, disables transcript logging, never injects, learns, updates recent cleanup context, or touches the clipboard, and clears on every exit path. |
| Can the HUD steal the caret? | The HUD is input-transparent and non-activating. A runtime focus guard hides it for the session and keeps tray feedback if focus retention fails. |
| Does Dictation off match microphone behavior? | Yes. The microphone stream closes and rolling RAM audio is cleared. |
| Can dictated text leave the machine through a configured cleanup URL? | No. Ollama URLs are canonicalized to numeric loopback; remote addresses are rejected and basic cleanup remains available. |
| Does interface state contain private working content? | No. The state store rejects unknown fields and exposes no audio, transcript, selection, clipboard, screen text, or window title. |

All five personas retain their Pass decision after the privacy and state audit.

## Pass 3 — rendered and automated checks

- Main and HUD QML load without warnings using the packaged Basic control style.
- The minimum 640 × 520 window retains all five labeled navigation items at
  200% text scale, wrapping to two columns and three rows.
- Light and dark token tests enforce 7:1 primary text, 4.5:1 secondary and
  semantic text, and 3:1 meaningful borders.
- Reduced Motion zeros transition durations while success/error reading time
  remains unchanged.
- Security tests reject unauthenticated fallback reads and mutations, invalid
  Host/Origin values, remote UI resources, and embedded browser engines.
- An outbound-socket test permits loopback only when the model is preseeded and
  Ollama is disabled.

## Pass 4 — repeated disagreement resolution

The review was deliberately reopened whenever one reviewer found a material
conflict. The implementation was not accepted while any veto remained.

| Review round | Material disagreement | Resolution |
|---|---|---|
| 1 | A failed config save could leave memory and disk disagreeing; Practice could survive navigation; setup could advance before the local model was ready | Atomic rollback, complete Practice exit clearing, and model-readiness gates |
| 2 | Device/compute labels could describe requested rather than active values; stale dictionary row IDs could remove the wrong edited line | Active-versus-pending summaries, actual runtime compute state, and content-bound dictionary IDs |
| 3 | Generic retry could call the wrong subsystem; restart notices and Ollama availability could become stale | Exact recovery-action routing, selectively persistent issues, and live local-Ollama reachability updates |
| 4 | An older completion could clear a newer microphone failure; cleanup-path language mixed availability with last use | Selective issue resolution and one consistent availability meaning for cleanup state |
| 5 | Runtime pipeline errors could replace a newer capture; Vocabulary failures lacked useful inline recovery | Nonblocking job errors, capture-first priority, busy mutation guards, and inline recovery |
| 6 | Runtime mic failure could focus Main; error HUDs could remain forever; failed Vocabulary/Practice submissions lost input; successful mic retry left a stale reconnect warning | Hidden windows no longer auto-open from state errors; five-second error HUD settle with persistent Home/tray recovery; boolean bridge results with clear-on-success fields; both mic issues clear after a successful normal open |
| 7 | Snapshot-then-clear timers still had a narrow race | Atomic, lock-protected, generation-guarded capture and pipeline retirement |
| 8 | The source-oriented macOS bundle installed packages from PyPI on first launch, and the artifact scan could miss concrete Addons modules | `package_mac.sh` now produces a self-contained Python 3.11 PyInstaller app with no runtime package install; release builds reject an installed Addons distribution and scan real module/library families such as QtCharts |
| 9 | A stale pre-QML Windows installation could own the single-instance mutex with no window; a rapid duplicate during native startup could also lose its wake request | Replaced the installed legacy payload without touching user data, verified the native window and Qt modules, and moved stale wake-file cleanup ahead of UI startup so fresh duplicate requests survive |

The ninth-pass live-filesystem audit found no remaining material veto.
New, expert, variable/unclear-speech, low-vision, and elderly personas all
returned **Pass**. The full automated suite reports **57/57 passing tests**.

## Pass 5 — current Windows artifact

- The exact PyInstaller onedir shape used by the Windows release workflow was
  rebuilt from the audited files.
- The artifact scanner found the required local QML and icon, no WebView2,
  QtWebEngine, QtWebView/WebChannel, Chromium, concrete PySide6 Addons module,
  or remote UI resource reference.
- With Hugging Face offline mode enabled, the frozen executable remained
  alive in native QML for seven seconds and did not create the browser
  fallback marker or log a native-interface fallback.

The five-persona implementation consensus is unanimous after these passes.

## Release-only verification still required

Before distribution, run the platform matrix in the design plan on real
Windows and macOS hardware: NVDA/VoiceOver, OS contrast and motion settings,
mixed DPI, RDP/software rendering, permission repair, caret retention, and the
final signed/notarized artifacts. The exact Windows onedir native-QML build and
privacy scan have passed locally; macOS signing/notarization requires a macOS
runner.
