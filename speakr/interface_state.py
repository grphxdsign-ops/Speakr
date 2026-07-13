"""Thread-safe, privacy-sanitized presentation state for Speakr's UIs.

The dict returned by :class:`InterfaceState` is intentionally much smaller
than the application's working state.  Audio, transcript text, selected
text, screen context, clipboard contents, and foreground-window metadata do
not belong here.  This object is safe to mirror into QML or the loopback
recovery panel.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
from collections.abc import Callable, Mapping
from typing import Any

log = logging.getLogger("speakr.interface_state")


AVAILABILITY = frozenset({"starting", "ready", "disabled", "needs_attention"})
CAPTURE = frozenset({"idle", "listening"})
PIPELINE = frozenset(
    {
        "idle",
        "queued",
        "waiting_model",
        "transcribing",
        "formatting",
        "injecting",
        "success",
        "error",
    }
)
MODES = frozenset({"dictation", "edit"})
MIC_LEVELS = frozenset({"silent", "low", "good", "high"})
DEVICES = frozenset({"cpu", "cuda", "unknown"})
CLEANUP_PATHS = frozenset({"ollama", "rules"})

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_SAFE_TEXT = 240

_DEFAULTS: dict[str, Any] = {
    "availability": "starting",
    "capture": "idle",
    "pipeline": "idle",
    "mode": "dictation",
    "capture_mode": "dictation",
    "pipeline_mode": "dictation",
    "job_id": 0,
    "capture_job_id": 0,
    "pipeline_job_id": 0,
    "queue_depth": 0,
    "settings_version": 0,
    "mic_level_band": "silent",
    "status_code": "starting",
    "detail_code": None,
    "latest_outcome_code": "none",
    "enabled": True,
    "hotkey": "",
    "model": "auto",
    "device": "unknown",
    "compute_type": "unknown",
    "cleanup_path": "rules",
    "fallback_active": False,
    "active_monitor_x": 0,
    "active_monitor_y": 0,
    "active_monitor_width": 0,
    "active_monitor_height": 0,
    "last_issue": None,
}

_ENUM_FIELDS = {
    "availability": AVAILABILITY,
    "capture": CAPTURE,
    "pipeline": PIPELINE,
    "mode": MODES,
    "capture_mode": MODES,
    "pipeline_mode": MODES,
    "mic_level_band": MIC_LEVELS,
    "device": DEVICES,
    "cleanup_path": CLEANUP_PATHS,
}

_STATUS_COPY = {
    "starting": "Getting Speakr ready",
    "ready": "Ready",
    "disabled": "Dictation is off",
    "needs_attention": "Speakr needs attention",
    "listening": "Listening",
    "listening_edit": "Listening for an edit instruction",
    "edit_listening": "Listening for an edit instruction",
    "queued": "Waiting to process",
    "waiting_model": "Waiting for the speech model",
    "transcribing": "Transcribing locally",
    "formatting": "Cleaning up locally",
    "formatting_edit": "Applying your instruction locally",
    "edit_formatting": "Applying your instruction locally",
    "injecting": "Inserting text",
    "injecting_edit": "Replacing selection",
    "edit_injecting": "Replacing selection",
    "success": "Inserted",
    "success_edit": "Selection updated",
    "edit_success": "Selection updated",
    "pipeline_error": "Speakr couldn't finish that dictation. Nothing was inserted.",
    "no_speech": "Speakr didn't catch speech. Nothing was inserted.",
    "mic_recovery": "Microphone reconnected. Please try again.",
    "edit_failure": "The original selection was not changed.",
    "formatting_fallback": "Basic cleanup active",
    "gpu_fallback": "Using CPU",
    "excluded_app": "Dictation is paused for this app",
}

_PIPELINE_CODES = {
    "queued": "queued",
    "waiting_model": "waiting_model",
    "transcribing": "transcribing",
    "formatting": "formatting",
    "injecting": "injecting",
    "success": "success",
    "error": "pipeline_error",
}

_PIPELINE_PROGRESS = {
    "idle": 0,
    "queued": 0,
    "waiting_model": 0,
    "transcribing": 1,
    "formatting": 2,
    "injecting": 3,
    "success": 4,
    "error": 0,
}

_ISSUE_DEFAULTS = {
    "microphone_unavailable": (
        "Microphone access is unavailable.",
        "open_system_settings",
    ),
    "microphone_reconnected": (
        "Microphone reconnected. Please try again.",
        "start_practice",
    ),
    "permission_missing": (
        "Speakr needs microphone and input permissions.",
        "open_system_settings",
    ),
    "model_unavailable": ("The speech model is unavailable.", "retry_model"),
    "edit_unchanged": ("The original selection was not changed.", "try_again"),
    "pipeline_failed": (
        "Speakr couldn't finish that dictation. Nothing was inserted.",
        "open_log",
    ),
    "hud_focus_guard": (
        "The dictation HUD was hidden to protect keyboard focus.",
        "open_speakr",
    ),
    "setting_save_failed": (
        "That setting could not be saved. Your previous file is unchanged.",
        "open_config",
    ),
    "unknown": ("Speakr needs attention.", "dismiss"),
}

_ISSUE_STATUS_CODES = {
    "microphone_reconnected": "mic_recovery",
    "edit_unchanged": "edit_failure",
    "edit_failed": "edit_failure",
}

_ACTION_COPY = {
    "open_system_settings": "Open system settings",
    "start_practice": "Start Practice",
    "retry_model": "Retry",
    "try_again": "Try again",
    "open_log": "Open local log",
    "open_speakr": "Open Speakr",
    "open_config": "Open local config",
    "open_dictionary": "Open local dictionary",
    "choose_hotkey": "Choose another shortcut",
    "edit_vocabulary": "Edit vocabulary",
    "reload_dictionary": "Reload vocabulary",
    "dismiss": "Dismiss",
}

_LATEST_OUTCOME_COPY = {
    "none": "No dictation yet",
    "success": "Text inserted",
    "edit_success": "Selection updated",
    "no_speech": "Nothing inserted",
    "edit_failure": "Original selection unchanged",
    "pipeline_failed": "Nothing inserted",
    "mic_recovery": "Microphone reconnected; please try again",
}

# A successful insertion proves only runtime pipeline health. Persistent
# configuration, vocabulary, restart, and HUD-focus notices must survive it.
_SUCCESS_RESOLVES_ISSUES = frozenset(
    {
        "pipeline_failed",
        "edit_failed",
        "edit_unchanged",
        "model_load_failed",
        "model_unavailable",
    }
)


def _safe_text(value: Any, *, field: str, limit: int = _MAX_SAFE_TEXT) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise TypeError(f"{field} must be text")
    text = str(value).strip()
    if any(ord(char) < 32 and char not in "\t" for char in text):
        raise ValueError(f"{field} contains control characters")
    return text[:limit]


def _safe_code(value: Any, *, field: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not _CODE_RE.fullmatch(value):
        raise ValueError(f"{field} must be a stable lowercase code")
    return value


def _safe_job_id(value: Any, *, field: str) -> int | str:
    if value in (None, "", 0):
        return 0
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0:
            raise ValueError(f"{field} must not be negative")
        return value
    text = _safe_text(value, field=field, limit=96)
    # Generation IDs are identifiers, never presentation copy.
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        raise ValueError(f"{field} contains invalid characters")
    return text


class InterfaceState:
    """Small observable state store shared by the native and fallback UIs.

    Mutations are serialized under a condition lock, snapshots are detached
    copies, and subscribers are called after the lock is released.  A failed
    subscriber cannot prevent other subscribers from receiving a change.
    """

    def __init__(self, initial: Mapping[str, Any] | None = None):
        self._condition = threading.Condition(threading.RLock())
        self._state = copy.deepcopy(_DEFAULTS)
        self._version = 0
        self._subscribers: dict[int, Callable[[dict[str, Any]], None]] = {}
        self._next_subscriber_id = 1
        if initial:
            sanitized = self._sanitize_changes(dict(initial), allow_issue=True)
            if "mode" in sanitized:
                sanitized.setdefault("capture_mode", sanitized["mode"])
                sanitized.setdefault("pipeline_mode", sanitized["mode"])
            self._state.update(sanitized)
            self._normalize()
            if "status_code" not in initial:
                self._state["status_code"] = self._derived_status_code_locked()

    @property
    def version(self) -> int:
        with self._condition:
            return self._version

    def snapshot(self) -> dict[str, Any]:
        """Return a detached, derived snapshot containing approved fields only."""
        with self._condition:
            return self._snapshot_locked()

    def update(self, **changes: Any) -> dict[str, Any]:
        """Atomically apply validated fields and notify observers once.

        Unknown keys are rejected.  This is an intentional privacy fence: a
        caller cannot accidentally add ``transcript`` or ``selected_text`` to
        data mirrored by the UI.
        """
        if not changes:
            return self.snapshot()
        sanitized = self._sanitize_changes(changes, allow_issue=False)
        callbacks: list[Callable[[dict[str, Any]], None]] = []
        with self._condition:
            before = copy.deepcopy(self._state)
            if "mode" in sanitized:
                capture = sanitized.get("capture", self._state["capture"])
                pipeline = sanitized.get("pipeline", self._state["pipeline"])
                if capture == "listening":
                    sanitized.setdefault("capture_mode", sanitized["mode"])
                if pipeline != "idle":
                    sanitized.setdefault("pipeline_mode", sanitized["mode"])
            self._state.update(sanitized)

            # A successful insertion clears only issues it actually proves
            # resolved. Configuration/restart/vocabulary notices persist.
            if (
                sanitized.get("pipeline") == "success"
                and self._state["last_issue"]
                and self._state["last_issue"]["code"] in _SUCCESS_RESOLVES_ISSUES
            ):
                self._state["last_issue"] = None
                if self._state["availability"] == "needs_attention":
                    self._state["availability"] = (
                        "ready" if self._state["enabled"] else "disabled"
                    )

            self._normalize()
            if "status_code" not in sanitized and set(sanitized) & {
                "availability",
                "capture",
                "pipeline",
                "mode",
                "enabled",
            }:
                self._state["status_code"] = self._derived_status_code_locked()
            if self._state == before:
                return self._snapshot_locked()
            snapshot, callbacks = self._commit_locked()
        self._notify(callbacks, snapshot)
        return snapshot

    def latch_issue(
        self,
        code: str,
        message: str | None = None,
        action: str = "",
        detail: str = "",
        *,
        blocking: bool = True,
    ) -> dict[str, Any]:
        """Latch a recoverable issue until dismissal or a later success.

        ``detail`` is retained only when it is a stable code.  Exception text
        is accepted for controller compatibility but deliberately discarded;
        it may contain private working content or machine-specific paths.
        """
        code = _safe_code(code, field="issue code") or "unknown"
        default_message, default_action = _ISSUE_DEFAULTS.get(
            code, _ISSUE_DEFAULTS["unknown"]
        )
        safe_detail = self._sanitize_issue_detail(detail)
        issue = {
            "code": code,
            "message": _safe_text(
                message if message is not None else default_message,
                field="issue message",
            ),
            "action": _safe_text(action or default_action, field="issue action", limit=80),
            "detail": safe_detail,
            "blocking": bool(blocking),
        }
        callbacks: list[Callable[[dict[str, Any]], None]] = []
        with self._condition:
            before = copy.deepcopy(self._state)
            self._state["last_issue"] = issue
            self._state["status_code"] = _ISSUE_STATUS_CODES.get(code, "needs_attention")
            if safe_detail:
                self._state["detail_code"] = safe_detail
            outcome_code = {
                "edit_failed": "edit_failure",
                "edit_unchanged": "edit_failure",
                "pipeline_failed": "pipeline_failed",
                "microphone_reconnected": "mic_recovery",
            }.get(code)
            if outcome_code:
                self._state["latest_outcome_code"] = outcome_code
            if blocking:
                self._state["availability"] = "needs_attention"
            if self._state == before:
                return self._snapshot_locked()
            snapshot, callbacks = self._commit_locked()
        self._notify(callbacks, snapshot)
        return snapshot

    def dismiss_issue(self, code: str | None = None) -> dict[str, Any]:
        callbacks: list[Callable[[dict[str, Any]], None]] = []
        with self._condition:
            if self._state["last_issue"] is None:
                return self._snapshot_locked()
            if code is not None and self._state["last_issue"]["code"] != code:
                return self._snapshot_locked()
            self._state["last_issue"] = None
            self._state["detail_code"] = None
            if self._state["availability"] == "needs_attention":
                self._state["availability"] = (
                    "ready" if self._state["enabled"] else "disabled"
                )
            if self._state["pipeline"] == "error":
                self._state["pipeline"] = "idle"
            self._normalize()
            self._state["status_code"] = self._derived_status_code_locked()
            snapshot, callbacks = self._commit_locked()
        self._notify(callbacks, snapshot)
        return snapshot

    def retire_pipeline_job(self, job_id: int | str, expected_states) -> bool:
        """Atomically retire one unchanged pipeline presentation job.

        Timers use this compare-and-retire operation so a stale callback can
        never clear a newer dictation between a snapshot check and update.
        """
        safe_job_id = _safe_job_id(job_id, field="pipeline_job_id")
        expected = frozenset(expected_states)
        if not expected or not expected.issubset(PIPELINE):
            raise ValueError("expected_states must contain valid pipeline states")

        callbacks: list[Callable[[dict[str, Any]], None]] = []
        with self._condition:
            if (
                self._state["pipeline_job_id"] != safe_job_id
                or self._state["capture"] != "idle"
                or self._state["pipeline"] not in expected
            ):
                return False
            self._state.update(
                pipeline="idle",
                pipeline_job_id=0,
                job_id=0,
                status_code="ready" if self._state["enabled"] else "disabled",
                detail_code=None,
                pipeline_mode="dictation",
            )
            self._normalize()
            snapshot, callbacks = self._commit_locked()
        self._notify(callbacks, snapshot)
        return True

    def retire_capture_attempt(self, job_id: int | str) -> bool:
        """Atomically hide one finished microphone-attempt HUD scope."""
        safe_job_id = _safe_job_id(job_id, field="capture_job_id")
        callbacks: list[Callable[[dict[str, Any]], None]] = []
        with self._condition:
            if (
                self._state["capture_job_id"] != safe_job_id
                or self._state["capture"] != "idle"
            ):
                return False
            self._state["capture_job_id"] = 0
            if self._state["pipeline"] == "idle":
                self._state["job_id"] = 0
            self._normalize()
            snapshot, callbacks = self._commit_locked()
        self._notify(callbacks, snapshot)
        return True

    # The shorter name is useful to UI/controller call sites and is part of
    # the public contract retained for compatibility.
    dismiss = dismiss_issue

    def subscribe(
        self,
        callback: Callable[[dict[str, Any]], None],
        *,
        replay: bool = False,
    ) -> Callable[[], None]:
        """Register a callback and return an idempotent unsubscribe closure."""
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._condition:
            token = self._next_subscriber_id
            self._next_subscriber_id += 1
            self._subscribers[token] = callback
            snapshot = self._snapshot_locked() if replay else None

        if snapshot is not None:
            self._notify([callback], snapshot)

        def unsubscribe() -> None:
            with self._condition:
                self._subscribers.pop(token, None)

        return unsubscribe

    def wait(self, after_version: int, timeout: float | None = None) -> dict[str, Any] | None:
        """Wait for a snapshot newer than ``after_version``.

        Returns ``None`` on timeout.  Spurious condition wakeups are handled
        internally, and a negative timeout behaves like an immediate poll.
        """
        if isinstance(after_version, bool) or not isinstance(after_version, int):
            raise TypeError("after_version must be an integer")
        if timeout is not None:
            timeout = max(0.0, float(timeout))
        with self._condition:
            if self._version <= after_version:
                changed = self._condition.wait_for(
                    lambda: self._version > after_version,
                    timeout=timeout,
                )
                if not changed:
                    return None
            return self._snapshot_locked()

    def _sanitize_changes(
        self, changes: Mapping[str, Any], *, allow_issue: bool
    ) -> dict[str, Any]:
        allowed = set(_DEFAULTS)
        unknown = set(changes) - allowed
        if unknown:
            names = ", ".join(sorted(unknown))
            raise KeyError(f"InterfaceState does not expose: {names}")
        if "last_issue" in changes and not allow_issue:
            raise KeyError("use latch_issue() or dismiss_issue() to change last_issue")

        out: dict[str, Any] = {}
        for key, value in changes.items():
            if key in _ENUM_FIELDS:
                if value not in _ENUM_FIELDS[key]:
                    raise ValueError(f"invalid {key}: {value!r}")
                out[key] = value
            elif key in {"job_id", "capture_job_id", "pipeline_job_id"}:
                out[key] = _safe_job_id(value, field=key)
            elif key in {"queue_depth", "settings_version"}:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{key} must be a non-negative integer")
                out[key] = min(value, 100_000 if key == "queue_depth" else 2_147_483_647)
            elif key == "enabled":
                if not isinstance(value, bool):
                    raise TypeError("enabled must be a boolean")
                out[key] = value
            elif key == "fallback_active":
                if not isinstance(value, bool):
                    raise TypeError("fallback_active must be a boolean")
                out[key] = value
            elif key in {"status_code", "latest_outcome_code"}:
                out[key] = _safe_code(value, field=key)
            elif key == "detail_code":
                out[key] = _safe_code(value, field=key, allow_none=True)
            elif key in {"hotkey", "model", "compute_type"}:
                out[key] = _safe_text(value, field=key, limit=128)
            elif key.startswith("active_monitor_"):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"{key} must be an integer")
                out[key] = max(-1_000_000, min(1_000_000, value))
            elif key == "last_issue":
                if value is not None:
                    if not isinstance(value, Mapping):
                        raise TypeError("last_issue must be a mapping or None")
                    issue_code = _safe_code(value.get("code", "unknown"), field="issue code")
                    defaults = _ISSUE_DEFAULTS.get(issue_code, _ISSUE_DEFAULTS["unknown"])
                    value = {
                        "code": issue_code,
                        "message": _safe_text(
                            value.get("message", defaults[0]), field="issue message"
                        ),
                        "action": _safe_text(
                            value.get("action", defaults[1]),
                            field="issue action",
                            limit=80,
                        ),
                        "detail": self._sanitize_issue_detail(value.get("detail")),
                        "blocking": bool(value.get("blocking", True)),
                    }
                out[key] = value
        return out

    def _normalize(self) -> None:
        if not self._state["enabled"]:
            self._state["availability"] = "disabled"
            self._state["capture"] = "idle"
            self._state["capture_job_id"] = 0
        elif self._state["availability"] == "disabled":
            self._state["availability"] = "ready"

        if self._state["capture"] == "listening":
            self._state["mode"] = self._state["capture_mode"]
        elif self._state["pipeline"] != "idle":
            self._state["mode"] = self._state["pipeline_mode"]

        # Maintain a convenient presentation generation while preserving the
        # independent IDs needed for overlapping capture and processing.
        if self._state["capture"] == "listening" and self._state["capture_job_id"]:
            self._state["job_id"] = self._state["capture_job_id"]
        elif self._state["pipeline"] != "idle" and self._state["pipeline_job_id"]:
            self._state["job_id"] = self._state["pipeline_job_id"]

    def _derived_status_code_locked(self) -> str:
        issue = self._state["last_issue"]
        if self._state["availability"] == "needs_attention" and issue:
            return _ISSUE_STATUS_CODES.get(issue["code"], "needs_attention")
        if self._state["capture"] == "listening":
            return "edit_listening" if self._state["capture_mode"] == "edit" else "listening"
        pipeline = self._state["pipeline"]
        if pipeline != "idle":
            code = _PIPELINE_CODES[pipeline]
            if self._state["pipeline_mode"] == "edit" and pipeline in {
                "formatting",
                "injecting",
                "success",
            }:
                code = "edit_" + code
            return code
        if not self._state["enabled"] or self._state["availability"] == "disabled":
            return "disabled"
        if self._state["availability"] == "starting":
            return "starting"
        # Preserve a short-lived outcome/detail code only while otherwise
        # idle.  Callers clear it by publishing the next structural state.
        status = self._state.get("status_code")
        if status in {"no_speech", "mic_recovery", "edit_failure"}:
            return status
        return "ready"

    def _snapshot_locked(self) -> dict[str, Any]:
        state = copy.deepcopy(self._state)
        issue = state["last_issue"]
        primary, secondary = self._presentation_copy_locked()
        state.update(
            {
                "version": self._version,
                "primary": primary,
                "secondary": secondary,
                "primary_text": primary,
                "secondary_text": secondary,
                "status": primary,
                "issue": issue["message"] if issue else "",
                "issue_action": issue["action"] if issue else "",
                "progress_stage": _PIPELINE_PROGRESS[state["pipeline"]],
                "latest_outcome": _LATEST_OUTCOME_COPY.get(
                    state["latest_outcome_code"], "Ready for dictation"
                ),
            }
        )
        return state

    def _presentation_copy_locked(self) -> tuple[str, str]:
        state = self._state
        issue = state["last_issue"]
        if state["availability"] == "needs_attention" and issue:
            return issue["message"], _ACTION_COPY.get(issue["action"], issue["action"])

        if state["capture"] == "listening":
            primary_code = "edit_listening" if state["capture_mode"] == "edit" else "listening"
            secondary = ""
            if state["pipeline"] != "idle":
                pipeline_code = self._pipeline_copy_code_locked()
                secondary = f"Previous dictation: {_STATUS_COPY[pipeline_code]}"
            elif issue:
                secondary = issue["message"]
            return _STATUS_COPY[primary_code], secondary

        if state["pipeline"] != "idle":
            primary = _STATUS_COPY[self._pipeline_copy_code_locked()]
            secondary = issue["message"] if issue and not issue["blocking"] else ""
            return primary, secondary

        if not state["enabled"] or state["availability"] == "disabled":
            return _STATUS_COPY["disabled"], issue["message"] if issue else ""
        if state["availability"] == "starting":
            return _STATUS_COPY["starting"], ""

        status = state["status_code"]
        primary = _STATUS_COPY.get(status, _STATUS_COPY["ready"])
        if issue and not issue.get("blocking", True):
            return primary, issue["message"]
        if status == "ready":
            detail = _STATUS_COPY.get(state["detail_code"] or "", "")
            if not detail and state["model"] and state["device"] != "unknown":
                detail = f"{state['model']} on {state['device'].upper()}"
            return primary, detail
        return primary, ""

    def _pipeline_copy_code_locked(self) -> str:
        pipeline = self._state["pipeline"]
        code = _PIPELINE_CODES[pipeline]
        if self._state["pipeline_mode"] == "edit" and pipeline in {
            "formatting",
            "injecting",
            "success",
        }:
            code = "edit_" + code
        return code

    @staticmethod
    def _sanitize_issue_detail(value: Any) -> str | None:
        """Keep only stable diagnostic codes; never mirror exception text."""
        if not value or not isinstance(value, str):
            return None
        return value if _CODE_RE.fullmatch(value) else None

    def _commit_locked(
        self,
    ) -> tuple[dict[str, Any], list[Callable[[dict[str, Any]], None]]]:
        self._version += 1
        snapshot = self._snapshot_locked()
        callbacks = list(self._subscribers.values())
        self._condition.notify_all()
        return snapshot, callbacks

    @staticmethod
    def _notify(
        callbacks: list[Callable[[dict[str, Any]], None]], snapshot: dict[str, Any]
    ) -> None:
        for callback in callbacks:
            try:
                callback(copy.deepcopy(snapshot))
            except Exception:
                log.exception("InterfaceState subscriber failed")


__all__ = [
    "AVAILABILITY",
    "CAPTURE",
    "CLEANUP_PATHS",
    "DEVICES",
    "InterfaceState",
    "MIC_LEVELS",
    "MODES",
    "PIPELINE",
]
