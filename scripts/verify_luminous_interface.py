#!/usr/bin/env python3
"""Run the complete Luminous Orbit interface verification harness.

The harness fails at the first broken gate and writes each command's complete
output plus a machine-readable report below ``build/ui-verification`` by
default.  The evidence map intentionally points at focused tests already in
the repository so PR-11 adds orchestration instead of cloning their logic.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]

# These exact tests are the minimum proof for each audit area.  The harness
# still runs the complete suite, including every regression test not listed.
REQUIRED_EVIDENCE_TESTS = {
    "qml_runtime_and_warnings": (
        "tests.test_qml_load.QmlLoadTests.test_main_and_hud_load_without_qml_warnings",
        "tests.test_qml_load.QmlLoadTests.test_qml_teardown_destroys_roots_and_engine_before_bridge",
        "tests.test_qml_components.QmlComponentContractTests.test_new_primitives_load_without_warnings",
        "tests.test_settings_help_qml.SettingsHelpQmlTests.test_settings_load_render_and_teardown_emit_no_qml_warnings",
        "tests.test_verification_harness.VerificationHarnessTests.test_every_qml_component_compiles_without_errors",
        "tests.test_verification_harness.VerificationHarnessTests.test_every_qml_component_is_reachable_and_has_no_unbounded_effect",
        "tests.test_verification_harness.VerificationHarnessTests.test_runtime_warning_parser_rejects_green_qml_failures",
        "tests.test_verification_harness.VerificationHarnessTests.test_platform_screenshot_runtime_diagnostics_fail_report",
        "tests.test_verification_harness.VerificationHarnessTests.test_raw_runtime_log_marker_scan_is_explicit_and_fail_closed",
    ),
    "effects_contrast_and_fallbacks": (
        "tests.test_qml_components.QmlComponentContractTests.test_effect_resolution_and_material_opacity_are_deterministic",
        "tests.test_qml_load.QmlLoadTests.test_light_dark_and_manual_high_contrast_tokens_meet_contrast_contracts",
        "tests.test_qml_components.QmlComponentContractTests.test_system_high_contrast_overrides_every_saved_theme_and_effect_choice",
        "tests.test_qml_components.QmlComponentContractTests.test_divergent_system_palette_uses_canonical_pairs_in_rendered_components",
        "tests.test_qml_components.QmlComponentContractTests.test_manual_high_contrast_component_states_and_focus_render_at_100_and_200_percent",
        "tests.test_native_window.EffectResolutionTests.test_resolution_priority_and_native_materials",
        "tests.test_native_window.NativeControllerTests.test_explicit_high_contrast_theme_forces_solid_effects_off",
        "tests.test_native_window.NativeControllerTests.test_native_failure_and_accessibility_preferences_fall_back_safely",
        "tests.test_renderer_truth.RendererDeviceTests.test_software_preflight_renders_and_leaves_no_quick_objects",
        "tests.test_hud_qml.HudQmlTests.test_software_renderer_forces_reduced_tier_without_native_hud_blur",
        "tests.test_verification_harness.VerificationHarnessTests.test_effect_tier_theme_and_contrast_matrix",
    ),
    "reduced_and_bounded_motion": (
        "tests.test_qml_components.QmlComponentContractTests.test_radius_motion_and_focus_tokens_match_contract",
        "tests.test_qml_components.QmlComponentContractTests.test_foundation_has_no_remote_or_idle_effect_mechanism",
        "tests.test_hud_qml.HudQmlTests.test_system_reduce_motion_preference_selects_zero_or_full_tokens",
        "tests.test_hud_qml.HudQmlTests.test_high_contrast_is_opaque_and_full_motion_uses_only_bounded_tokens",
        "tests.test_verification_harness.VerificationHarnessTests.test_every_qml_component_is_reachable_and_has_no_unbounded_effect",
    ),
    "scale_and_reflow_geometry": (
        "tests.test_qml_load.QmlLoadTests.test_narrow_200_percent_navigation_wraps_without_eliding_labels",
        "tests.test_shell_home.ShellHomeTests.test_home_reflows_at_minimum_size_and_200_percent_text",
        "tests.test_setup_practice_qml.SetupPracticeQmlTests.test_narrow_200_percent_high_contrast_reflows_without_horizontal_scroll",
        "tests.test_settings_help_qml.SettingsHelpQmlTests.test_settings_and_help_reflow_at_640_by_520_and_scaled_text",
        "tests.test_vocabulary_qml.VocabularyQmlTests.test_narrow_200_percent_reflow_and_visible_keyboard_focus",
        "tests.test_hud_qml.HudQmlTests.test_latched_monitor_geometry_reflows_large_hud_at_150_and_200_percent",
        "tests.test_shell_home.ShellHomeTests.test_os_high_contrast_shell_screenshot_overrides_saved_light_full_at_100_and_200_percent",
        "tests.test_verification_harness.VerificationHarnessTests.test_all_pages_reflow_and_focus_heading_across_size_scale_matrix",
    ),
    "custom_chrome_and_native_fallback": (
        "tests.test_native_window.HitRegionTests.test_controls_caption_and_resize_edges_have_stable_precedence",
        "tests.test_native_window.NativeControllerTests.test_custom_chrome_failure_restores_normal_window_flags",
        "tests.test_native_window.NativeControllerTests.test_run_native_ui_custom_chrome_fails_closed_under_offscreen_qpa",
        "tests.test_shell_home.ShellHomeTests.test_custom_chrome_reports_logical_hit_regions_and_44px_controls",
        "tests.test_shell_home.ShellHomeTests.test_shell_uses_shared_tokens_and_accessible_window_copy",
        "tests.test_shell_home.ShellHomeTests.test_system_frame_fallback_hides_duplicate_custom_titlebar",
        "tests.test_renderer_truth.RendererDeviceTests.test_gpu_preflight_failure_is_retryable_and_cleanup_is_exact",
        "tests.test_verification_harness.VerificationHarnessTests.test_windows_real_qpa_custom_maximize_changes_hwnd_and_restores",
    ),
    "hud_focus_concurrency_and_large_mode": (
        "tests.test_hud_qml.HudQmlTests.test_window_flags_content_boundary_and_bounded_rendering",
        "tests.test_hud_qml.HudQmlTests.test_overlapping_capture_keeps_previous_job_secondary_and_stale_retire_is_safe",
        "tests.test_hud_qml.HudQmlTests.test_real_settle_timer_waits_for_capture_and_cannot_retire_newer_job",
        "tests.test_hud_qml.HudQmlTests.test_latched_monitor_geometry_reflows_large_hud_at_150_and_200_percent",
        "tests.test_hud_qml.HudQmlTests.test_os_high_contrast_overrides_saved_hud_theme_and_full_effects",
        "tests.test_renderer_truth.RendererDeviceTests.test_native_windows_gpu_and_software_preserve_focus_and_caret",
        "tests.test_verification_harness.VerificationHarnessTests.test_hud_focus_guard_fails_closed_and_latches_recovery",
    ),
    "keyboard_and_heading_focus": (
        "tests.test_shell_home.ShellHomeTests.test_navigation_and_practice_cancel_untimed_hotkey_capture",
        "tests.test_shell_home.ShellHomeTests.test_fullscreen_shortcut_uses_standard_key_and_invokes_controller",
        "tests.test_shell_home.ShellHomeTests.test_window_controls_follow_platform_visual_focus_order",
        "tests.test_shell_home.ShellHomeTests.test_shell_uses_shared_tokens_and_accessible_window_copy",
        "tests.test_settings_help_qml.SettingsHelpQmlTests.test_focus_targets_remain_visible_at_supported_text_scales",
        "tests.test_settings_help_qml.SettingsHelpQmlTests.test_windows_qpa_keeps_keyboard_and_reset_focus_visible",
        "tests.test_vocabulary_qml.VocabularyQmlTests.test_narrow_200_percent_reflow_and_visible_keyboard_focus",
        "tests.test_verification_harness.VerificationHarnessTests.test_all_pages_reflow_and_focus_heading_across_size_scale_matrix",
    ),
    "privacy_and_outbound_boundary": (
        "tests.test_qml_load.QmlLoadTests.test_hostile_markup_in_plain_text_never_fetches_an_image",
        "tests.test_outbound_boundary.OutboundBoundaryTests.test_offline_interface_path_connects_only_to_loopback",
        "tests.test_outbound_boundary.OutboundBoundaryTests.test_ollama_origin_is_forced_to_numeric_loopback",
        "tests.test_outbound_boundary.OutboundBoundaryTests.test_remote_ollama_config_cannot_send_dictated_text",
        "tests.test_artifact_privacy_scan.ArtifactPrivacyScanTests.test_rejects_remote_url_in_qml_but_not_localhost",
        "tests.test_artifact_privacy_scan.ArtifactPrivacyScanTests.test_rejects_browser_engine_and_addons_names",
        "tests.test_artifact_privacy_scan.ArtifactPrivacyScanTests.test_release_environment_is_essentials_only",
        "tests.test_artifact_privacy_scan.ArtifactPrivacyScanTests.test_qml_keeps_required_qtnetwork_binding_without_app_api_imports",
        "tests.test_verification_harness.VerificationHarnessTests.test_verification_tools_add_no_network_surface",
    ),
    "lifecycle_and_fail_closed_guards": (
        "tests.test_verification_harness.VerificationHarnessTests.test_close_hides_main_while_tray_and_event_loop_remain_alive",
        "tests.test_verification_harness.VerificationHarnessTests.test_show_main_restores_hidden_and_minimized_window",
        "tests.test_verification_harness.VerificationHarnessTests.test_hud_focus_guard_fails_closed_and_latches_recovery",
        "tests.test_renderer_truth.RendererDeviceTests.test_required_main_gate_and_commit_order",
        "tests.test_renderer_truth.PreparedHandoffTests.test_frontend_commit_orders_prepare_before_core_and_aborts_once",
    ),
    "platform_screenshot_artifacts": (
        "tests.test_verification_harness.VerificationHarnessTests.test_platform_screenshot_manifest_is_complete_and_idempotent",
    ),
}


# These are product-owned findings from the first PR-12 review. PR-11 records
# and routes them without changing production QML or behavior.
ROUTED_PR12_PRODUCT_VETOES = (
    {
        "id": 1,
        "owner": "Shell/Home + HUD + browser recovery (PR-12 integration)",
        "veto": "Toggle-mode Hold/release instructions are unsafe/contradictory across Home, HUD, browser — interaction truth.",
    },
    {
        "id": 2,
        "owner": "Settings + Onboarding + browser recovery (PR-12 integration)",
        "veto": "Windows '+' hotkeys force Toggle while Settings/Onboarding show impossible Hold; capture promises combinations but captures one key — hotkey presentation.",
    },
    {
        "id": 3,
        "owner": "Browser recovery (PR-12 integration)",
        "veto": "Browser shortcut capture falsely says 'no hidden background access' despite untimed global hook — privacy copy.",
    },
    {
        "id": 4,
        "owner": "Shell/Home (PR-12 integration)",
        "veto": "Title-bar local privacy cue disappears below 720px/above 150% — low-vision/privacy.",
    },
    {
        "id": 5,
        "owner": "Browser recovery (PR-12 integration)",
        "veto": "Browser privacy checkboxes are all labeled 'Enabled' and never show On/Off truth — browser a11y/privacy.",
    },
    {
        "id": 6,
        "owner": "Onboarding/Practice (PR-12 integration)",
        "veto": "Practice idle shows Retry before an attempt and says Waiting for sound before listening — Practice truth.",
    },
    {
        "id": 7,
        "owner": "Onboarding/Practice (PR-12 integration)",
        "veto": "Onboarding Practice has competing Start Practice + Finish setup primaries and duplicate Skip/Finish path — new/elderly hierarchy.",
    },
    {
        "id": 8,
        "owner": "Shared foundation accessibility (PR-12 integration)",
        "veto": "SectionHeading titles are ignored/grouped, absent from screen-reader heading navigation — shared a11y.",
    },
    {
        "id": 9,
        "owner": "Shell/Home (PR-12 integration)",
        "veto": "Home uses forbidden four-card summary and pushes status/privacy/latest outcome below default 960x700 fold — shell/Home hierarchy.",
    },
    {
        "id": 10,
        "owner": "Onboarding/Practice (PR-12 integration)",
        "veto": "Future onboarding steps are disabled but announced as 'Return to…' — setup a11y.",
    },
    {
        "id": 11,
        "owner": "HUD (PR-12 integration)",
        "veto": "HUD opt-in background announcements expose every pipeline stage instead of coalesced Listening / Processing locally / final — HUD a11y/privacy.",
    },
)


def invalid_evidence_test_ids(
    evidence: dict[str, Sequence[str]] | None = None,
) -> list[str]:
    """Return IDs that do not resolve to exactly one real unittest case."""

    loader = unittest.TestLoader()
    invalid: list[str] = []
    selected = REQUIRED_EVIDENCE_TESTS if evidence is None else evidence
    for test_ids in selected.values():
        for test_id in test_ids:
            error_count = len(loader.errors)
            suite = loader.loadTestsFromName(test_id)
            new_errors = loader.errors[error_count:]
            failed_test = any(
                case.__class__.__name__ == "_FailedTest"
                for case in _iter_test_cases(suite)
            )
            if suite.countTestCases() != 1 or new_errors or failed_test:
                invalid.append(test_id)
    return invalid


def _iter_test_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_test_cases(item)
        else:
            yield item


# A unittest process can exit successfully while Qt writes runtime QML
# failures to stderr. These patterns deliberately target runtime diagnostics,
# not the advisory output from the separate qmllint step.
QML_RUNTIME_WARNING_PATTERNS = (
    re.compile(
        r"(?im)^.*\.qml:\d+(?::\d+)?:\s*\S.*$"
    ),
    re.compile(r"(?im)^.*\bbinding loop detected\b.*$"),
    re.compile(
        r"(?im)^.*qt\.qpa\.fonts:.*"
        r"(?:missing font family|font family aliases).*$"
    ),
    re.compile(
        r"(?im)^.*Scenegraph already initialized,\s*"
        r"setBackend\(\) request ignored.*$"
    ),
    re.compile(
        r"(?im)^.*(?:qml|qrc|file):.*\.qml.*(?:error|warning).*$"
    ),
    re.compile(r"(?im)^.*scene\s*graph.*(?:error|failed).*$"),
    re.compile(
        r"(?im)^.*(?:failed|unable) to (?:create|initialize).*"
        r"(?:RHI|renderer|graphics|Direct3D|Metal|OpenGL|Vulkan).*$"
    ),
)

# Runtime diagnostics may surface from either the unittest process or the
# separate native/offscreen screenshot process.  Keep qmllint out of this set:
# its advisory diagnostics are governed by qmllint's own exit status.
RUNTIME_DIAGNOSTIC_STEPS = frozenset(
    {
        "unit_and_interface_tests",
        "platform_screenshots",
    }
)


def detect_qml_runtime_warnings(output: str) -> list[str]:
    """Return unique QML/renderer diagnostics from a runtime-process log."""

    matches = []
    seen = set()
    for pattern in QML_RUNTIME_WARNING_PATTERNS:
        for match in pattern.finditer(output or ""):
            line = " ".join(match.group(0).strip().split())
            if line and line not in seen:
                seen.add(line)
                matches.append(line)
    return matches


def scan_raw_runtime_outputs(outputs: dict[str, str]) -> dict[str, list[str]]:
    """Scan unredacted subprocess output and return only failing markers.

    The raw text stays in memory: review logs are path-redacted separately.
    Only runtime steps are eligible so advisory qmllint text cannot be
    misrepresented as an application-rendering failure.
    """

    findings: dict[str, list[str]] = {}
    for name in sorted(RUNTIME_DIAGNOSTIC_STEPS):
        diagnostics = detect_qml_runtime_warnings(outputs.get(name, ""))
        if diagnostics:
            findings[name] = diagnostics
    return findings


def detect_missing_interactive_windows_proof(output: str) -> list[str]:
    """Reject a green Windows run that skipped its focus/caret probe."""

    if platform.system() != "Windows":
        return []
    pattern = re.compile(
        r"(?im)^.*(?:"
        r"test_windows_native_probe_preserves_foreground_focus_and_caret|"
        r"test_native_windows_gpu_and_software_preserve_focus_and_caret"
        r").*\.\.\.\s+skipped.*$"
    )
    return [" ".join(match.group(0).strip().split()) for match in pattern.finditer(output)]


def native_rect_matches_work_area(
    native_rect: Sequence[int],
    work_rect: Sequence[int],
    horizontal_tolerance: int,
    vertical_tolerance: int,
) -> bool:
    """Return whether every native window edge matches its work-area edge."""

    if len(native_rect) != 4 or len(work_rect) != 4:
        return False
    horizontal_tolerance = max(0, int(horizontal_tolerance))
    vertical_tolerance = max(0, int(vertical_tolerance))
    return (
        abs(int(native_rect[0]) - int(work_rect[0])) <= horizontal_tolerance
        and abs(int(native_rect[1]) - int(work_rect[1])) <= vertical_tolerance
        and abs(int(native_rect[2]) - int(work_rect[2])) <= horizontal_tolerance
        and abs(int(native_rect[3]) - int(work_rect[3])) <= vertical_tolerance
    )


def sanitize_evidence_text(value: object, output: Path) -> str:
    """Redact machine-local roots from evidence intended for review artifacts."""

    text = str(value)
    replacements = (
        (output.resolve(), "<output>"),
        (ROOT.resolve(), "<repo>"),
        (Path.home().resolve(), "<home>"),
    )
    for path, token in replacements:
        variants = {str(path), path.as_posix()}
        try:
            variants.add(path.as_uri())
        except ValueError:
            pass
        variants = sorted(variants, key=len, reverse=True)
        for variant in variants:
            if not variant:
                continue
            text = re.sub(
                re.escape(variant),
                token,
                text,
                flags=re.IGNORECASE if os.name == "nt" else 0,
            )
    return text


def _qmllint_executable() -> str:
    name = "pyside6-qmllint.exe" if os.name == "nt" else "pyside6-qmllint"
    beside_python = Path(sys.executable).resolve().parent / name
    if beside_python.is_file():
        return str(beside_python)
    discovered = shutil.which(name) or shutil.which("pyside6-qmllint")
    if not discovered:
        raise FileNotFoundError("pyside6-qmllint was not found beside Python or on PATH")
    return discovered


def diff_check_commands(
    root: Path = ROOT,
    environment: dict[str, str] | None = None,
) -> list[tuple[str, Sequence[str], dict[str, str]]]:
    """Build committed-diff and working-tree whitespace checks truthfully."""

    environment = os.environ if environment is None else environment
    explicit_base = str(environment.get("SPEAKR_VERIFY_BASE", "")).strip()
    github_base = str(environment.get("GITHUB_BASE_REF", "")).strip()
    if explicit_base:
        candidates = (explicit_base,)
    elif github_base:
        candidates = (f"origin/{github_base}", github_base)
    else:
        candidates = ("origin/main",)

    for candidate in candidates:
        merged = subprocess.run(
            ["git", "merge-base", "HEAD", candidate],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        base_sha = merged.stdout.strip()
        if merged.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40}", base_sha):
            continue
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode == 0 and head.stdout.strip() != base_sha:
            return [
                (
                    "committed_diff_check",
                    ("git", "diff", "--check", f"{base_sha}...HEAD"),
                    {},
                ),
                ("working_tree_diff_check", ("git", "diff", "--check"), {}),
            ]
    return [("working_tree_diff_check", ("git", "diff", "--check"), {})]


def verification_commands(
    output: Path,
    *,
    qmllint_executable: str | None = None,
) -> list[tuple[str, Sequence[str], dict[str, str]]]:
    qml_dir = ROOT / "speakr" / "ui" / "qml"
    qml_files = sorted(str(path) for path in qml_dir.glob("*.qml"))
    offscreen = {
        "QT_QPA_PLATFORM": "offscreen",
        "QT_QUICK_BACKEND": "software",
        "QSG_RHI_BACKEND": "software",
        "SPEAKR_QT_SOFTWARE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    commands = [
        (
            "compileall",
            (sys.executable, "-m", "compileall", "-q", "speakr", "tests", "scripts"),
            {},
        ),
        (
            "unit_and_interface_tests",
            (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"),
            offscreen,
        ),
        (
            "qt_dependency_boundary",
            (sys.executable, "scripts/check_qt_build_environment.py"),
            {},
        ),
        (
            "qmllint",
            (
                qmllint_executable or _qmllint_executable(),
                "-I",
                str(qml_dir),
                *qml_files,
            ),
            {},
        ),
    ]
    commands.extend(diff_check_commands())
    commands.append(
        (
            "platform_screenshots",
            (
                sys.executable,
                "scripts/capture_ui_verification.py",
                "--output",
                str(output / "screenshots"),
            ),
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            },
        )
    )
    return commands


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_verification(output: Path) -> int:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "schema_version": 2,
        "status": "running",
        "automated_status": "running",
        "manual_platform_status": "required",
        "routed_product_findings_status": "open_pr12_inputs",
        "routed_product_findings": ROUTED_PR12_PRODUCT_VETOES,
        "root": "<repo>",
        "required_evidence_tests": REQUIRED_EVIDENCE_TESTS,
        "manual_platform_gates": (
            "Windows WM_NCHITTEST with physical mixed-DPI coordinates",
            "Windows 11 Snap Layout hover and Win+Z",
            "Windows system High Contrast and NVDA behavior",
            "macOS compositor, zoom/fullscreen, and VoiceOver",
            "foreground caret identity when an interactive Windows desktop is unavailable",
        ),
        "conditional_platform_tests": {
            "tests.test_hud_qml.HudQmlTests.test_windows_native_probe_preserves_foreground_focus_and_caret": (
                "A skip is not focus-retention proof; run the foreground/caret "
                "gate on an interactive Windows desktop."
            ),
            "tests.test_renderer_truth.RendererDeviceTests.test_native_windows_gpu_and_software_preserve_focus_and_caret": (
                "A skip is not renderer/focus proof; run both renderer paths "
                "on an interactive Windows desktop."
            ),
            "tests.test_verification_harness.VerificationHarnessTests.test_windows_10_real_qpa_uses_scene_glass_and_visible_system_frame": (
                "Required on Windows; skipped by design on non-Windows hosts."
            ),
            "tests.test_verification_harness.VerificationHarnessTests.test_windows_real_qpa_custom_maximize_changes_hwnd_and_restores": (
                "Required on Windows; verifies the production button, HWND zoom "
                "state, work-area geometry, controller state, and restore path."
            ),
        },
        "steps": [],
    }
    report_path = output / "verification-report.json"
    _write_report(report_path, report)

    try:
        qmllint_executable = _qmllint_executable()
    except (FileNotFoundError, OSError) as error:
        message = sanitize_evidence_text(error, output)
        log_name = "00-qmllint_discovery.log"
        (output / log_name).write_text(message + "\n", encoding="utf-8")
        report["status"] = "failed"
        report["automated_status"] = "failed"
        report["failed_step"] = "qmllint_discovery"
        report["steps"].append(
            {
                "name": "qmllint_discovery",
                "command": ["pyside6-qmllint"],
                "exit_code": None,
                "log": log_name,
                "error": message,
                "runtime_qml_warnings": [],
                "missing_platform_proof": [],
            }
        )
        _write_report(report_path, report)
        print(
            f"FAILED: qmllint_discovery ({message}); see {output / log_name}",
            file=sys.stderr,
        )
        return 1

    commands = verification_commands(
        output,
        qmllint_executable=qmllint_executable,
    )
    raw_runtime_outputs: dict[str, str] = {}
    for index, (name, command, overrides) in enumerate(commands, start=1):
        environment = os.environ.copy()
        environment.update(overrides)
        completed = subprocess.run(
            list(command),
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = completed.stdout + "\n" + completed.stderr
        if name in RUNTIME_DIAGNOSTIC_STEPS:
            raw_runtime_outputs[name] = combined_output
        runtime_warnings = (
            detect_qml_runtime_warnings(combined_output)
            if name in RUNTIME_DIAGNOSTIC_STEPS
            else []
        )
        missing_platform_proof = (
            detect_missing_interactive_windows_proof(combined_output)
            if name == "unit_and_interface_tests"
            else []
        )
        display_command = [sanitize_evidence_text(item, output) for item in command]
        safe_stdout = sanitize_evidence_text(completed.stdout, output)
        safe_stderr = sanitize_evidence_text(completed.stderr, output)
        runtime_warnings = [
            sanitize_evidence_text(item, output) for item in runtime_warnings
        ]
        missing_platform_proof = [
            sanitize_evidence_text(item, output) for item in missing_platform_proof
        ]
        log_name = f"{index:02d}-{name}.log"
        (output / log_name).write_text(
            "$ " + subprocess.list2cmdline(display_command) + "\n\n"
            + safe_stdout
            + ("\n[stderr]\n" + safe_stderr if safe_stderr else ""),
            encoding="utf-8",
        )
        step = {
            "name": name,
            "command": display_command,
            "exit_code": completed.returncode,
            "log": log_name,
            "runtime_qml_warnings": runtime_warnings,
            "missing_platform_proof": missing_platform_proof,
        }
        report["steps"].append(step)
        if completed.returncode != 0 or runtime_warnings or missing_platform_proof:
            report["status"] = "failed"
            report["automated_status"] = "failed"
            report["failed_step"] = name
            _write_report(report_path, report)
            reason = (
                f"{len(runtime_warnings)} runtime QML warning(s)"
                if runtime_warnings
                else "interactive Windows focus/caret proof was skipped"
                if missing_platform_proof
                else f"exit code {completed.returncode}"
            )
            print(
                f"FAILED: {name} ({reason}); see {output / log_name}",
                file=sys.stderr,
            )
            return completed.returncode or 1
        print(f"PASS: {name}")
        _write_report(report_path, report)

    raw_findings = scan_raw_runtime_outputs(raw_runtime_outputs)
    raw_scan_index = len(commands) + 1
    raw_scan_log = f"{raw_scan_index:02d}-raw_runtime_log_marker_scan.log"
    raw_scan_text = (
        "Scanned unredacted in-memory stdout/stderr from: "
        + ", ".join(sorted(raw_runtime_outputs))
        + "\nForbidden QML/renderer diagnostic markers: "
        + str(sum(len(items) for items in raw_findings.values()))
        + "\n"
    )
    (output / raw_scan_log).write_text(raw_scan_text, encoding="utf-8")
    safe_raw_findings = {
        name: [sanitize_evidence_text(item, output) for item in items]
        for name, items in raw_findings.items()
    }
    report["steps"].append(
        {
            "name": "raw_runtime_log_marker_scan",
            "command": ["internal", "scan unredacted runtime stdout/stderr"],
            "exit_code": 1 if raw_findings else 0,
            "log": raw_scan_log,
            "scanned_steps": sorted(raw_runtime_outputs),
            "runtime_qml_warnings": safe_raw_findings,
            "missing_platform_proof": [],
        }
    )
    if raw_findings:
        report["status"] = "failed"
        report["automated_status"] = "failed"
        report["failed_step"] = "raw_runtime_log_marker_scan"
        _write_report(report_path, report)
        print(
            "FAILED: raw_runtime_log_marker_scan "
            f"({sum(len(items) for items in raw_findings.values())} marker(s)); "
            f"see {output / raw_scan_log}",
            file=sys.stderr,
        )
        return 1
    print("PASS: raw_runtime_log_marker_scan")
    _write_report(report_path, report)

    report["status"] = "passed"
    report["automated_status"] = "passed"
    _write_report(report_path, report)
    print(
        "Automated verification passed; manual platform gates remain required. "
        f"Evidence: {output}"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "ui-verification",
        help="directory for logs, JSON reports, and platform screenshots",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(argv)
    return run_verification(arguments.output)


if __name__ == "__main__":
    raise SystemExit(main())
