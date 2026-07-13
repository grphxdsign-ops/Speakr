# Release proof contract

Speakr release jobs prove the exact distributable rather than treating a
successful PyInstaller build as launch evidence. The proof remains entirely
local to the runner and never enables telemetry, update checks, or product
networking.

## Two release modes

- A manual `workflow_dispatch` run is **proof-only**. It builds and exercises
  both platform artifacts, uploads immutable workflow artifacts, and never
  creates or mutates a GitHub release.
- A `v*` tag is **publish-eligible** only when both platform proof jobs pass
  and every signing/notarization credential is present. Publication is one
  final job depending on both platforms, so a partial release cannot be
  published.

The release source identity is the checked-out commit. A tag build must prove
that the tag resolves to that same commit. A manual run cannot redirect its
artifacts to an unrelated tag.

## Build and scan

Both platforms use Python 3.11, `requirements-release.txt`, and
`scripts/build_release.py`. The latter is the single PyInstaller argument
contract and always performs a clean build. QtNetwork is retained only because
Qt QML imports that Essentials binding transitively; Speakr does not call its
network API.

Before signing or wrapping, `scripts/scan_artifact_privacy.py` verifies the
native QML, HUD, icon, and the deterministic native-controller capability
marker. It rejects embedded browser engines, Addons module families, remote UI
URLs, and updater/telemetry/crash-report SDKs. The final installed or mounted app
is scanned again after extraction.

## Runtime readiness receipt

The installed application writes a receipt only when the release runner sets:

```text
SPEAKR_RELEASE_PROOF_PATH=<runner-private path>
SPEAKR_RELEASE_PROOF_QUIT=1
```

Production launches do not set these variables, so no receipt is written. The
receipt is emitted only after the native frontend is accepted, the tray is
visible, and any required main window is visible and exposed. Proof mode then
quits before microphone capture, model loading, Ollama startup, hotkey
registration, or pipeline workers begin.

The schema contains only booleans and fixed enums:

```json
{
  "chrome": "custom",
  "effect_tier": "full",
  "frontend": "native",
  "main_window_exposed": true,
  "main_window_required": true,
  "main_window_visible": true,
  "material": "mica",
  "native_material_available": true,
  "renderer": "hardware",
  "schema": 1,
  "tray_visible": true
}
```

Fallback values such as `scene_glass`, `solid`, `system_frame`, and `software`
are valid when the runner or platform cannot provide the native effect. A
browser-recovery frontend is never valid release proof. Audio, transcripts,
selected text, clipboard data, screen content, window titles, usernames,
machine paths, and configuration values are absent by construction.

## Offline core receipt

The build runner uses the one permitted Hugging Face model download to preseed
a private `tiny` faster-whisper cache. It then launches the same installed or
copied artifact a second time with Ollama disabled and:

```text
SPEAKR_RELEASE_CORE_PROOF_PATH=<runner-private path>
```

This environment-only path installs a loopback-only Python socket and DNS
guard before `speakr.app` is imported, forces Hugging Face and Transformers
offline, disables Hugging Face telemetry, and starts the real application
core. A success receipt is written only after the preseeded model loads and
warms up, rule-based cleanup is ready, the guard remains active, and no
non-loopback attempt was blocked. The process then quits through the normal
application shutdown path.

```json
{
  "blocked_attempts": 0,
  "cleanup_path": "rules",
  "core_ready": true,
  "guard_active": true,
  "model_ready": true,
  "model_source": "preseeded_local",
  "network_policy": "loopback_only",
  "offline_mode": true,
  "ollama": "disabled",
  "schema": 1
}
```

The second launch also writes and validates the native UI receipt without the
fast-quit flag. This proves native UI and real local-model readiness in the
same exact-artifact process. Both proof mechanisms are inert when their
environment variables are absent.

## Evidence manifest and publication

Each platform emits a JSON manifest beside its artifact. The manifest binds
the full source commit and optional version tag to the artifact SHA-256, the
LF-normalized `requirements-release.txt` SHA-256, platform architecture, public signing
identity/team evidence, notarization status, both scan stages, and the two
fixed runtime receipts. It contains no runner path, username, log text,
configuration, transcript, or model name.

The final tag-only publisher downloads both platform artifacts and manifests,
recomputes both artifact and dependency-lock hashes, rechecks source/tag
identity, revalidates both receipt schemas, and requires Authenticode for
Windows plus Developer ID signing and notarization for macOS. The four files
are then published together. Manual proof runs retain the same manifests but
cannot enter the publisher.

## Platform evidence

Windows proof silently installs `Speakr-Setup.exe` into an isolated location,
launches that installed copy for both receipts, validates them, checks the
installer and installed executable signatures when the run is
publish-eligible, and uninstalls it.

macOS proof mounts `Speakr.dmg`, copies `Speakr.app` out of the read-only image,
launches the copied app for both receipts, validates them, asserts its arm64
executable, and checks Gatekeeper, codesigning, and notarization when the run
is publish-eligible.

Missing release credentials are an explicit tag-release failure. They may not
be replaced with an ad-hoc signature while publishing. Proof-only runs may
produce clearly labeled non-distributable artifacts so the packaging and
runtime paths remain testable without impersonating a signed release.
