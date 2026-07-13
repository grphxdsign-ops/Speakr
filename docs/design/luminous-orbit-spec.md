# Luminous Orbit interface specification

Status: design contract for implementation and review.

This document translates the Luminous Orbit direction into screen,
component, native-window, effects, responsive, and acceptance requirements.
It supersedes Quiet Signal's visual anti-glass doctrine only. Speakr's
local-only privacy boundary, truthful interface state, focus retention,
Practice isolation, keyboard access, assistive-technology support, and
pipeline behavior remain unchanged.

## Experience model

The physical scene is a person glancing at Speakr while working in another
application. The interface can feel like an orbital observatory, but the user
must identify readiness, recording, processing, success, and recovery in one
glance. Atmosphere establishes place; icon, text, shape, and position convey
meaning.

Dark mode uses a deep ink canvas with violet, cyan, and blush light caught in
rounded material. Light mode uses cool lunar mist with the same hierarchy and
less saturated atmosphere. Neither mode imitates a science-fiction control
panel.

## Non-negotiable boundaries

- Audio, transcript text, selected text, screen content, clipboard content,
  foreground-window titles, and learned vocabulary never enter visual-effects
  or native-window state.
- No remote font, image, shader, script, help link, CDN, WebEngine, WebView2,
  telemetry, analytics, crash upload, or update request.
- No visual implementation may change transcription, formatting, injection,
  microphone, hotkey, dictionary, learning, or Practice-isolation semantics.
- The main window must appear with a normal system frame if native custom
  chrome cannot initialize.
- HUD focus and caret safety outrank material fidelity.
- High Contrast, Increased Contrast, Reduce Transparency, Reduce Motion, RDP,
  and software rendering are complete product modes, not degraded test cases.

## Token contract

### Color

| Token | Light | Dark | Use |
|---|---|---|---|
| `canvas` | `#EDF1FA` | `#090B18` | Window and fallback backdrop |
| `surfaceStrong` | `#F8FAFF` | `#20243A` | Opaque and near-opaque content |
| `textPrimary` | `#17182A` | `#F2F3FC` | Headings, labels, body |
| `textSecondary` | `#55596D` | `#B4B7C9` | Supporting copy |
| `borderMeaningful` | `#747A92` | `#737A99` | Controls and material boundaries |
| `accent` | `#6657D8` | `#A89AFB` | Primary action, selection, focus |

Atmospheric violet, cyan, and blush are decorative and remain below 18%
opacity over the canvas. They do not sit directly behind body text unless a
92--96% content well intervenes. High Contrast removes them.

Semantic colors must pass the final composited contrast checks and always pair
with a distinct icon, label, and shape. The system palette owns semantic and
focus colors in High Contrast or Increased Contrast.

### Material

| Layer | Full | Reduced | Off |
|---|---|---|---|
| Shell | Native material plus 72% dark / 78% light veil | 94% local surface | Solid canvas |
| Navigation | 76% dark / 82% light | 96% local surface | Strong surface |
| Major panel | 84% dark / 88% light | 96% local surface | Strong surface |
| Context notice | 88% dark / 92% light | 96% local surface | Strong surface |
| Text content | 94% dark / 96% light | Opaque | Opaque |
| HUD | At least 96%; local only | Opaque | Opaque |

Each material edge uses one meaningful 1 px boundary and, outside High
Contrast, at most one restrained shadow. Never stack two blurred or
translucent surfaces. Never place a focus ring beneath a translucent layer.

### Type, spacing, and shape

| Role | Contract |
|---|---|
| Page heading | 28 px system UI, semibold |
| Section heading | 22 px system UI, semibold |
| Status heading | 18 px system UI, semibold |
| Body and controls | 16 px system UI |
| Secondary | 15 px system UI |
| Spacing | 4, 8, 12, 16, 24, 32 logical px |
| Control radius | 14 logical px |
| Major-panel radius | 20 logical px |
| Shell radius | 28 logical px |
| Minimum target | 44 by 44 logical px |
| Focus | 2 px outline plus 2 px clearance |

Pills are limited to short statuses and metadata. Buttons, inputs, settings,
and navigation retain readable labels and do not become capsules by default.

## Effects resolution

Persist:

```text
ui.visual_effects: system | full | reduced | off
```

Default: `system`.

Resolve in this order:

1. High Contrast or Increased Contrast: `off`, `solid`.
2. OS Reduce Transparency: `reduced`.
3. RDP, virtualized display, forced software renderer, or graphics failure:
   `reduced`.
4. Explicit `off` or `reduced`: honor the explicit value.
5. Explicit `full` or eligible `system`: use `full`.
6. No native material under `full`: use `scene_glass`.
7. Scene-graph effect failure: use `solid` without delaying launch.

The effective material is exactly one of `mica`, `vibrancy`, `scene_glass`,
or `solid`. Settings may expose this resolved value as read-only expert
information. It is not a readiness or error state.

### Windows material and chrome

- Windows 11 build 22621 or newer requests the DWM main-window backdrop type.
- Unsupported Windows or a failed DWM call uses `scene_glass`.
- The custom frame retains DWM corners and shadow.
- Native hit testing owns the caption, eight resize regions, and system menu.
- The maximize region returns `HTMAXBUTTON` so Windows 11 Snap Layouts and
  Win+Z remain available.
- Maximization uses the active monitor's work area and responds to mixed-DPI
  changes.
- Alt+Space opens the system menu. Double-clicking the drag region toggles
  maximize or restore.

### macOS material and chrome

- The AppKit window retains titled, closable, miniaturizable, and resizable
  style masks.
- Full-size content and a transparent title-bar appearance place QML behind
  the title region; the standard controls are visually hidden.
- An `NSVisualEffectView` sits behind, not above, the main QML scene.
- Custom QML controls dispatch to native close, miniaturize, zoom, and
  fullscreen behavior.
- Reduce Transparency removes vibrancy immediately and selects an opaque local
  surface.
- The compositor's sampled pixels never become application data.

### Shared chrome behavior

- Custom chrome applies only to the main window.
- Minimize, Maximize or Restore, and Close have accessible roles and dynamic
  accessible names.
- Each control has a 44 px hit target even if its visible glyph is smaller.
- The drag region never overlaps a control or the active page.
- Native system move and resize operations are used; QML does not implement a
  manual geometry loop.
- Close hides to tray. Explicit Quit remains separate.
- If native setup fails before show, restore the normal system frame and then
  show the window. A failed effect cannot create an invisible process.

Official platform references:

- [Windows system backdrops](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type)
- [Windows Snap Layout integration](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/ui/apply-snap-layout-menu)
- [Qt system move and resize](https://doc.qt.io/qt-6/qwindow.html)
- [AppKit visual effect view](https://developer.apple.com/documentation/appkit/nsvisualeffectview)
- [AppKit full-size content](https://developer.apple.com/documentation/appkit/nswindow/stylemask-swift.struct/fullsizecontentview)

These links are design and implementation references only. They are not
loaded by the shipped interface. Platform capability assumptions were
reviewed against these references on 2026-07-12; runtime feature detection
and the visible system-frame fallback remain authoritative if platform
behavior changes.

## Responsive composition

### Wide: 860 logical px and above

- Custom title bar spans the shell.
- Labeled navigation occupies the left column.
- The page occupies the remaining width with one dominant state or task.
- Home may place status details beside the primary readiness surface when
  text scale and width permit.

### Narrow: below 860 logical px

- Navigation moves above content without becoming icon-only.
- Page content becomes a single reading column.
- Secondary actions wrap below the primary action.
- Horizontal scrolling is prohibited for page-level content.

### Minimum: 640 by 520 at 200% text

- Five navigation labels remain visible in a two-column, three-row grid.
- Controls grow vertically rather than clipping labels.
- Content scrolls within the page, not under the title bar or navigation.
- Dialog-like confirmations remain inside the visible work area.
- Focus rings and rounded shadows are not clipped.

The default window remains 960 by 700 logical pixels. Content reflows before
truncation; primary instructions, state labels, privacy copy, and recovery
actions are never elided.

## Shared component contract

| Component | Required behavior |
|---|---|
| `CosmicBackdrop` | Static local fields and orbital curves; absent in High Contrast; no idle animation |
| `GlassSurface` | Resolves full/reduced/off appearance; one edge; no nested glass |
| `StatusOrb` | Icon, text, shape, and state color; never color alone |
| `SectionHeading` | Heading, optional description, at most one contextual action |
| `InlineNotice` | Persistent message, specific next action, optional technical detail |
| `FocusRing` | Separate 2 px system/accent outline with 2 px clearance |
| `ChromeButton` | Native action, accessible name, focus, 44 px hit target |
| `SignalPath` | Three labeled workflow nodes; connectors animate only on real state transitions |
| `SettingRow` | Label, description, control, saved/validation state; reflows at large text |
| `HUD surface` | Two reserved lines, coarse meter, no controls, transcript, or native blur |

All interactive components implement default, hover, focused, pressed,
disabled, loading, and error states across light, dark, High Contrast,
full, reduced, and off effects.

## Screen contract

### Main shell and Home

- The title bar contains Speakr identity, a non-interactive local privacy cue,
  and platform-appropriate window controls.
- Navigation remains labeled: Home, Practice, Vocabulary, Settings, Help.
- Home's dominant surface pairs truthful readiness with the Dictation switch.
- The primary instruction is the current hotkey and Hold or Toggle behavior.
- Start Practice and Change shortcut remain visible without opening Settings.
- Microphone, model, cleanup, privacy, and latest-outcome status use compact
  readable rows rather than a uniform card grid.
- Persistent recovery remains available after a transient HUD retires.

### Onboarding

```text
Privacy --> Permissions --> Speech model --> Shortcut --> optional Practice --> Home
```

- One primary action per frame; Back and Skip remain visible and labeled.
- Permission and model failures explain what happened and provide one specific
  next action.
- Hotkey capture has no timeout, exposes Cancel, and accepts Escape.
- Practice never gates completion.
- Directional movement is 180 ms only when Reduced Motion is not active.

### Practice

- Show a coarse five-segment microphone meter and `Low`, `Good`, or `High`.
- Never display clarity, confidence, correctness, or a speech score.
- Use the exact label: "Not stored by Speakr; clears when you leave Practice."
- Temporary text sits in a highly opaque content well.
- Retry, Clear, Add word, and Add replacement are labeled actions.
- Practice never injects, logs, learns, enters formatter recent context, or
  touches the clipboard, and it clears on every existing exit path.

### Vocabulary

- Manual words, Replacements, and Learned words are separate sections with
  neutral counts.
- Empty states explain the feature and present one relevant action.
- Approve, forget, remove, and destructive actions remain labeled and guarded
  by confirmation or Undo.
- Failed input stays visible with inline recovery.
- The expert raw-file action is secondary and explicitly local.

### Settings

- Search matches labels and descriptions, reports a result count, preserves
  category context, and shows a useful empty state.
- Privacy remains outside Advanced.
- Visual effects offers System, Full, Reduced, and Off. The effective material
  is read-only expert information, not a warning.
- Switches save immediately with Saved and Undo. Hotkey and model changes
  require confirmation.
- Deferred or blocked changes explain the active capture or processing
  conflict.
- Advanced retains exact model, device, compute, beam, sample rate, VAD,
  streaming, duration, injection, Ollama, per-app tone, and excluded-app
  values.

### Help and diagnostics

- Setup repair, local privacy explanation, current hardware/model, local log
  and config actions, and reset-by-section remain visible.
- Recovery copy names the local subsystem and one next action.
- Technical detail is progressively disclosed and never replaces the plain
  explanation.
- No help surface links to a remote page.

### Tray

- Retain Open Speakr, Dictation On or Off, current state, browser recovery,
  and Quit.
- The tray is not restyled into a custom floating window.
- Closing the main window leaves tray dictation running.

### HUD

- Standard is approximately 360 by 96; Large is approximately 460 by 128.
- Default position is bottom-center, 24 logical pixels inside the active
  monitor's work area.
- Active monitor is captured at hotkey-down and does not change mid-dictation.
- Two text lines are always reserved so concurrent jobs never resize the HUD.
- Active capture outranks active pipeline; an older completion never hides a
  newer capture.
- The surface is at least 96% opaque and never uses desktop-backed blur.
- It is pointer-transparent, non-focusable, non-activating, absent from tab
  order, and transcript-free.
- Focus-retention failure disables the HUD for the session and preserves tray
  feedback.

### Browser recovery

- Use a static local orbital backdrop and opaque glass-like surfaces.
- Honor `prefers-contrast` and `prefers-reduced-motion`.
- Do not attempt native material or custom desktop chrome.
- Preserve loopback-only behavior, token authentication, Host and Origin
  rejection, CSP, no CORS, `Cache-Control: no-store`, sanitized events, and
  Practice exclusion.

## Motion and state flow

| Transition | Contract |
|---|---|
| HUD hidden to Listening | Opacity 0 to 1, translate Y 8 to 0, 160 ms |
| Listening to processing | Meter settles 100 ms; icon and label crossfade 120 ms |
| Processing stage | Connector scale fill and label crossfade, 160 ms |
| Inserting to success | One check draw or restrained bloom, 220 ms; hold 1.2 s |
| Any state to error | Icon, border, and label crossfade, 160 ms; no shake |
| Page change | Opacity plus 8 px settle, 160 ms; focus moves to heading |
| Onboarding next or back | Directional 12 px slide and fade, 180 ms |
| Toggle | Thumb transform 140 ms; label changes immediately |
| Disclosure | Layout changes immediately; content fades 120 ms |

Reduced Motion removes translation, drawing, sweep, connector, scale, and
crossfade animations. States change immediately while success and error
reading time remains unchanged. There is no idle animation.

## Reference-board inventory

The following boards are required before runtime styling is accepted. This
specification does not create them.

| Planned file | Frames and annotations |
|---|---|
| `luminous-orbit-home-light-dark.png` | Light and dark Home, 960 by 700, custom Windows/macOS chrome, exact readiness/privacy copy |
| `luminous-orbit-responsive-accessibility.png` | 640 by 520 at 200%, Large HUD, High Contrast, reduced effects, focus ring |
| `luminous-orbit-onboarding-practice.png` | Privacy -> Permissions -> Model -> Shortcut -> Practice; arrows, Skip, retry, meter, exact privacy label |
| `luminous-orbit-settings-vocabulary-help.png` | Search results, empty search, privacy, Advanced, Vocabulary sections, Help recovery |
| `luminous-orbit-hud-motion.png` | Listening -> Transcribing -> Cleaning -> Inserting -> Inserted; durations, concurrent job, mic and edit errors |

Board rules:

- Use system typography, local abstract shapes, labeled controls, and exact
  production copy.
- Show light and dark parity rather than presenting dark mode as the only
  designed state.
- Show full, reduced, and opaque fallback behavior.
- Use explicit arrows and duration labels for flows.
- Do not show a star field, particle effect, decorative waveform, gradient
  text, speech score, cloud imagery, tiny copy, or watermark.
- Reference boards never ship in the runtime interface.

## Persona acceptance

| Persona | Acceptance condition |
|---|---|
| New user | Completes setup and optional Practice without tray knowledge, JSON, or technical jargon; identifies the primary action in every frame |
| Expert user | Uses tray-first behavior, custom HUD preferences, keyboard navigation, searchable Advanced, and exact hardware/material details |
| Variable or unclear speech | Uses Hold or Toggle, neutral microphone feedback, language/model controls, and vocabulary correction without grading or "speak clearly" copy |
| Low-vision user | Receives opaque High Contrast, 200% reflow, 44 px targets, 2 px focus, screen-reader semantics, and a reflowing Large HUD |
| Elderly user | Encounters no timed step, retains persistent recovery, guarded deletion, familiar window behavior, literal labels, and one dominant action per view |
| Privacy reviewer | Confirms native compositor pixels never enter application state and no user-derived content leaves the machine |
| Feasibility reviewer | Confirms unsupported material and chrome paths always produce a visible, usable fallback window |

A material persona veto reopens the complete review. Acceptance requires all
five user personas plus privacy and feasibility to pass the integrated
interface, not only isolated boards.

## Review checklist

- [ ] Every visible state uses icon, text, and shape rather than color alone.
- [ ] Primary and secondary text meet 4.5:1 after final compositing; essential
      text targets 7:1; control boundaries and focus meet 3:1.
- [ ] Light, dark, High Contrast, full, reduced, off, and software-rendered
      states are represented and testable.
- [ ] 960 by 700 and 640 by 520 at 200% contain no clipped labels, controls,
      focus, or shadows.
- [ ] Custom chrome retains Windows snap/system-menu and macOS native
      lifecycle behavior.
- [ ] Native setup failure restores a normal frame before show.
- [ ] No page introduces a local color, radius, duration, or one-off glass
      implementation outside the shared token system.
- [ ] No animation runs while idle or survives Reduced Motion.
- [ ] HUD appearance never changes foreground focus or caret identity.
- [ ] No remote resource or private working content enters interface state.
- [ ] All persona acceptance conditions pass with no material veto.
