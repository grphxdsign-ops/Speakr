# Product

## Register

product

## Users

Speakr serves people who want fast, private voice dictation on Windows and
macOS. The inclusive baseline covers first-time users, expert keyboard users,
people with variable or unclear speech, people with low vision, and older
adults. Users are usually working in another application and need Speakr to
communicate its state without taking focus.

## Product purpose

Speakr turns speech into cleaned-up text at the cursor while keeping audio,
transcripts, context, and learned vocabulary on the user's machine. Success
means a user can install it, choose a shortcut, complete an optional practice
dictation, understand every runtime state, recover from errors, and configure
accuracy or privacy without editing JSON.

## Brand personality

Private, lucid, calm, and quietly futuristic.

Luminous Orbit is the product expression: a dark orbital observatory at night
and luminous lunar mist by day. It may feel atmospheric and dimensional, but
never theatrical. Its visual finish supports quick state recognition and
local-first trust rather than performing intelligence.

## Anti-references

- Sci-fi control rooms, star fields, particles, decorative waveforms, gradient
  text, grain, infinite shimmer, breathing halos, or constantly moving
  backgrounds.
- Glass on every row, nested translucent cards, low-contrast blur, or
  atmosphere that competes with instructions and status.
- Tiny muted copy, icon-only primary actions, color-only states, hidden
  timeouts, and unfamiliar custom-window behavior.
- Transcript timelines, cloud-account patterns, speech scores, or copy that
  judges how clearly a person speaks.
- Interfaces that hide important privacy behavior or force technical settings
  into the primary workflow.

## Design principles

1. Show truthful state without stealing focus.
2. Make privacy behavior visible and literal.
3. Keep the simple path calm while preserving exact expert control.
4. Use atmosphere to establish place, not to communicate state by itself.
5. Use motion only to explain a real state change.
6. Make recovery local, specific, persistent, and respectful.
7. Preserve familiar desktop behavior under custom visual treatment.

## Visual direction

- Follow the operating system's light or dark appearance by default.
- Use native Windows Mica and macOS Vibrancy when supported, with deterministic
  scene-glass and solid fallbacks.
- Reserve glass for the outer shell, navigation, major surfaces, contextual
  notices, and HUD. Keep text-heavy content wells 92--96% opaque.
- Use restrained violet, cyan, and blush atmosphere over deep orbital or pale
  lunar canvases. Never use gradient text or decorative motion.
- Use a fully custom title-bar presentation while retaining native movement,
  resizing, snapping, maximization, fullscreen, close-to-tray, system-menu,
  keyboard, and accessibility behavior.
- Use the three-stage signal path as a static identity for Transcribe, Clean
  up, and Insert. It may adopt an orbital geometry but never becomes a
  decorative waveform.

## Accessibility and inclusion

Use system light and dark palettes, the OS palette whenever High Contrast or
Increased Contrast is active, and deterministic local roles for the explicit
in-app High contrast choice; 16 px-equivalent body text; 44 by 44
logical-pixel targets; visible 2 px focus treatment;
keyboard-complete navigation; accessible Qt roles and names; reduced-motion
and reduced-transparency support; reflow at 200% scaling; icon, text, and
shape redundancy for every state.

OS High Contrast or Increased Contrast overrides every saved theme/effects
choice, removes branded transparency, and uses an opaque system palette. The
manual High contrast theme uses audited black, white, cyan, yellow, and
semantic role pairs rather than an arbitrary normal system palette. Reduce
Transparency, RDP, software rendering, or native material failure selects a
quieter local fallback without hiding the window.
Practice is optional and never grades speech. Hotkey capture asks for one key,
has no timeout, and always offers Cancel and Escape. If an existing Windows
key combination forces press-to-start/press-to-stop behavior, every visible
instruction states that effective behavior without rewriting the user's saved
mode.

Background screen-reader announcements are opt-in because they could enter
the microphone. The visual HUD contributes no accessibility live region; one
job-keyed bridge channel announces only Listening, Processing locally, and the
final result.

## Privacy and product boundaries

- No remote assets, fonts, telemetry, analytics, crash uploads, update checks,
  WebEngine, WebView2, cloud services, or new outbound requests.
- No transcript history or transcript text in the HUD. Practice text remains
  temporary, isolated, and in memory.
- Native compositors may render material from the desktop, but Speakr never
  reads, stores, exposes, or transmits the sampled pixels.
- Visual work does not change transcription, formatting, injection, hotkey,
  dictionary, learning, or Practice-isolation behavior.
- HUD focus and caret safety outrank visual fidelity. The HUD never uses a
  desktop-backed blur and is disabled for the session if focus retention
  cannot be guaranteed.
