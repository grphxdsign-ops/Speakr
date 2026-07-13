# Luminous Orbit reference boards

These generated boards are design references only. The shipped interface is
implemented with local QML, local image assets, and operating-system fonts.
None of these raster boards are loaded by the application.

The current Luminous Orbit set is:

- [`luminous-orbit-home-light-dark.png`](luminous-orbit-home-light-dark.png): adaptive light and dark Home shells with custom chrome.
- [`luminous-orbit-compact-high-contrast.png`](luminous-orbit-compact-high-contrast.png): compact 640 by 520 navigation, 200% text intent, and the opaque High Contrast fallback.
- [`luminous-orbit-onboarding-practice.png`](luminous-orbit-onboarding-practice.png): the untimed five-step setup flow with explicit arrows and optional Practice.
- [`luminous-orbit-settings-vocabulary.png`](luminous-orbit-settings-vocabulary.png): searchable visual-effects settings and separated vocabulary collections.
- [`luminous-orbit-hud-motion.png`](luminous-orbit-hud-motion.png): the fixed-size HUD state sequence, errors, and motion timings.

Implementation verification is documented in
[`luminous-orbit-verification.md`](luminous-orbit-verification.md), including
the one-command warning, geometry, accessibility, privacy, and platform
screenshot harness.

Controller merge evidence and the repeated five-persona gate are recorded in
[`luminous-orbit-ledger.md`](luminous-orbit-ledger.md) and
[`luminous-orbit-consensus.md`](luminous-orbit-consensus.md).

Generated text and small details are illustrative. `DESIGN.md` and
`luminous-orbit-spec.md` are authoritative whenever a raster board differs
from the product copy or accessibility contract.

## Archived Quiet Signal boards

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
