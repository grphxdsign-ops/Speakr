"""Speakr orchestrator: hotkey -> record -> transcribe -> format -> inject.

The core pipeline remains UI-toolkit agnostic. A sanitized InterfaceState is
the single source of truth for the native Qt window, HUD, tray, and emergency
browser fallback. Audio and transcript content never enter that state.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from speakr import config as cfg_mod
from speakr.audio import AudioRecorder
from speakr.config import Config, setup_logging
from speakr.context import get_active_app, get_screen_context, get_selected_text
from speakr.dictionary import Dictionary
from speakr.formatter import (
    Formatter,
    _local_ollama_url,
    apply_voice_commands,
    rule_based_clean,
)
from speakr.hotkey import resolve_hotkey_mode
from speakr.injector import inject, read_selection_via_clipboard
from speakr.inputs import HotkeyListener, capture_next_key
from speakr.interface_state import InterfaceState
from speakr.learning import VocabLearner, extract_notable_tokens
from speakr.renderer_handoff import (
    ADDRESS_ENV as _SOFTWARE_RELAUNCH_ADDRESS_ENV,
    GUARD_ENV as _SOFTWARE_RELAUNCH_GUARD_ENV,
    NONCE_ENV as _SOFTWARE_RELAUNCH_NONCE_ENV,
    PARENT_ENV as _SOFTWARE_RELAUNCH_PARENT_ENV,
    TOKEN_ENV as _SOFTWARE_RELAUNCH_AUTH_ENV,
    RendererHandoffChild as _RendererHandoffChild,
    RendererHandoffParent as _RendererHandoffParent,
    is_guarded as _software_relaunch_is_guarded,
)
from speakr.streaming import DictationSession
from speakr.transcriber import Transcriber
from speakr.tray import Tray
from speakr.webui import WebUI


_SINGLE_INSTANCE_HANDOFF_SECONDS = 10.0
_SINGLE_INSTANCE_POLL_SECONDS = 0.05
_SINGLE_INSTANCE_MUTEX_NAME = "SpeakrSingleInstance"
_LAUNCH_GATE_MUTEX_NAME = "SpeakrLaunchGate"


def _native_relaunch_command() -> list[str]:
    """Build a fixed, shell-free command for source and frozen releases."""

    executable = str(sys.executable or "").strip()
    if not executable:
        raise OSError("the Python executable path is unavailable")
    if bool(getattr(sys, "frozen", False)):
        return [executable]
    return [executable, "-m", "speakr"]


def _native_relaunch_working_directory() -> Path:
    if bool(getattr(sys, "frozen", False)):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _relaunch_with_software_renderer(logger) -> bool:
    """Return whether a renderer child owns the outcome and blocks recovery."""

    if _software_relaunch_is_guarded():
        return False
    try:
        gate_acquired = _acquire_launch_gate(
            wait_seconds=_SINGLE_INSTANCE_HANDOFF_SECONDS
        )
    except OSError as exc:
        logger.warning("Could not create the renderer handoff launch gate: %s", exc)
        return False
    if not gate_acquired:
        logger.warning("Could not reserve the renderer handoff launch gate")
        return False
    handoff = None
    child = None
    released_instance = False
    child_ready = False
    child_unresolved = False
    reacquired = False
    environment = os.environ.copy()
    environment["SPEAKR_QT_SOFTWARE"] = "1"
    environment[_SOFTWARE_RELAUNCH_GUARD_ENV] = "1"
    environment[_SOFTWARE_RELAUNCH_PARENT_ENV] = str(os.getpid())
    try:
        handoff = _RendererHandoffParent()
        environment.update(handoff.environment())
        child = subprocess.Popen(
            _native_relaunch_command(),
            cwd=str(_native_relaunch_working_directory()),
            env=environment,
            close_fds=True,
        )
        if handoff.wait_for_ready(
            child,
            timeout=_SINGLE_INSTANCE_HANDOFF_SECONDS,
            release_primary=_release_single_instance,
            claim_is_exclusive=_renderer_child_holds_primary,
        ):
            child_ready = True
            logger.warning(
                "Relaunched the native interface with Qt software rendering"
            )
            return True
        logger.warning(
            "Qt software-renderer child did not acknowledge a visible frontend"
        )
    except (OSError, ValueError) as exc:
        logger.warning("Could not relaunch with Qt software rendering: %s", exc)
    finally:
        released_instance = bool(
            handoff is not None and handoff.primary_released is True
        )
        if child is not None and not child_ready:
            child_stopped = handoff.stop_child(child)
            child_unresolved = released_instance and not child_stopped
            if child_unresolved:
                logger.error(
                    "Renderer runtime could not be proven stopped; "
                    "suppressing a second frontend"
                )
        if released_instance and not child_ready and not child_unresolved:
            try:
                reacquired = _acquire_single_instance(
                    wait_seconds=_SINGLE_INSTANCE_HANDOFF_SECONDS
                )
            except OSError as exc:
                reacquired = False
                logger.error(
                    "Could not recreate the primary lock after renderer handoff: %s",
                    exc,
                )
            if not reacquired:
                # The launch gate still gives this parent exclusive startup
                # ownership. Keep it for the visible recovery lifetime rather
                # than allowing a third launcher to become a second primary.
                logger.error(
                    "Could not reacquire the primary lock after renderer handoff; "
                    "retaining the launch gate for recovery"
                )
        if child_ready:
            _release_launch_gate()
        # Otherwise recovery startup keeps the gate until the main thread has
        # started the local browser surface. Process exit is the final safety
        # release if recovery cannot be constructed.
        if handoff is not None:
            handoff.close()
    return child_unresolved


def _open_path(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        os.startfile(path)


def _is_app_excluded(exe: str, excluded_apps) -> bool:
    """Return whether the foreground application is excluded from dictation."""
    if not excluded_apps or not exe:
        return False
    return exe.lower() in {str(item).lower() for item in excluded_apps}


def _level_band(level: float) -> str:
    if level < 0.015:
        return "silent"
    if level < 0.16:
        return "low"
    if level < 0.72:
        return "good"
    return "high"


def _migrate_existing_user_interface(config, logger, *, config_existed, had_ui_settings):
    """Keep existing users out of onboarding even if their config is read-only."""
    if not config_existed or had_ui_settings:
        return
    try:
        config.set("ui", "onboarding_complete", value=True)
    except OSError as exc:
        logger.warning(
            "Could not persist the existing-user interface migration; "
            "continuing with the in-memory setting: %s",
            exc,
        )
        config.data.setdefault("ui", {})["onboarding_complete"] = True


def _open_running_legacy_panel() -> bool:
    """Open a verified loopback panel owned by a running pre-native release."""
    try:
        url = cfg_mod.PANEL_URL_PATH.read_text(encoding="utf-8-sig").strip()
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            return False
        port = parsed.port
        if port is None:
            return False
        with socket.create_connection((parsed.hostname, port), timeout=0.25):
            pass
        return bool(webbrowser.open(url))
    except (OSError, UnicodeError, ValueError):
        return False


class SpeakrApp:
    def __init__(self):
        self.log = setup_logging()

        config_existed = cfg_mod.CONFIG_PATH.exists()
        had_ui_settings = False
        if config_existed:
            try:
                prior = json.loads(cfg_mod.CONFIG_PATH.read_text(encoding="utf-8-sig"))
                had_ui_settings = isinstance(prior.get("ui"), dict)
            except (OSError, json.JSONDecodeError):
                pass

        self.config = Config()
        # Existing users should not be forced through first-run onboarding.
        # New installs retain the default false value and start at Privacy.
        _migrate_existing_user_interface(
            self.config,
            self.log,
            config_existed=config_existed,
            had_ui_settings=had_ui_settings,
        )
        self.first_run = not config_existed

        self.dictionary = Dictionary(cfg_mod.DICTIONARY_PATH)
        self.recorder = AudioRecorder(
            sample_rate=self.config.get("sample_rate"),
            input_device=self.config.get("input_device"),
            keep_stream_open=self.config.get("keep_mic_stream_open"),
            preroll_seconds=self.config.get("preroll_seconds", default=0.4),
        )
        self.learner = VocabLearner(self.config, cfg_mod.LEARNED_PATH)
        self.transcriber = Transcriber(self.config, self.dictionary, self.learner)
        self.formatter = Formatter(self.config)

        self.enabled = True
        self.interface_state = InterfaceState({
            "availability": "starting",
            "capture": "idle",
            "pipeline": "waiting_model",
            "mode": "dictation",
            "capture_mode": "dictation",
            "pipeline_mode": "dictation",
            "capture_job_id": 0,
            "pipeline_job_id": 0,
            "queue_depth": 0,
            "mic_level_band": "silent",
            "status_code": "starting",
            "detail_code": None,
            "enabled": True,
            "hotkey": self.config.get("hotkey"),
            "model": self.config.get("model"),
            "device": "unknown",
            "compute_type": "unknown",
            "cleanup_path": "rules",
            "fallback_active": False,
        })
        self.formatter.set_status_callback(self._on_formatter_status)

        # Legacy objects are constructed but never run in the normal Qt path.
        # This keeps fallback completely independent from Qt imports.
        self.tray = Tray(self)
        self.webui = WebUI(self)
        self._fallback_active = False
        self._qt_frontend = None
        self._renderer_handoff = None

        self._recording = False
        self._record_started_at = 0.0
        self._queue: queue.Queue = queue.Queue()
        self._listener = None
        self._session = None
        self._capture_job_id = 0
        self._job_counter = 0
        self._job_lock = threading.Lock()

        self._hotkey_capture_lock = threading.Lock()
        self._hotkey_cancel = None
        self._capturing_hotkey = False
        self._pending_hotkey = None

        self._practice_lock = threading.RLock()
        self._practice_generation = 0
        self._practice_recording = False
        self._practice_audio = None
        self._practice = self._empty_practice()
        self._practice_subscribers = []
        self._settings_subscribers = []

        self._core_started = False
        self._shutting_down = False

    # ----- lifecycle -------------------------------------------------------

    def start(self):
        self.log.info("Speakr starting (hotkey=%r)", self.config.get("hotkey"))

        if sys.version_info < (3, 10):
            self.log.info("Python below 3.10 uses the local recovery interface")
            self._start_legacy_interface()
            return

        try:
            from speakr.qt_ui import _prefer_software_renderer, run_native_ui
        except (ImportError, ModuleNotFoundError) as exc:
            self.log.warning("Native UI unavailable (%s); using recovery interface", exc)
        else:
            native_error = None
            software_requested = _prefer_software_renderer()
            try:
                result = run_native_ui(self)
                if result is not False:
                    return
                native_error = RuntimeError("the native interface exited before starting")
            except Exception as exc:
                native_error = exc

            can_relaunch = (
                native_error is not None
                and bool(getattr(native_error, "renderer_retryable", False))
                and not isinstance(native_error, (ImportError, ModuleNotFoundError))
                and not software_requested
                and not _software_relaunch_is_guarded()
                and not self._core_started
                and not self._fallback_active
                and self._qt_frontend is None
            )
            if can_relaunch and _relaunch_with_software_renderer(self.log):
                return

            if native_error is not None:
                if native_error.__class__.__name__ != "QtUnavailable":
                    self.log.error(
                        "Native UI failed; using recovery interface: %s", native_error
                    )
                else:
                    self.log.warning(
                        "Native UI unavailable (%s); using recovery interface", native_error
                    )

        handoff = self._renderer_handoff
        if handoff is not None and handoff.attempted:
            self.log.error("Renderer handoff was rejected after frontend preparation")
            return
        self._start_legacy_interface()

    def _frontend_committed(self, frontend: str) -> bool:
        """Acknowledge only after native or recovery UI is visibly committed."""

        handoff = self._renderer_handoff
        if handoff is None:
            return True
        accepted = handoff.prepare(
            frontend,
            timeout=_SINGLE_INSTANCE_HANDOFF_SECONDS,
            acquire_primary=_acquire_single_instance,
            release_primary=_release_single_instance,
        )
        if accepted:
            self._renderer_handoff = None
        return accepted

    def _start_core(self):
        if self._core_started or self._shutting_down:
            return
        self._core_started = True

        threading.Thread(target=self._load_model, name="model-loader", daemon=True).start()
        threading.Thread(target=self._prepare_formatter, name="ollama-prepare", daemon=True).start()
        try:
            self.recorder.start()
        except Exception as exc:
            self.log.error("Could not open microphone: %s", exc)
            self.interface_state.latch_issue(
                "microphone_unavailable",
                "Microphone access is needed.",
                "open_system_settings",
                str(exc),
            )
            self._legacy_state("error", "microphone unavailable")
        self._register_hotkey()
        self._notify_settings()
        threading.Thread(target=self._worker, name="pipeline", daemon=True).start()
        threading.Thread(target=self._watch_show_requests, name="ui-wake", daemon=True).start()
        threading.Thread(target=self._watch_session_lock, name="privacy-lock", daemon=True).start()

    def _start_legacy_interface(self):
        self._fallback_active = True
        self.interface_state.update(fallback_active=True)
        self.webui.start()
        self.open_panel()
        # A failed handoff can deliberately retain the launch gate until
        # recovery exists. Release it here on the same main thread that
        # acquired the Win32 mutex only when the primary lock also proves
        # ownership. If primary reacquisition failed, the gate remains this
        # recovery process's sole exclusivity proof until exit.
        if _instance_lock is not None:
            _release_launch_gate()

        def visible_tray_ready(icon):
            try:
                icon.visible = True
                if not self._frontend_committed("legacy"):
                    raise RuntimeError(
                        "the renderer handoff parent did not accept recovery readiness"
                    )
                self._start_core()
            except Exception as exc:
                self.log.error("Could not commit the recovery interface: %s", exc)
                try:
                    icon.visible = False
                except Exception:
                    pass
                self.webui.stop()
                try:
                    icon.stop()
                except Exception:
                    pass

        self.tray.run(setup=visible_tray_ready)

    def _load_model(self):
        self.interface_state.dismiss_issue("model_load_failed")
        self.interface_state.dismiss_issue("model_unavailable")
        self.interface_state.update(
            availability="starting", pipeline="waiting_model", status_code="waiting_model"
        )
        self._legacy_state("loading", "preparing local speech model")
        try:
            self.transcriber.load()
        except Exception as exc:
            self.log.exception("Speech model failed to load: %s", exc)
            self.interface_state.update(availability="needs_attention", pipeline="error")
            self.interface_state.latch_issue(
                "model_load_failed",
                "The local speech model could not be prepared.",
                "retry_model",
                str(exc),
            )
            self._legacy_state("error", "speech model failed")
            return

        if self._shutting_down:
            return
        self.interface_state.dismiss_issue("model_load_failed")
        remaining_issue = self.interface_state.snapshot().get("last_issue")
        availability = (
            "needs_attention"
            if remaining_issue and remaining_issue.get("blocking", True)
            else ("ready" if self.enabled else "disabled")
        )
        model_state = dict(
            availability=availability,
            pipeline="idle",
            model=self.transcriber.model_in_use or self.config.get("model"),
            device=self.transcriber.device_in_use or "unknown",
            compute_type=getattr(self.transcriber, "compute_type_in_use", None) or "unknown",
        )
        if (
            self.config.get("device") == "cuda"
            and self.transcriber.device_in_use == "cpu"
        ):
            model_state.update(status_code="gpu_fallback", detail_code="gpu_fallback")
        else:
            model_state["detail_code"] = None
        self.interface_state.update(**model_state)
        self._legacy_state(
            "idle" if self.enabled else "disabled",
            f"{self.transcriber.model_in_use} on {self.transcriber.device_in_use}",
        )
        self._notify_settings()

    def _prepare_formatter(self):
        try:
            formatting = self.config.get("formatting", default={}) or {}
            if formatting.get("enabled", True) and formatting.get("use_ollama", True):
                self.formatter.ensure_ollama()
        finally:
            self.interface_state.update(cleanup_path=self._current_cleanup_path())

    def _current_cleanup_path(self):
        formatting = self.config.get("formatting", default={}) or {}
        return (
            "ollama"
            if formatting.get("enabled", True)
            and formatting.get("use_ollama", True)
            and getattr(self.formatter, "_ollama_ok", False) is True
            else "rules"
        )

    def _on_formatter_status(self, _available):
        if getattr(self, "_shutting_down", False):
            return
        self.interface_state.update(cleanup_path=self._current_cleanup_path())

    def _watch_show_requests(self):
        last_seen = 0
        while not self._shutting_down:
            try:
                stamp = cfg_mod.SHOW_REQUEST_PATH.stat().st_mtime_ns
            except OSError:
                stamp = 0
            if stamp and stamp != last_seen:
                last_seen = stamp
                self.show_main_window()
            time.sleep(0.35)

    @staticmethod
    def _session_is_locked():
        """Best-effort local OS lock detection for transient Practice data."""
        try:
            if sys.platform == "win32":
                import ctypes

                user32 = ctypes.windll.user32
                user32.OpenInputDesktop.restype = ctypes.c_void_p
                user32.CloseDesktop.argtypes = [ctypes.c_void_p]
                desktop = user32.OpenInputDesktop(0, False, 0x0100)
                if not desktop:
                    return True
                user32.CloseDesktop(desktop)
                return False
            if sys.platform == "darwin":
                import Quartz

                session = Quartz.CGSessionCopyCurrentDictionary() or {}
                return bool(session.get("CGSSessionScreenIsLocked", False))
        except Exception:
            return False
        return False

    def _watch_session_lock(self):
        was_locked = False
        while not self._shutting_down:
            locked = self._session_is_locked()
            if locked and not was_locked:
                snapshot = self.practice_snapshot()
                if snapshot.get("active") or snapshot.get("processing") or snapshot.get("hasResult"):
                    self.clear_practice()
            was_locked = locked
            time.sleep(1.0)

    def show_main_window(self):
        frontend = self._qt_frontend
        if frontend is not None and hasattr(frontend, "show_main"):
            frontend.show_main()
        elif self._fallback_active:
            self.open_browser_fallback()

    def quit(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self.log.info("Speakr shutting down")
        self.clear_practice()
        self.cancel_hotkey_capture()
        self.webui.stop()
        self._stop_hotkey_listener()
        self.recorder.shutdown()
        self._queue.put(None)
        try:
            self.tray.stop()
        except Exception:
            pass
        handoff, self._renderer_handoff = self._renderer_handoff, None
        if handoff is not None:
            handoff.close()
        _release_launch_gate()
        frontend = self._qt_frontend
        if frontend is not None and hasattr(frontend, "request_quit"):
            frontend.request_quit()
        try:
            cfg_mod.SHOW_REQUEST_PATH.unlink()
        except OSError:
            pass

    # ----- single source of visible state ---------------------------------

    def _legacy_state(self, state: str, detail: str = ""):
        try:
            self.tray.set_state(state, detail)
        except Exception:
            pass

    def _next_job_id(self) -> int:
        with self._job_lock:
            self._job_counter += 1
            return self._job_counter

    def _pipeline_busy(self) -> bool:
        phase = self.interface_state.snapshot().get("pipeline", "idle")
        return phase not in ("idle", "success", "error")

    # ----- hotkey ----------------------------------------------------------

    def _register_hotkey(self):
        if self._shutting_down:
            return
        try:
            self._listener = HotkeyListener(
                self.config.get("hotkey"),
                self.config.get("toggle_mode"),
                on_press=self._hotkey_down,
                on_release=self._hotkey_up,
                on_toggle=self._toggle_recording,
            )
            self._listener.start()
            self.interface_state.dismiss_issue("hotkey_unavailable")
        except Exception as exc:
            self._listener = None
            self.log.exception("Could not register hotkey: %s", exc)
            self.interface_state.latch_issue(
                "hotkey_unavailable",
                "That shortcut is not available.",
                "choose_hotkey",
                str(exc),
            )

    def _stop_hotkey_listener(self):
        listener, self._listener = self._listener, None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass

    def _restart_hotkey_listener(self):
        self._stop_hotkey_listener()
        self._register_hotkey()

    @property
    def capturing_hotkey(self) -> bool:
        return self._capturing_hotkey

    @property
    def pending_hotkey(self):
        return self._pending_hotkey

    def begin_hotkey_capture(self, callback=None):
        if self._capturing_hotkey or self._recording or self._pipeline_busy():
            return False
        self._capturing_hotkey = True
        self._pending_hotkey = None
        self._hotkey_cancel = threading.Event()
        self._stop_hotkey_listener()
        self._notify_settings()

        def run():
            candidate = None
            try:
                candidate = capture_next_key(None, cancel_event=self._hotkey_cancel)
                if candidate in ("esc", "escape"):
                    candidate = None
                if not self._hotkey_cancel.is_set():
                    self._pending_hotkey = candidate
            except Exception as exc:
                self.interface_state.latch_issue(
                    "hotkey_capture_failed",
                    "Speakr could not listen for a shortcut.",
                    "choose_hotkey",
                    str(exc),
                )
            finally:
                self._capturing_hotkey = False
                self._register_hotkey()
                self._notify_settings()
                if callback is not None:
                    callback(self._pending_hotkey)

        threading.Thread(target=run, name="hotkey-capture", daemon=True).start()
        return True

    def cancel_hotkey_capture(self):
        if self._hotkey_cancel is not None:
            self._hotkey_cancel.set()
        self._pending_hotkey = None
        self._notify_settings()

    def confirm_hotkey(self, candidate=None):
        candidate = candidate or self._pending_hotkey
        if not candidate:
            return False
        try:
            self.config.set("hotkey", value=str(candidate))
        except OSError as exc:
            self.interface_state.latch_issue(
                "setting_save_failed",
                "The shortcut could not be saved. Your previous shortcut is still active.",
                "open_config",
                str(exc),
            )
            return False
        self.interface_state.dismiss_issue("setting_save_failed")
        self._pending_hotkey = None
        self.interface_state.update(hotkey=str(candidate), status_code="ready")
        self._restart_hotkey_listener()
        self._notify_settings()
        self.log.info("Hotkey changed to %r", candidate)
        return True

    def capture_hotkey(self, timeout=None):
        """Synchronous compatibility path used by the recovery browser."""
        if not self._hotkey_capture_lock.acquire(blocking=False):
            return None
        self._stop_hotkey_listener()
        try:
            name = capture_next_key(timeout)
            if name in (None, "esc", "escape"):
                return None
            self.config.set("hotkey", value=name)
            self.interface_state.update(hotkey=name)
            self._notify_settings()
            return name
        finally:
            self._register_hotkey()
            self._hotkey_capture_lock.release()

    def _hotkey_down(self):
        if not self._recording:
            self._begin_recording()

    def _hotkey_up(self):
        if self._recording:
            self._end_recording()

    def _toggle_recording(self):
        if self._recording:
            self._end_recording()
        else:
            self._begin_recording()

    # ----- record and process ---------------------------------------------

    def _begin_recording(self):
        if not self.enabled or self._practice_recording:
            return
        excluded = self.config.get("hotkey_exclude_apps", default=[])
        if excluded:
            exe = get_active_app().get("exe", "")
            if _is_app_excluded(exe, excluded):
                self.log.info("Hotkey ignored: foreground app %r is excluded", exe)
                self.interface_state.update(status_code="excluded_app")
                return
        job_id = self._next_job_id()
        try:
            self.recorder.start_recording()
        except Exception as exc:
            self.log.error("Mic error: %s", exc)
            self.interface_state.update(capture_job_id=job_id)
            self.interface_state.latch_issue(
                "microphone_unavailable",
                "Microphone access is needed.",
                "open_system_settings",
                str(exc),
            )
            self._schedule_attempt_hud_clear(job_id, delay=5.0)
            self._legacy_state("error", "microphone unavailable")
            return

        session = DictationSession(self.transcriber, self.recorder, self.config)
        session.job_id = job_id
        self._session = session
        self._capture_job_id = job_id
        threading.Thread(target=self._capture_context, args=(session,), daemon=True).start()
        session.start()
        self._recording = True
        self._record_started_at = time.monotonic()
        self.interface_state.dismiss_issue("microphone_unavailable")
        self.interface_state.dismiss_issue("microphone_reconnected")
        self.interface_state.update(
            availability="ready",
            capture="listening",
            capture_job_id=job_id,
            capture_mode="dictation",
            status_code="listening",
            mic_level_band="silent",
        )
        self._legacy_state("recording")
        threading.Thread(target=self._meter_loop, args=(job_id,), daemon=True).start()

    def _meter_loop(self, job_id):
        while self._recording and self._capture_job_id == job_id and not self._shutting_down:
            self.interface_state.update(mic_level_band=_level_band(self.recorder.current_level()))
            time.sleep(0.25)

    def _capture_context(self, session):
        context = get_active_app()
        em = self.config.get("edit_mode", default={})
        tone = self.config.get("app_tones", context.get("exe", ""), default="neutral")
        if em.get("enabled", True) and tone != "literal":
            selected = get_selected_text(max_chars=em.get("max_chars", 4000))
            if not selected.strip() and em.get("clipboard_fallback", True):
                selected = read_selection_via_clipboard()[: em.get("max_chars", 4000)]
            if selected.strip():
                context["selected_text"] = selected
                if self._capture_job_id == getattr(session, "job_id", 0):
                    self.interface_state.update(
                        capture_mode="edit", status_code="edit_listening"
                    )
        sc = self.config.get("screen_context", default={})
        if sc.get("enabled", True):
            screen_text = get_screen_context(
                max_chars=sc.get("max_chars", 1200),
                timeout=sc.get("timeout_seconds", 1.0),
            )
            if screen_text:
                context["screen_text"] = screen_text
                session.extra_hints = extract_notable_tokens(screen_text)
        session.app_context = context

    def _end_recording(self):
        self._recording = False
        session, self._session = self._session, None
        if session is None:
            return
        session.stop()
        duration = session.duration()
        held = time.monotonic() - self._record_started_at
        job_id = getattr(session, "job_id", self._capture_job_id)
        self._capture_job_id = 0
        self.interface_state.update(capture="idle", mic_level_band="silent")

        if held > 1.5 and duration < held * 0.4:
            self.log.error("Mic captured only %.1fs of a %.1fs hold", duration, held)
            self.recorder.reset_stream()
            self.interface_state.latch_issue(
                "microphone_reconnected",
                "Microphone reconnected. Please try again.",
                "start_practice",
                "The audio stream stopped delivering frames during dictation.",
            )
            self._schedule_attempt_hud_clear(job_id, delay=5.0)
            self._legacy_state("error", "microphone reconnected")
            return
        if duration < self.config.get("min_duration_seconds"):
            self.log.info("Ignoring %.2fs tap", duration)
            self.interface_state.update(
                status_code="ready", capture_mode="dictation", capture_job_id=0
            )
            self._legacy_state("idle")
            return

        self.interface_state.update(capture_job_id=0)
        self._queue.put(session)
        # Do not let a newly queued job replace the truthful stage of an
        # older job that is still running.  While capture B is active, job A
        # remains the secondary HUD line; after release, queue_depth records
        # B until the worker actually begins it.
        current = self.interface_state.snapshot()
        if current.get("pipeline") in ("idle", "success", "error"):
            queued_mode = (
                "edit"
                if (getattr(session, "app_context", None) or {}).get("selected_text")
                else "dictation"
            )
            self.interface_state.update(
                pipeline="queued",
                pipeline_job_id=job_id,
                pipeline_mode=queued_mode,
                queue_depth=self._queue.qsize(),
                status_code="queued",
            )
        else:
            self.interface_state.update(queue_depth=self._queue.qsize())
        self._legacy_state("processing")

    def _worker(self):
        while True:
            session = self._queue.get()
            if session is None:
                self._queue.task_done()
                return
            job_id = getattr(session, "job_id", self._next_job_id())
            app_context = session.app_context or {}
            job_mode = "edit" if app_context.get("selected_text", "") else "dictation"
            started = time.monotonic()
            succeeded = False
            try:
                if not self.transcriber.wait_ready(timeout=0):
                    self.interface_state.update(
                        pipeline="waiting_model", pipeline_job_id=job_id,
                        pipeline_mode=job_mode, status_code="waiting_model",
                    )
                else:
                    self.interface_state.update(
                        pipeline="transcribing", pipeline_job_id=job_id,
                        pipeline_mode=job_mode, status_code="transcribing",
                    )
                text = session.finalize()
                t_asr = time.monotonic()
                selected = app_context.get("selected_text", "")

                if not text:
                    self.interface_state.update(
                        pipeline="idle", pipeline_job_id=job_id,
                        status_code="no_speech", detail_code="nothing_inserted",
                        latest_outcome_code="no_speech",
                    )
                    self._schedule_ready(job_id, delay=5.0)
                    continue

                if selected:
                    self.interface_state.update(
                        pipeline="formatting", pipeline_job_id=job_id,
                        pipeline_mode="edit", status_code="edit_formatting",
                    )
                    edited = self.formatter.edit(text, selected, app_context)
                    self.interface_state.update(
                        cleanup_path=self._current_cleanup_path()
                    )
                    t_fmt = time.monotonic()
                    if edited is None:
                        self.log.warning("Edit failed; selection left untouched")
                        self._finish_error(
                            job_id,
                            "edit_failed",
                            "The original selection was not changed.",
                            "try_again",
                            "Local edit formatting was unavailable or returned no safe result.",
                        )
                        self._legacy_state("error", "selection unchanged")
                        continue
                    self.interface_state.update(
                        pipeline="injecting", pipeline_job_id=job_id,
                        status_code="edit_injecting",
                    )
                    inject(
                        edited,
                        method=self.config.get("injection"),
                        restore_clipboard=self.config.get("restore_clipboard"),
                    )
                    self.log.info(
                        "Edit mode: %d chars -> %d chars in %s in %.2fs (asr %.2f, edit %.2f)",
                        len(selected), len(edited), app_context.get("exe") or "unknown app",
                        time.monotonic() - started, t_asr - started, t_fmt - t_asr,
                    )
                    self._finish_success(job_id, "edit_success")
                    succeeded = True
                else:
                    self.interface_state.update(
                        pipeline="formatting", pipeline_job_id=job_id,
                        pipeline_mode="dictation", status_code="formatting",
                    )
                    formatted = self.formatter.format(text, app_context)
                    self.interface_state.update(
                        cleanup_path=self._current_cleanup_path()
                    )
                    formatted = self.dictionary.apply(formatted)
                    t_fmt = time.monotonic()
                    self.interface_state.update(
                        pipeline="injecting", pipeline_job_id=job_id,
                        status_code="injecting",
                    )
                    inject(
                        formatted,
                        method=self.config.get("injection"),
                        restore_clipboard=self.config.get("restore_clipboard"),
                    )
                    t_inj = time.monotonic()
                    self.formatter.note_result(formatted)
                    self.learner.observe(formatted)
                    self.log.info(
                        "Inserted %d chars into %s in %.2fs (asr %.2f, format %.2f, inject %.2f)",
                        len(formatted), app_context.get("exe") or "unknown app",
                        t_inj - started, t_asr - started, t_fmt - t_asr, t_inj - t_fmt,
                    )
                    self._finish_success(job_id, "success")
                    succeeded = True
            except Exception as exc:
                self.log.exception("Pipeline error: %s", exc)
                self._finish_error(
                    job_id,
                    "pipeline_failed",
                    "Text was not inserted.",
                    "open_log",
                    str(exc),
                )
                self._legacy_state("error", "pipeline failed")
            finally:
                self._queue.task_done()
                self.interface_state.update(queue_depth=self._queue.qsize())
                if succeeded:
                    self._legacy_state("recording" if self._recording else "idle")

    def _finish_success(self, job_id: int, status_code: str):
        current_issue = self.interface_state.snapshot().get("last_issue")
        availability = (
            "needs_attention"
            if current_issue and current_issue.get("blocking", True)
            else ("ready" if self.enabled else "disabled")
        )
        self.interface_state.update(
            availability=availability,
            pipeline="success",
            pipeline_job_id=job_id,
            status_code=status_code,
            detail_code=None,
            latest_outcome_code=status_code,
        )
        self._schedule_ready(job_id, delay=1.2)

    def _finish_error(
        self,
        job_id: int,
        issue_code: str,
        message: str,
        action: str,
        detail: str = "",
    ):
        """Publish a recoverable job error, then retire only its HUD state.

        The issue remains available on Home and in the tray after the
        pointer-transparent HUD has had enough time to be read.
        """
        self.interface_state.update(pipeline="error", pipeline_job_id=job_id)
        self.interface_state.latch_issue(
            issue_code,
            message,
            action,
            detail,
            blocking=False,
        )
        self._schedule_pipeline_settle(job_id, delay=5.0, expected=("error",))

    def _schedule_ready(self, job_id: int, delay: float):
        self._schedule_pipeline_settle(
            job_id,
            delay=delay,
            expected=("success", "idle"),
        )

    def _retire_pipeline_job(self, job_id: int, expected) -> bool:
        """Retire one unchanged job without touching a newer capture/job."""
        return self.interface_state.retire_pipeline_job(job_id, expected)

    def _schedule_pipeline_settle(self, job_id: int, delay: float, expected):
        expected = frozenset(expected)

        def settle():
            time.sleep(delay)
            while not getattr(self, "_shutting_down", False):
                snapshot = self.interface_state.snapshot()
                if (
                    snapshot.get("pipeline_job_id") != job_id
                    or snapshot.get("pipeline") not in expected
                ):
                    return
                if self._retire_pipeline_job(job_id, expected):
                    return
                # A newer capture owns the primary HUD line. Wait until it
                # finishes rather than hiding or replacing that interaction.
                time.sleep(0.1)

        threading.Thread(
            target=settle,
            name=f"state-settle-{job_id}",
            daemon=True,
        ).start()

    def _schedule_attempt_hud_clear(self, job_id: int, delay: float):
        """Hide an attempt-scoped HUD error without dismissing its recovery issue."""
        def settle():
            time.sleep(delay)
            self.interface_state.retire_capture_attempt(job_id)

        threading.Thread(
            target=settle,
            name=f"attempt-hud-settle-{job_id}",
            daemon=True,
        ).start()

    # ----- isolated Practice ----------------------------------------------

    @staticmethod
    def _empty_practice():
        return {
            "active": False,
            "processing": False,
            "hasResult": False,
            "heard": "",
            "wouldType": "",
            "level": "silent",
            "message": "",
            "privacyLabel": "Not stored by Speakr; clears when you leave Practice.",
        }

    def subscribe_practice(self, callback):
        self._practice_subscribers.append(callback)

        def unsubscribe():
            try:
                self._practice_subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def _notify_practice(self):
        snapshot = self.practice_snapshot()
        for callback in list(self._practice_subscribers):
            try:
                callback(snapshot)
            except Exception:
                self.log.exception("Practice subscriber failed")

    def practice_snapshot(self):
        with self._practice_lock:
            snapshot = dict(self._practice)
            if self._practice_recording:
                snapshot["level"] = _level_band(self.recorder.current_level())
            return snapshot

    def start_practice(self):
        with self._practice_lock:
            practice_processing = bool(self._practice.get("processing", False))
        if self._recording or self._practice_recording or practice_processing:
            with self._practice_lock:
                self._practice["message"] = (
                    "Wait for the current local dictation to finish, then try Practice."
                )
            self._notify_practice()
            return False
        if self._pipeline_busy():
            phase = self.interface_state.snapshot().get("pipeline", "idle")
            with self._practice_lock:
                self._practice["message"] = (
                    "The local speech model is still getting ready. Practice will be available when it finishes."
                    if phase == "waiting_model"
                    else "Wait for the current local dictation to finish, then try Practice."
                )
            self._notify_practice()
            return False
        if not self.transcriber.wait_ready(timeout=0):
            with self._practice_lock:
                self._practice["message"] = (
                    "The local speech model is not ready. Wait for it to finish, then try again."
                )
            self._notify_practice()
            return False
        self.clear_practice()
        try:
            self.recorder.start_recording()
        except Exception as exc:
            with self._practice_lock:
                self._practice["message"] = "Microphone access is needed."
            self._notify_practice()
            self.interface_state.latch_issue(
                "microphone_unavailable", "Microphone access is needed.",
                "open_system_settings", str(exc),
            )
            return False
        self.interface_state.dismiss_issue("microphone_unavailable")
        self.interface_state.dismiss_issue("microphone_reconnected")
        with self._practice_lock:
            self._practice_recording = True
            self._practice["active"] = True
            generation = self._practice_generation
        self._notify_practice()

        def meter():
            while self._practice_recording and generation == self._practice_generation:
                self._notify_practice()
                time.sleep(0.25)

        threading.Thread(target=meter, name="practice-meter", daemon=True).start()
        return True

    def stop_practice(self):
        with self._practice_lock:
            if not self._practice_recording:
                return False
            self._practice_recording = False
            generation = self._practice_generation
        audio = self.recorder.stop_recording()
        with self._practice_lock:
            self._practice_audio = audio
            self._practice.update(active=False, processing=True, level="silent", message="")
        self._notify_practice()

        def transcribe_practice():
            heard = ""
            would_type = ""
            message = ""
            try:
                if len(audio) < int(self.recorder.sample_rate * 0.25):
                    message = "Speakr didn’t catch speech. Try again when you’re ready."
                else:
                    heard = self.transcriber.transcribe(
                        audio,
                        self.recorder.sample_rate,
                        allow_text_log=False,
                    )
                    with self._practice_lock:
                        if generation != self._practice_generation:
                            return
                    if heard:
                        would_type = rule_based_clean(heard)
                        if self.config.get("voice_commands", default=True):
                            would_type = apply_voice_commands(would_type)
                        would_type = self.dictionary.apply(would_type).strip()
                    else:
                        message = "Speakr didn’t catch speech. Try again when you’re ready."
            except Exception as exc:
                self.log.warning(
                    "Practice transcription failed without content logging (%s)",
                    type(exc).__name__,
                )
                message = "Practice could not finish. Your audio was discarded."
            finally:
                # `audio` is captured only by this worker and becomes collectible
                # immediately after this function returns.
                with self._practice_lock:
                    if generation != self._practice_generation:
                        return
                    self._practice_audio = None
                    self._practice.update(
                        processing=False,
                        hasResult=bool(heard),
                        heard=heard,
                        wouldType=would_type,
                        message=message,
                    )
                self._notify_practice()

        threading.Thread(target=transcribe_practice, name="practice-transcribe", daemon=True).start()
        return True

    def clear_practice(self):
        with self._practice_lock:
            self._practice_generation += 1
            was_recording = self._practice_recording
            self._practice_recording = False
            audio, self._practice_audio = self._practice_audio, None
            self._practice = self._empty_practice()
        if audio is not None:
            try:
                audio.fill(0)
            except (AttributeError, TypeError, ValueError):
                pass
        if was_recording:
            try:
                self.recorder.stop_recording()
            except Exception:
                pass
        self._notify_practice()
        return True

    def navigate(self, page):
        if str(page).lower() != "practice":
            self.clear_practice()
        return True

    # ----- UI data and operations -----------------------------------------

    def subscribe_settings(self, callback):
        self._settings_subscribers.append(callback)

        def unsubscribe():
            try:
                self._settings_subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def _notify_settings(self):
        current = self.interface_state.snapshot().get("settings_version", 0)
        self.interface_state.update(settings_version=(int(current) + 1) % 2_147_483_648)
        snapshot = self.settings_snapshot()
        for callback in list(self._settings_subscribers):
            try:
                callback(snapshot)
            except Exception:
                self.log.exception("Settings subscriber failed")

    def settings_snapshot(self):
        data = self.config.snapshot()
        data["pending_hotkey"] = self._pending_hotkey or ""
        data["capturing_hotkey"] = self._capturing_hotkey
        data["platform"] = "mac" if sys.platform == "darwin" else "windows"
        data.update(
            resolve_hotkey_mode(
                data.get("hotkey", ""),
                data.get("toggle_mode", False),
                platform=data["platform"],
            )
        )
        data["microphone_stream_open"] = self.recorder.stream_open
        data["active_input_device"] = (
            "" if self.recorder.input_device is None else self.recorder.input_device
        )
        data["active_sample_rate"] = self.recorder.sample_rate
        data["model_in_use"] = self.transcriber.model_in_use or ""
        data["device_in_use"] = self.transcriber.device_in_use or ""
        data["compute_type_in_use"] = getattr(
            self.transcriber, "compute_type_in_use", None
        ) or ""
        data["config_path"] = str(cfg_mod.CONFIG_PATH)
        data["log_path"] = str(cfg_mod.LOG_PATH)
        return data

    def list_manual_words(self):
        return self.dictionary.entries()

    def list_learned_words(self):
        return self.learner.entries()

    def _vocabulary_mutation_allowed(self):
        with self._practice_lock:
            practice_busy = self._practice_recording or bool(
                self._practice.get("processing", False)
            )
        if self._recording or self._pipeline_busy() or practice_busy:
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current local dictation or Practice result before changing Vocabulary.",
                "dismiss",
                blocking=False,
            )
            return False
        return True

    def _dismiss_vocabulary_issue(self):
        for code in (
            "busy_setting",
            "dictionary_invalid",
            "dictionary_changed",
            "vocabulary_save_failed",
        ):
            self.interface_state.dismiss_issue(code)

    def add_word(self, word):
        if not self._vocabulary_mutation_allowed():
            return False
        try:
            self.dictionary.add_hint(word)
            self._dismiss_vocabulary_issue()
            self._notify_settings()
            return True
        except ValueError as exc:
            self.interface_state.latch_issue(
                "dictionary_invalid", str(exc), "edit_vocabulary", "", blocking=False
            )
            return False
        except OSError as exc:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "The word could not be saved. The local dictionary is unchanged.",
                "open_dictionary",
                str(exc),
                blocking=False,
            )
            return False

    def add_replacement(self, heard, intended):
        if not self._vocabulary_mutation_allowed():
            return False
        try:
            self.dictionary.add_replacement(heard, intended)
            self._dismiss_vocabulary_issue()
            self._notify_settings()
            return True
        except ValueError as exc:
            self.interface_state.latch_issue(
                "dictionary_invalid", str(exc), "edit_vocabulary", "", blocking=False
            )
            return False
        except OSError as exc:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "The replacement could not be saved. The local dictionary is unchanged.",
                "open_dictionary",
                str(exc),
                blocking=False,
            )
            return False

    def remove_manual_word(self, entry_id):
        if not self._vocabulary_mutation_allowed():
            return False
        try:
            self.dictionary.remove_entry(str(entry_id))
            self._dismiss_vocabulary_issue()
            self._notify_settings()
            return True
        except ValueError as exc:
            self.interface_state.latch_issue(
                "dictionary_changed", str(exc), "reload_dictionary", "", blocking=False
            )
            return False
        except OSError as exc:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "That entry could not be removed. The local dictionary is unchanged.",
                "open_dictionary",
                str(exc),
                blocking=False,
            )
            return False

    def approve_learned_word(self, word):
        if not self._vocabulary_mutation_allowed():
            return False
        try:
            self.dictionary.add_hint(str(word))
        except (ValueError, OSError) as exc:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "That learned word could not be approved. The local dictionary is unchanged.",
                "open_dictionary",
                str(exc),
                blocking=False,
            )
            return False
        removed = self.learner.forget(str(word))
        if not removed:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "The word was added manually, but its learned entry could not be removed.",
                "open_dictionary",
                blocking=False,
            )
        else:
            self._dismiss_vocabulary_issue()
        self._notify_settings()
        return removed

    def forget_learned_word(self, word):
        if not self._vocabulary_mutation_allowed():
            return False
        result = self.learner.forget(str(word))
        if not result:
            self.interface_state.latch_issue(
                "vocabulary_save_failed",
                "That learned word could not be removed. The local file is unchanged.",
                "open_dictionary",
                blocking=False,
            )
        else:
            self._dismiss_vocabulary_issue()
        self._notify_settings()
        return result

    def complete_onboarding(self):
        try:
            self.config.set("ui", "onboarding_complete", value=True)
        except OSError as exc:
            self.interface_state.latch_issue(
                "setting_save_failed",
                "Setup could not be marked complete. Your settings are otherwise unchanged.",
                "open_config",
                str(exc),
            )
            return False
        self.interface_state.dismiss_issue("setting_save_failed")
        self._notify_settings()
        return True

    def reset_settings_section(self, section):
        section = str(section).lower()
        sections = {
            "interface": {
                "ui.theme": "system",
                "ui.visual_effects": "system",
                "ui.density": "comfortable",
                "ui.text_scale": "system",
                "ui.reduced_motion": "system",
                "ui.hud_visibility": "while_dictating",
                "ui.hud_size": "standard",
                "ui.hud_edge": "bottom",
                "ui.hud_scale": 100,
                "ui.background_announcements": False,
            },
            "privacy": {
                "keep_mic_stream_open": True,
                "preroll_seconds": 0.4,
                "screen_context.enabled": True,
                "formatting.include_recent_context": True,
                "log_transcripts": False,
                "restore_clipboard": True,
            },
        }
        updates = sections.get(section)
        if updates is None:
            return False
        if section != "interface" and (
            self._recording or self._practice_recording or self._pipeline_busy()
        ):
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current dictation to finish before resetting this section.",
                "dismiss",
            )
            return False
        try:
            self.config.set_many(updates)
        except OSError as exc:
            self.interface_state.latch_issue(
                "setting_save_failed",
                "Those defaults could not be saved. Your previous file is unchanged.",
                "open_config",
                str(exc),
            )
            return False
        self.interface_state.dismiss_issue("setting_save_failed")
        if section == "privacy":
            self.recorder.preroll_samples = int(0.4 * self.recorder.sample_rate)
            self.recorder.clear_preroll()
            try:
                if self.enabled:
                    self.recorder.set_keep_stream_open(True)
                else:
                    self.recorder.keep_stream_open = True
                    self.recorder.pause()
            except Exception as exc:
                self.interface_state.latch_issue(
                    "microphone_unavailable",
                    "Privacy defaults were saved, but the microphone could not be made ready.",
                    "open_system_settings",
                    str(exc),
                )
        self._notify_settings()
        return True

    def dismiss_issue(self):
        self.interface_state.dismiss_issue()
        return True

    def toggle_dictation(self):
        return self.toggle_enabled()

    def toggle_enabled(self):
        if self._recording or self._practice_recording or self._pipeline_busy():
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current dictation to finish before changing this setting.",
                "dismiss",
                "",
            )
            return False
        self.enabled = not self.enabled
        if self.enabled:
            try:
                self.recorder.resume()
            except Exception as exc:
                self.enabled = False
                self.interface_state.latch_issue(
                    "microphone_unavailable", "Microphone access is needed.",
                    "open_system_settings", str(exc),
                )
                return False
        else:
            self.recorder.pause()
        self.interface_state.update(
            enabled=self.enabled,
            availability="ready" if self.enabled else "disabled",
            status_code="ready" if self.enabled else "disabled",
            mic_level_band="silent",
        )
        self._legacy_state("idle" if self.enabled else "disabled")
        self._notify_settings()
        return self.enabled

    def set_setting(self, path, value):
        path = str(path)
        bool_paths = {
            "toggle_mode", "restore_clipboard", "keep_mic_stream_open",
            "voice_commands", "log_transcripts", "streaming.enabled",
            "screen_context.enabled", "edit_mode.enabled",
            "edit_mode.clipboard_fallback", "learning.enabled",
            "formatting.enabled", "formatting.use_ollama",
            "formatting.autostart_ollama", "formatting.include_recent_context",
            "ui.onboarding_complete", "ui.open_window_on_start",
            "ui.background_announcements",
        }
        choices = {
            "model": {"auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"},
            "device": {"auto", "cpu", "cuda"},
            "compute_type": {"auto", "int8", "float16", "float32", "int8_float16"},
            "injection": {"paste", "type"},
            "ui.theme": {"system", "light", "dark", "high_contrast"},
            "ui.visual_effects": {"system", "full", "reduced", "off"},
            "ui.density": {"comfortable", "compact"},
            "ui.text_scale": {"system", "110", "125", "150", "175", "200"},
            "ui.reduced_motion": {"system", "reduce"},
            # Compatibility for pre-release native-interface configs.
            "ui.motion": {"system", "reduced", "full"},
            "ui.hud_visibility": {"while_dictating", "always", "off"},
            "ui.hud_size": {"standard", "large"},
            "ui.hud_edge": {"bottom", "top"},
        }
        numeric = {
            "ui.hud_scale": (100, 200),
            "preroll_seconds": (0.0, 2.0), "vad_threshold": (0.05, 0.95),
            "min_duration_seconds": (0.1, 3.0), "max_duration_seconds": (5, 600),
            "streaming.chunk_seconds": (3, 30),
            "streaming.min_silence_seconds": (0.2, 2.0),
            "screen_context.max_chars": (0, 10000),
            "screen_context.timeout_seconds": (0.1, 5.0),
            "edit_mode.max_chars": (100, 20000),
            "learning.min_occurrences": (1, 20), "learning.max_hints": (1, 200),
            "formatting.timeout_seconds": (1, 120), "sample_rate": (8000, 48000),
        }
        string_paths = {
            "language", "beam_size", "input_device", "formatting.ollama_model",
            "formatting.ollama_url", "formatting.keep_alive",
        }
        if path not in bool_paths and path not in choices and path not in numeric and path not in string_paths:
            self.interface_state.latch_issue(
                "setting_not_allowed", "That setting cannot be changed here.", "dismiss", path,
            )
            return False

        if path in bool_paths:
            if not isinstance(value, bool):
                return False
        elif path in choices:
            value = str(value)
            if value not in choices[path]:
                return False
        elif path in numeric:
            low, high = numeric[path]
            if isinstance(value, bool):
                return False
            try:
                value = float(value)
            except (TypeError, ValueError):
                return False
            if not low <= value <= high:
                return False
            if isinstance(low, int) and isinstance(high, int):
                value = int(value)
        elif path == "formatting.ollama_url":
            value = _local_ollama_url(value)
            if value is None:
                self.interface_state.latch_issue(
                    "local_url_required",
                    "Speakr only connects to Ollama on this device.",
                    "dismiss",
                    "",
                )
                return False
        elif path == "beam_size":
            value = "auto" if str(value) == "auto" else max(1, min(10, int(value)))
        elif path == "language":
            value = None if value in (None, "", "auto") else str(value)[:16]
        elif path == "input_device":
            cleaned_device = "" if value is None else str(value).strip()
            value = None if cleaned_device.casefold() in {"", "default"} else cleaned_device
        else:
            value = str(value)[:200]

        busy = self._recording or self._pipeline_busy() or self._practice_recording
        privacy_shutdown = path == "log_transcripts" and value is False
        if busy and not path.startswith("ui.") and not privacy_shutdown:
            self.interface_state.latch_issue(
                "busy_setting",
                "Wait for the current dictation to finish before changing this setting.",
                "dismiss",
                "",
            )
            return False

        keys = path.split(".")
        if path == "model":
            return self.change_model(value)
        try:
            self.config.set(*keys, value=value)
        except OSError as exc:
            self.interface_state.latch_issue(
                "setting_save_failed",
                "That setting could not be saved. Your previous file is unchanged.",
                "open_config",
                str(exc),
            )
            return False

        for resolved_issue in (
            "setting_save_failed",
            "setting_not_allowed",
            "busy_setting",
            "local_url_required",
        ):
            self.interface_state.dismiss_issue(resolved_issue)

        if path == "toggle_mode":
            self._restart_hotkey_listener()
        elif path == "keep_mic_stream_open":
            try:
                if self.enabled:
                    self.recorder.set_keep_stream_open(value)
                else:
                    self.recorder.keep_stream_open = value
            except Exception as exc:
                self.interface_state.latch_issue(
                    "microphone_unavailable",
                    "The preference was saved, but the microphone could not be made ready.",
                    "open_system_settings",
                    str(exc),
                )
        elif path == "preroll_seconds":
            self.recorder.preroll_samples = int(value * self.recorder.sample_rate)
            self.recorder.clear_preroll()
        elif path == "formatting.include_recent_context" and value is False:
            self.formatter.clear_recent_context()
        elif path in {"device", "compute_type"}:
            self.interface_state.update(
                availability="starting",
                pipeline="waiting_model",
                status_code="waiting_model",
                device="unknown",
                compute_type="unknown",
            )
            threading.Thread(
                target=self._load_model,
                name=f"{path.replace('_', '-')}-change",
                daemon=True,
            ).start()
        elif path in {"sample_rate", "input_device"}:
            self.interface_state.latch_issue(
                "restart_required",
                "Restart Speakr to use the new microphone setting.",
                "dismiss",
                "",
                blocking=False,
            )
        elif path.startswith("formatting."):
            if path in {"formatting.ollama_url", "formatting.ollama_model"}:
                self.formatter._ollama_ok = None
            self.interface_state.update(cleanup_path=self._current_cleanup_path())
            formatting = self.config.get("formatting", default={}) or {}
            if (
                path in {
                    "formatting.enabled",
                    "formatting.use_ollama",
                    "formatting.autostart_ollama",
                    "formatting.ollama_url",
                    "formatting.ollama_model",
                }
                and formatting.get("enabled", True)
                and formatting.get("use_ollama", True)
            ):
                threading.Thread(
                    target=self._prepare_formatter,
                    name="ollama-setting-probe",
                    daemon=True,
                ).start()

        self._notify_settings()
        return True

    # Compatibility actions retained for the legacy tray.
    def toggle_formatting(self):
        return self.set_setting("formatting.enabled", not self.config.get("formatting", "enabled"))

    def toggle_learning(self):
        return self.set_setting("learning.enabled", not self.config.get("learning", "enabled"))

    def toggle_screen_context(self):
        return self.set_setting("screen_context.enabled", not self.config.get("screen_context", "enabled"))

    def toggle_edit_mode(self):
        return self.set_setting("edit_mode.enabled", not self.config.get("edit_mode", "enabled"))

    def change_model(self, name):
        if self._recording or self._pipeline_busy() or self._practice_recording:
            return False
        try:
            self.config.set("model", value=name)
        except OSError as exc:
            self.interface_state.latch_issue(
                "setting_save_failed",
                "The speech model setting could not be saved. The previous model remains active.",
                "open_config",
                str(exc),
            )
            return False
        self.interface_state.dismiss_issue("setting_save_failed")
        self.interface_state.update(
            availability="starting", pipeline="waiting_model", model=name,
            status_code="waiting_model",
        )
        threading.Thread(target=self._load_model, name="model-change", daemon=True).start()
        self._notify_settings()
        return True

    def retry_model(self):
        if self._pipeline_busy():
            return False
        threading.Thread(target=self._load_model, name="model-retry", daemon=True).start()
        return True

    def retry_microphone(self):
        if self._recording or self._practice_recording:
            return False
        try:
            if not self.enabled:
                self.recorder.pause()
            else:
                self.recorder.reset_stream()
                if self.config.get("keep_mic_stream_open", default=True):
                    self.recorder.resume()
                else:
                    # Open and immediately close a local probe stream.  No
                    # resulting samples leave AudioRecorder or reach ASR.
                    self.recorder.start_recording()
                    self.recorder.stop_recording()
            self.interface_state.dismiss_issue("microphone_unavailable")
            self.interface_state.dismiss_issue("microphone_reconnected")
            self._notify_settings()
            return True
        except Exception as exc:
            self.interface_state.latch_issue(
                "microphone_unavailable",
                "Microphone access is needed.",
                "open_system_settings",
                str(exc),
            )
            return False

    def retry_setup(self):
        issue = (self.interface_state.snapshot().get("last_issue") or {}).get("code", "")
        if issue in {"model_unavailable", "model_load_failed"}:
            return self.retry_model()
        microphone_ok = self.retry_microphone()
        if not self.transcriber.wait_ready(timeout=0):
            self.retry_model()
        return microphone_ok

    def reload_config(self):
        self.config.load()
        self.dictionary.load()
        self._restart_hotkey_listener()
        self.interface_state.dismiss_issue("dictionary_changed")
        self.interface_state.dismiss_issue("vocabulary_save_failed")
        self.interface_state.update(hotkey=self.config.get("hotkey"), model=self.config.get("model"))
        self._notify_settings()
        self.log.info("Config and dictionary reloaded")
        return True

    def reload_dictionary(self):
        self.dictionary.load()
        self.interface_state.dismiss_issue("dictionary_changed")
        self.interface_state.dismiss_issue("vocabulary_save_failed")
        self._notify_settings()
        self.log.info("Dictionary reloaded")
        return True

    def open_local(self, kind):
        mapping = {
            "config": cfg_mod.CONFIG_PATH,
            "dictionary": cfg_mod.DICTIONARY_PATH,
            "log": cfg_mod.LOG_PATH,
        }
        path = mapping.get(str(kind))
        if path is None:
            return False
        _open_path(path)
        return True

    def open_config(self):
        return self.open_local("config")

    def open_dictionary(self):
        return self.open_local("dictionary")

    def open_log(self):
        return self.open_local("log")

    def open_system_settings(self):
        try:
            if sys.platform == "darwin":
                subprocess.Popen([
                    "open",
                    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
                ])
            else:
                os.startfile("ms-settings:privacy-microphone")
            return True
        except OSError as exc:
            self.interface_state.latch_issue(
                "settings_open_failed", "Open your system privacy settings manually.",
                "dismiss", str(exc),
            )
            return False

    def open_panel(self):
        return self.open_browser_fallback()

    def open_browser_fallback(self):
        if self.webui.port is None:
            self.webui.start()
        webbrowser.open(self.webui.url())
        return True


_instance_lock = None
_launch_gate = None


def _try_process_lock(existing, windows_name, unix_name, *, owned=False):
    if existing is not None:
        return existing, True
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183
        WAIT_OBJECT_0 = 0
        WAIT_ABANDONED = 0x80
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateMutexW(None, owned, windows_name)
        if not handle:
            raise OSError(f"could not create the {windows_name} mutex")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            acquired = owned and kernel32.WaitForSingleObject(handle, 0) in {
                WAIT_OBJECT_0,
                WAIT_ABANDONED,
            }
            if not acquired:
                kernel32.CloseHandle(handle)
                return None, False
        return handle, True

    import fcntl

    lock_file = open(cfg_mod.ROOT / unix_name, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file, True
    except OSError:
        lock_file.close()
        return None, False


def _wait_for_process_lock(try_acquire, wait_seconds):
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    while True:
        if try_acquire():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_SINGLE_INSTANCE_POLL_SECONDS)


def _release_process_lock(lock, *, owned=False):
    if lock is None:
        return
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            if owned:
                kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
                kernel32.ReleaseMutex.restype = wintypes.BOOL
                kernel32.ReleaseMutex(lock)
            kernel32.CloseHandle(lock)
        except Exception:
            pass
        return
    try:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_UN)
    except (OSError, ValueError):
        pass
    try:
        lock.close()
    except (OSError, ValueError):
        pass


def _try_acquire_launch_gate():
    global _launch_gate
    _launch_gate, acquired = _try_process_lock(
        _launch_gate,
        _LAUNCH_GATE_MUTEX_NAME,
        ".speakr.launch-gate.lock",
        owned=True,
    )
    return acquired


def _acquire_launch_gate(*, wait_seconds=0.0):
    return _wait_for_process_lock(_try_acquire_launch_gate, wait_seconds)


def _release_launch_gate():
    global _launch_gate
    lock, _launch_gate = _launch_gate, None
    _release_process_lock(lock, owned=True)


def _try_acquire_single_instance():
    global _instance_lock
    _instance_lock, acquired = _try_process_lock(
        _instance_lock, _SINGLE_INSTANCE_MUTEX_NAME, ".speakr.lock"
    )
    return acquired


def _acquire_single_instance(*, wait_seconds=0.0):
    return _wait_for_process_lock(_try_acquire_single_instance, wait_seconds)


def _release_single_instance():
    global _instance_lock
    lock, _instance_lock = _instance_lock, None
    _release_process_lock(lock)


def _renderer_child_holds_primary() -> bool:
    """Probe that the renderer child exclusively owns the primary lock."""

    if not _try_acquire_single_instance():
        return True
    _release_single_instance()
    return False


def main():
    acquired = False
    handoff = _RendererHandoffChild.from_environment()
    if handoff is None:
        try:
            gate_acquired = _try_acquire_launch_gate()
            waited_for_handoff = not gate_acquired
            if not gate_acquired:
                gate_acquired = _acquire_launch_gate(
                    wait_seconds=_SINGLE_INSTANCE_HANDOFF_SECONDS
                )
        except OSError as exc:
            setup_logging().warning(
                "Could not use the launch gate; using the primary lock: %s", exc
            )
            gate_acquired = False
            waited_for_handoff = False
            acquired = _acquire_single_instance()
        if gate_acquired:
            try:
                acquired = _acquire_single_instance()
            finally:
                _release_launch_gate()
    if handoff is None and not acquired:
        setup_logging().warning("Speakr is already running; requesting its window")
        try:
            cfg_mod.SHOW_REQUEST_PATH.write_text(str(time.time_ns()), encoding="utf-8")
        except OSError:
            pass
        if not waited_for_handoff:
            _open_running_legacy_panel()
        return
    if handoff is None:
        # Remove only a stale request left by an earlier crashed/exited
        # primary. The renderer-handoff parent already did this; its guarded
        # child must preserve any fresh wake request written during handoff.
        try:
            cfg_mod.SHOW_REQUEST_PATH.unlink()
        except OSError:
            pass
    application = SpeakrApp()
    application._renderer_handoff = handoff
    application.start()


if __name__ == "__main__":
    main()
