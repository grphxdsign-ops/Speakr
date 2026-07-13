# Luminous Orbit controller ledger

This ledger records the controller's merge order and exclusive lane handoff.
Feature heads were squash-merged; the `Main merge` column is therefore the
authoritative integrated source. Historical worktrees are retained only as
review evidence and are never reused for a later lane.

| Order | Planned lane | Branch / worktree | Dependency main SHA | PR | Main merge | Evidence | Status |
|---:|---|---|---|---:|---|---|---|
| 0 | Native baseline | `codex/luminous-00-baseline` / controller tree | `752f65c` | 15 | `080d794` | Baseline native QML, lifecycle, recovery security, packaging; 57-test gate at handoff. | MERGED |
| 1 | Pull-request CI | `codex/luminous-01-pr-ci` / retired | `080d794` | 16 | `10059bb` | Windows/macOS Python 3.11 checks, offline Qt suite, dependency boundary. | MERGED |
| 2 | Design contract | `codex/luminous-02-design-contract` / retired | `10059bb` | 17 | `e0fa80c` | Written contract and five local reference boards. | MERGED |
| 3 | Native window | `codex/luminous-03-native-window` / `Speakr-wt-native` | `e0fa80c` | 20 | `e2c58d4` | Mica/Vibrancy capabilities, chrome fallback, mocked and hosted platform tests. | MERGED |
| 4 | QML foundation | `codex/luminous-04-foundation` / `Speakr-wt-foundation` | `e0fa80c` | 18 | `04f4c02` | Theme/effect tiers/shared controls across normal, HC, reduced, and software modes. | MERGED |
| 5 | Shell and Home | `codex/luminous-05-shell-home` / `Speakr-wt-shell` | `04f4c02` plus native corrections | 23 | `53cb2a3` | Responsive shell, Home, custom chrome, focus and visibility tests. | MERGED |
| 6 | Onboarding and Practice | `codex/luminous-06-onboarding-practice` / `Speakr-wt-setup` | `53cb2a3` | 22 | `dee35ae` | Setup/recovery flow and Practice-isolation presentation tests. | MERGED |
| 7 | Settings and Help | `codex/luminous-07-settings-help` / `Speakr-wt-settings` | `dee35ae` | 24 | `fb86155` | Search, validation, Undo, effects information, reflow and keyboard tests. | MERGED |
| 8 | Vocabulary | `codex/luminous-08-vocabulary` / `Speakr-wt-vocabulary` | `fb86155` | 27 | `b872be5` | Separated collections, guarded actions, error and empty states. | MERGED |
| 9 | HUD | `codex/luminous-09-hud` / `Speakr-wt-hud` | `b872be5` | 28 | `6636ff8` | Flags, focus guard, concurrency, job timers, motion, Large/HC modes. | MERGED |
| 10 | Browser recovery | `codex/luminous-10-browser-recovery` / `Speakr-wt-recovery` | `b872be5` | 19 | `449e021` | Embedded-only visual parity plus auth/CSP/Host/Origin/no-store gates. | MERGED |
| 11 | Verification harness | `codex/luminous-11-verification` / `Speakr-wt-verification` | `6eafb3d` | 29 | `72c9fcb` | 220-test gate, source-bound schema-3 report/manifest, hosted Windows/macOS checks. | MERGED |
| 12 | Integration/personas | `codex/luminous-12-integration` / controller tree | `72c9fcb` | 38 | `96c13d3` | Eleven veto fixes, three audit rounds, 240-test local gate, schema-3 evidence, and required Windows/macOS checks. | MERGED |
| 13 | Release proof | `codex/luminous-13-release` / `Speakr-wt-release` | `96c13d3` | TBD | TBD | Installed Windows artifact, mounted macOS artifact, privacy scan, signing/notarization evidence. | ACTIVE |

## Routed corrective PRs

The following narrow PRs were inserted when a lane gate found a shared
contract defect. They were merged before the next dependent feature lane;
none expanded transcription or privacy scope.

| PR | Main merge | Correction |
|---:|---|---|
| 21 | `8cc1140` | Callable QML/native hit-region boundary. |
| 25 | `0a70620` | Cocoa/offscreen lifecycle and native style fallback. |
| 26 | `0f23475` | Combo-box value reflow. |
| 30 | `cd5a319` | Native maximize/action routing. |
| 31 | `f3da4c8` | Settings QML binding-loop removal. |
| 32 | `00436fd` | Deterministic QML test teardown. |
| 33 | `df971d7` | macOS shortcut/focus and window actions. |
| 34 | `a763dd9` | Concrete local system-font normalization. |
| 35 | `d27c1ce` | Renderer-truth preflight and fresh-process ownership handoff. |
| 36 | `98efe41` | Plain setup and browser recovery actions. |
| 37 | `6eafb3d` | Canonical system/manual High Contrast roles. |

## Merge discipline

- Every worker lane used its own sibling worktree and an exact merged
  dependency SHA.
- Shared-contract defects returned to their owning lane or a named corrective
  lane; screen lanes did not add local color, radius, motion, or glass tokens.
- Feature PRs opened as drafts, required Windows/macOS checks, and used squash
  merge after independent review.
- `AGENTS.md`, `CLAUDE.md`, runtime config, logs, model data, dictionaries,
  learned vocabulary, and build output are user/runtime owned and excluded.
- PR-12 and PR-13 are controller-serial. PR-13 branched from the exact PR-12
  squash merge only after PR-12 was reviewed and merged.
