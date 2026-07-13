# Speakr design system

## Overview

Luminous Orbit is Speakr's adaptive desktop interface. It combines a deep
orbital observatory in dark mode with luminous lunar mist in light mode. The
experience is rounded, layered, and atmospheric while remaining quiet enough
for a person to understand at a glance from another application.

The earlier Quiet Signal visual prohibition on glass, glow, and atmospheric
color is superseded. Its privacy, focus-retention, accessibility, truthful
state, temporary Practice, and local-only constraints remain binding.

The complete screen, component, native-chrome, effects, and acceptance
contract lives in [`docs/design/luminous-orbit-spec.md`](docs/design/luminous-orbit-spec.md).

## Color

These sRGB tokens are the runtime source of truth.

| Role | Light | Dark |
|---|---|---|
| Canvas | `#EDF1FA` | `#090B18` |
| Strong content surface | `#F8FAFF` | `#20243A` |
| Primary text | `#17182A` | `#F2F3FC` |
| Secondary text | `#55596D` | `#B4B7C9` |
| Meaningful border | `#747A92` | `#737A99` |
| Accent | `#6657D8` | `#A89AFB` |

Atmosphere uses low-opacity violet, cyan, and blush fields. It never carries
meaning by itself and is removed in High Contrast. Essential text targets
7:1 where practical and never falls below 4.5:1 after compositing. Secondary
text, placeholder text, borders, focus, and controls are tested against the
final composited surface rather than their nominal source color. Meaningful
controls and boundaries remain at least 3:1.

Semantic success, warning, and danger colors remain distinguishable through
icon, label, and shape. Windows High Contrast and macOS Increased Contrast
replace branded colors with the system palette.

## Material and effects

Speakr persists one preference:

```text
ui.visual_effects: system | full | reduced | off
```

The default is `system`. The resolved material is one of:

```text
mica | vibrancy | scene_glass | solid
```

Resolution order:

1. High Contrast or Increased Contrast forces `off` and `solid`.
2. OS Reduce Transparency forces `reduced`.
3. RDP, virtualized display, software rendering, or graphics failure forces
   `reduced`.
4. Explicit `off` or `reduced` is honored.
5. Otherwise use `full`.
6. If native material is unavailable, `full` resolves to `scene_glass` rather
   than blocking launch.

Windows 11 build 22621 or newer uses Mica for the long-lived main window.
macOS uses Vibrancy behind the main QML scene. The HUD never uses native
desktop-backed blur. `scene_glass` is drawn from local QML colors and shapes;
it never samples the screen.

| Surface | Full effects | Reduced effects | Off |
|---|---:|---:|---|
| Outer shell veil | 72% dark / 78% light | 94% | Solid canvas |
| Navigation material | 76% dark / 82% light | 96% | Strong surface |
| Major surface | 84% dark / 88% light | 96% | Strong surface |
| Contextual notice | 88% dark / 92% light | 96% | Strong surface |
| Text-heavy content well | 94% dark / 96% light | 100% | Strong surface |
| HUD | 96% minimum | 100% | 100% |

Do not nest glass within glass. A content well inside a glass surface is
opaque enough to preserve reading contrast and a clear layer hierarchy.

## Typography

- Before QML loads, Qt resolves the system UI font (Segoe UI on native Windows
  and SF Pro UI on native macOS) from its local font database. If GeneralFont
  is generic, Qt's concrete default family is used. Private family names are
  never hard-coded, and discovery failure never blocks the window.
- Page heading: 28 px, semibold.
- Section heading: 22 px, semibold.
- Status heading: 18 px, semibold.
- Body: 16 px, regular.
- Secondary: 15 px, regular.
- Labels and controls: 16 px, medium.
- Prose line length: at most 70 characters.

Text remains flat and opaque. Do not use gradient, outlined, blurred, or
glowing type.

## Spacing, shape, and layout

- Spacing tokens: 4, 8, 12, 16, 24, and 32 logical pixels.
- Radius tokens: 14 px controls, 20 px major panels, and 28 px shell.
- Pills are limited to compact status and metadata.
- Minimum interactive target: 44 by 44 logical pixels.
- Main window: 960 by 700 default, 640 by 520 minimum.
- At 860 logical pixels and wider, labeled navigation sits beside content.
- Below 860, labeled navigation moves above content. At 640 by 520 and 200%
  text, all five labels remain visible in a two-column, three-row grid.
- Content reflows before it truncates. No primary action becomes icon-only.
- Use one shell layer and one content hierarchy; avoid nested-card grids.

## Custom chrome

The main window uses a custom visual title bar. The operating system continues
to own movement, resizing, snapping, maximization, fullscreen, system menus,
and window lifecycle.

- Windows provides DWM corners and shadow, eight resize regions, mixed-DPI
  work-area bounds, `HTMAXBUTTON` Snap Layouts, Win+Z, Alt+Space, and
  double-click maximize/restore.
- macOS retains titled, closable, miniaturizable, and resizable window masks
  with full-size content, hidden standard controls, and native
  close/minimize/zoom/fullscreen actions.
- Minimize, Maximize or Restore, and Close each have accessible roles, names,
  44 px targets, and visible focus.
- Close hides Speakr to the tray. Quit remains an explicit separate action.
- Chrome initialization failure restores the normal system frame before the
  window becomes visible.

The custom title bar contains no application setting or page action. Drag and
control regions never overlap.

## Components

- `CosmicBackdrop`: static local violet, cyan, and blush fields with abstract
  orbital curves; no image download, particle system, or idle animation.
- `GlassSurface`: one material boundary with resolved opacity, 1 px meaningful
  edge, and optional restrained shadow. It becomes opaque in `off`.
- `StatusOrb`: icon-and-label state marker; it never uses color alone.
- `SectionHeading`: heading, optional description, and one contextual action.
- `InlineNotice`: persistent recovery or saved-state message with a specific
  next action.
- `FocusRing`: independent 2 px accent or system-highlight outline with 2 px
  clearance; it is never clipped by a rounded parent.
- `ChromeButton`: accessible window control mapped to native behavior.
- Signal path: three labeled nodes for Transcribe, Clean up, and Insert with
  state-driven connectors only.
- Setting row: visible label, description, control, save state, and inline
  validation.
- HUD: two reserved text lines, coarse five-segment input meter, and no
  interactive controls or transcript content.

Every interactive component implements default, hover, focus, pressed,
disabled, loading, and error states in light, dark, High Contrast, full,
reduced, and off effects modes.

## Motion

- Fast: 100 ms.
- Standard: 160 ms.
- Emphasis: 220 ms.
- Ease out: `cubic-bezier(.22, 1, .36, 1)`.
- Ease in: `cubic-bezier(.4, 0, 1, 1)`.
- Page change: opacity plus 8 px settle, 160 ms.
- Hover: color plus optional 1 px lift, 100 ms.
- Press: scale no lower than `.99`, 100 ms.
- Pipeline stage: connector fill and crossfade, 160 ms.
- Success: one check draw or restrained bloom, 220 ms; retain a 1.2-second
  reading window.
- Error: icon, border, and label crossfade only.

Motion explains a state transition. There is no bounce, elastic easing,
shake, parallax, idle drift, breathing glow, fake progress, or delayed stage
completion. Reduced Motion makes transformations and drawing instant while
preserving success and error reading time.

### Runtime motion flow

```text
HUD hidden --160 ms opacity + 8 px settle--> Listening
Listening --120 ms crossfade--> Transcribing locally
Transcribing --160 ms connector fill--> Cleaning up locally
Cleaning up --160 ms connector fill--> Inserting text
Inserting --220 ms check draw--> Inserted --1.2 s reading time--> hidden

Any state --160 ms icon/border/label crossfade--> recoverable error
Page A --160 ms fade + 8 px settle--> Page B (focus moves to heading)
Onboarding step A --180 ms directional fade--> step B
```

## Product flows and content

```text
Privacy --> Microphone permissions --> Speech model --> Shortcut --> optional Practice --> Home

Ready --hotkey down--> Listening --valid release--> Transcribing locally
  --> Cleaning up locally --> Dictionary replacements --> Inserting text --> Inserted --> Ready

Processing job A + hotkey for job B
  --> Listening B is primary
  --> job A remains on the reserved secondary line
  --> completion A cannot hide or replace B
```

Use short, literal state copy: Ready, Listening, Transcribing locally,
Cleaning up locally, Inserting text, Inserted. Ollama unavailability is
presented as Basic cleanup active, not as a blocking error. Practice uses the
label "Not stored by Speakr; clears when you leave Practice." Never ask a
user to speak more clearly and never assign a speech or confidence score.

## Reference boards

The Luminous Orbit board set is stored locally as design-only references:

- `docs/design/luminous-orbit-home-light-dark.png` -- light and dark Home at
  960 by 700 with custom chrome.
- `docs/design/luminous-orbit-compact-high-contrast.png` -- 640 by 520,
  200% text, High Contrast, and reduced-effects states.
- `docs/design/luminous-orbit-onboarding-practice.png` -- connected setup and
  Practice frames with explicit arrows.
- `docs/design/luminous-orbit-settings-vocabulary.png` -- settings,
  vocabulary, empty, validation, and recovery states.
- `docs/design/luminous-orbit-hud-motion.png` -- timed runtime, concurrency,
  success, and error storyboard.

Boards are design references only. The shipped interface uses local QML,
local assets, and operating-system fonts.

## Privacy constraints

No remote assets, fonts, telemetry, WebView, QtWebEngine, cloud service,
update check, or crash upload. QtQml in PySide6 6.11.1 requires the
`PySide6.QtNetwork` binding to import, so release tests retain that transitive
runtime binding while rejecting every Speakr import of its APIs. Runtime
state never includes transcript text, selected text, screen content,
clipboard content, audio, or foreground-window titles. Practice text remains
isolated in memory and clears on navigation, window hide, minimize, close, OS
lock, explicit Clear, and app exit.

Native material is presentation-only. The compositor may sample pixels behind
the window, but Speakr never receives those pixels in Python, QML state, logs,
screenshots, telemetry, or network traffic.
