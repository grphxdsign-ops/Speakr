# Quiet Signal reference boards

These generated boards are design references only. The shipped interface is
implemented with local QML, local image assets, and operating-system fonts.
None of these raster boards are loaded by the application.

## Main window

[`quiet-signal-main-window.png`](quiet-signal-main-window.png) compares the
light and dark Home screen at 960 × 700. The generation brief required native
title bars, solid opaque surfaces, labeled controls, the static three-node
signal path, and the exact privacy and dictation copy used by the product.

## Onboarding and Practice

[`quiet-signal-onboarding-practice.png`](quiet-signal-onboarding-practice.png)
uses five connected frames and explicit directional arrows:

```text
Privacy --> Permissions --> Speech model --> Shortcut --> Practice
```

The brief required a visible Skip action, neutral retry language, a coarse
microphone meter, and “Not stored by Speakr; clears when you leave Practice.”

## HUD motion

[`quiet-signal-hud-motion.png`](quiet-signal-hud-motion.png) is the runtime
storyboard. Its primary path and production timings are:

```text
Hidden --160 ms--> Listening
Listening --120 ms--> Transcribing locally
Transcribing --160 ms--> Cleaning up locally
Cleaning up --160 ms--> Inserting text
Inserting --180 ms--> Inserted --1.2 s--> Hidden

Any state --160 ms--> Recoverable error
```

Alternate frames cover microphone access and an unchanged selection. The
brief expressly excluded decorative waveforms, speech scores, glass, glow,
gradients, cloud imagery, tiny text, and watermarks.
