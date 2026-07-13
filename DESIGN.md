# Speakr Design System

## Overview

Quiet Signal is a restrained desktop product interface. A three-node signal path represents Transcribe, Clean up, and Insert. The interface follows the operating system by default and remains legible during a quick glance while another application has focus.

## Color

Source tokens are authored in OKLCH and converted to checked sRGB values for QML.

| Role | Light source | Dark source |
|---|---|---|
| Background | `oklch(97% .010 255)` | `oklch(18% .016 255)` |
| Surface | `oklch(99% .006 255)` | `oklch(23% .018 255)` |
| Text | `oklch(24% .025 255)` | `oklch(93% .010 255)` |
| Muted text | `oklch(44% .020 255)` | `oklch(72% .018 255)` |
| Border | `oklch(82% .020 255)` | `oklch(40% .020 255)` |
| Accent | `oklch(55% .18 255)` | `oklch(72% .13 255)` |

Success, warning, and danger use restrained semantic colors. Meaning always includes an icon, label, and shape. Essential text targets 7:1 where practical and never falls below 4.5:1. Control boundaries target at least 3:1. Windows High Contrast and macOS Increased Contrast override branded tokens with the system palette.

## Typography

- System UI font only: Segoe UI on Windows and SF Pro on macOS.
- Page heading: 28 px, semibold.
- Section heading: 22 px, semibold.
- Status heading: 18 px, semibold.
- Body: 16 px, regular.
- Secondary: 15 px, regular.
- Labels and controls: 16 px, medium.
- Prose line length: at most 70 characters.

## Spacing and Layout

- Spacing tokens: 4, 8, 12, 16, 24, and 32 logical pixels.
- Minimum interactive target: 44 by 44 logical pixels.
- Main window: 960 by 700 default, 640 by 520 minimum.
- At narrow widths, labeled navigation moves above content. It never collapses to unlabeled icons.
- Use solid surfaces, full borders, and whitespace. Avoid nested cards and uniform card grids.

## Components

- Native title bar and native Qt Quick Controls.
- Status banner with icon, title, explanatory text, and an optional action.
- Signal path: three text-labeled nodes with directional connectors.
- Setting row: visible label, description, control, save state, and inline validation.
- Focus treatment: 2 px accent outline with 2 px clearance.
- Error treatment: persistent inline summary with one recommended action and optional technical detail.
- HUD: two reserved text lines, coarse five-segment input meter, no interactive controls.

Every interactive component implements default, hover, focus, pressed, disabled, loading, and error states.

## Motion

- Fast: 100 ms.
- Standard: 160 ms.
- Emphasis: 220 ms.
- Ease out: `cubic-bezier(.22, 1, .36, 1)`.
- Ease in: `cubic-bezier(.4, 0, 1, 1)`.
- Animate opacity and transforms only.
- No bounce, elastic motion, perpetual pulse, ambient drift, fake progress, or delayed stage completion.
- Reduced Motion removes translation, drawing, sweeps, and connector fills while preserving reading time.

### Motion flow

```text
HUD hidden --160 ms opacity + 8 px settle--> Listening
Listening --120 ms crossfade--> Transcribing locally
Transcribing --160 ms connector fill--> Cleaning up locally
Cleaning up --160 ms connector fill--> Inserting text
Inserting --180 ms check draw--> Inserted --1.2 s reading time--> hidden

Any state --160 ms icon/border/label crossfade--> recoverable error
Page A --160 ms fade + 8 px settle--> Page B (focus moves to heading)
Onboarding step A --180 ms directional fade--> step B
```

With Reduced Motion, every arrow changes state instantly; the 1.2-second
success and five-second error HUD reading windows remain unchanged. Error
recovery stays persistent on Home and in the tray after the HUD retires.

## Product flows

```text
Privacy --> Microphone permissions --> Speech model --> Shortcut --> optional Practice --> Home

Ready --hotkey down--> Listening --valid release--> Transcribing locally
  --> Cleaning up locally --> Dictionary replacements --> Inserting text --> Inserted --> Ready

Processing job A + hotkey for job B
  --> Listening B is primary
  --> job A remains on the reserved secondary line
  --> completion A cannot hide or replace B
```

## Reference boards

- `docs/design/quiet-signal-main-window.png` — light/dark Home.
- `docs/design/quiet-signal-onboarding-practice.png` — connected setup and Practice frames.
- `docs/design/quiet-signal-hud-motion.png` — timed runtime and recovery storyboard.

## Content

Use short, literal state copy: Ready, Listening, Transcribing locally, Cleaning up locally, Inserting text, Inserted. Ollama failure is presented as Basic cleanup active, not as a blocking error. Practice uses the label “Not stored by Speakr; clears when you leave Practice.” Never ask a user to speak more clearly and never assign a speech or confidence score.

## Privacy Constraints

No remote assets, fonts, telemetry, WebView, QtWebEngine, app-level QtNetwork API use, update checks, or crash uploads. QtQml in PySide6 6.11.1 requires the `PySide6.QtNetwork` binding to import, so release tests retain that transitive runtime binding while rejecting any Speakr import of its APIs. Runtime state never includes transcript text, selected text, screen content, clipboard content, or audio. Practice text is isolated in memory and clears on navigation, window hide/minimize/close, OS lock, explicit Clear, and app exit.
