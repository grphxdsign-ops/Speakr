from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from speakr import app as app_module
from speakr import qt_ui
from speakr import renderer_handoff as handoff_module
from speakr.app import SpeakrApp


REPO_ROOT = Path(__file__).resolve().parents[1]
_RENDERER_ENV_KEYS = (
    "QT_QUICK_BACKEND",
    "QSG_RHI_BACKEND",
    "SPEAKR_QT_SOFTWARE",
    handoff_module.GUARD_ENV,
    handoff_module.PARENT_ENV,
    handoff_module.ADDRESS_ENV,
    handoff_module.TOKEN_ENV,
    handoff_module.NONCE_ENV,
    "SESSIONNAME",
    "SSH_CONNECTION",
)
_RUNTIME_DIAGNOSTICS = re.compile(
    r"(?im)(?:"
    r"Scenegraph already initialized.*request ignored|"
    r"(?:TypeError|ReferenceError|binding loop).*\.qml|"
    r"(?:qml|qrc|file):.*\.qml.*(?:error|warning)|"
    r"scene\s*graph.*(?:error|failed)|"
    r"(?:failed|unable) to (?:create|initialize).*"
    r"(?:RHI|renderer|graphics|Direct3D|Metal|OpenGL|Vulkan)"
    r")"
)


def _run_python(code: str, *, environment=None, qpa="offscreen", timeout=30):
    child_env = os.environ.copy()
    for key in _RENDERER_ENV_KEYS:
        child_env.pop(key, None)
    child_env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT), child_env.get("PYTHONPATH", "")))
    )
    child_env.pop("QT_QPA_PLATFORM", None)
    if qpa is not None:
        child_env["QT_QPA_PLATFORM"] = qpa
    if environment:
        child_env.update(environment)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=REPO_ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


class CleanChildMixin:
    def assert_child_passed(self, completed):
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        combined = completed.stdout + "\n" + completed.stderr
        match = _RUNTIME_DIAGNOSTICS.search(combined)
        self.assertIsNone(match, f"nested runtime diagnostic: {match}\n{combined}")


@unittest.skipUnless(qt_ui.qt_available(), "PySide6-Essentials is optional")
class RendererDeviceTests(CleanChildMixin, unittest.TestCase):
    def test_nested_runtime_diagnostic_is_rejected(self):
        completed = subprocess.CompletedProcess(
            [sys.executable],
            0,
            "",
            "Scenegraph already initialized, setBackend() request ignored",
        )
        with self.assertRaises(AssertionError):
            self.assert_child_passed(completed)

    def test_software_preflight_renders_and_leaves_no_quick_objects(self):
        completed = _run_python(
            """
            import shiboken6
            from speakr import qt_ui

            qt = qt_ui._load_qt()
            qt_ui._configure_renderer(qt, True)
            app = qt.QApplication([])
            before_windows = {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickWindow)
            }
            before_controls = {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickRenderControl)
            }
            assert qt_ui._probe_effective_renderer(
                qt, software_requested=True
            ) is True
            assert app.allWindows() == []
            after_windows = {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickWindow)
            }
            after_controls = {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickRenderControl)
            }
            assert after_windows == before_windows
            assert after_controls == before_controls
            print('software-render-proof-clean')
            """,
            environment={"SPEAKR_QT_SOFTWARE": "1"},
        )
        self.assert_child_passed(completed)
        self.assertIn("software-render-proof-clean", completed.stdout)

    def test_gpu_preflight_failure_is_retryable_and_cleanup_is_exact(self):
        completed = _run_python(
            """
            from speakr import qt_ui

            qt = qt_ui._load_qt()
            qt.QGuiApplication = type(
                'Gui', (), {'platformName': staticmethod(lambda: 'windows')}
            )
            class Signal:
                def __init__(self): self.callback = None
                def connect(self, callback, *_args): self.callback = callback
                def emit(self, *args):
                    if self.callback: self.callback(*args)
            state = {'mode': 'false'}
            class Renderer:
                @staticmethod
                def graphicsApi():
                    return qt.QSGRendererInterface.GraphicsApi.Direct3D11
            class Probe:
                def __init__(self, _control):
                    self.sceneGraphInitialized = Signal()
                    self.sceneGraphError = Signal()
                    self.closed = self.destroyed = self.deleted = False
                    state['probe'] = self
                def rendererInterface(self): return Renderer()
                def close(self): self.closed = True
                def destroy(self): self.destroyed = True
                def deleteLater(self): self.deleted = True
            class Control:
                def __init__(self):
                    self.invalidated = self.deleted = False
                    state['control'] = self
                def initialize(self):
                    if state['mode'] == 'exception': raise RuntimeError('boom')
                    if state['mode'] == 'error':
                        state['probe'].sceneGraphError.emit('context', 'failed')
                    if state['mode'] == 'no_signal': return True
                    return False
                def invalidate(self): self.invalidated = True
                def deleteLater(self): self.deleted = True
            qt.QQuickWindow = Probe
            qt.QQuickRenderControl = Control
            for mode in ('false', 'exception', 'error', 'no_signal'):
                state['mode'] = mode
                for requested, retryable in ((False, True), (True, False)):
                    try:
                        qt_ui._probe_effective_renderer(
                            qt, software_requested=requested
                        )
                    except qt_ui.QtUnavailable as exc:
                        assert exc.renderer_retryable is retryable
                    else:
                        raise AssertionError(mode)
                    assert state['probe'].closed
                    assert state['probe'].destroyed
                    assert state['probe'].deleted
                    assert state['control'].invalidated
                    assert state['control'].deleted
            print('gpu-failure-matrix-clean')
            """
        )
        self.assert_child_passed(completed)

    @unittest.skipUnless(sys.platform == "win32", "native Windows proof")
    def test_native_windows_gpu_and_software_preserve_focus_and_caret(self):
        code = """
            import ctypes, shiboken6, sys
            from ctypes import wintypes
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QLineEdit, QWidget
            from speakr import qt_ui

            SOFTWARE = __SOFTWARE__
            class GUITHREADINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                    ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
                    ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                    ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
                    ('rcCaret', wintypes.RECT),
                ]
            def identity(hwnd):
                tid = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                info = GUITHREADINFO(); info.cbSize = ctypes.sizeof(info)
                if not tid or not ctypes.windll.user32.GetGUIThreadInfo(
                    tid, ctypes.byref(info)
                ): return None
                return int(info.hwndFocus or 0), int(info.hwndCaret or 0)

            qt = qt_ui._load_qt(); qt_ui._configure_renderer(qt, SOFTWARE)
            app = qt.QApplication([])
            if app.platformName() != 'windows': sys.exit(77)
            host = QWidget(); edit = QLineEdit(host)
            edit.setGeometry(8, 8, 260, 44); edit.setText('focus identity')
            host.resize(280, 60); host.show(); host.activateWindow(); edit.setFocus()
            ctypes.windll.user32.SetForegroundWindow(int(host.winId())); QTest.qWait(100)
            foreground = int(ctypes.windll.user32.GetForegroundWindow() or 0)
            before_identity = identity(foreground)
            if not foreground or not before_identity or not before_identity[0]: sys.exit(77)
            before_all = {int(x.winId()) for x in app.allWindows()}
            before_quick = {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickWindow)
            }
            before_controls = {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickRenderControl)
            }
            assert qt_ui._probe_effective_renderer(
                qt, software_requested=SOFTWARE
            ) is SOFTWARE
            QTest.qWait(30)
            assert int(ctypes.windll.user32.GetForegroundWindow() or 0) == foreground
            assert identity(foreground) == before_identity
            assert {int(x.winId()) for x in app.allWindows()} == before_all
            assert before_quick == {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickWindow)
            }
            assert before_controls == {
                id(x) for x in shiboken6.getAllValidWrappers()
                if isinstance(x, qt.QQuickRenderControl)
            }
            assert app.focusWidget() is edit
            host.close(); print('native-renderer-focus-clean')
        """
        for software in (False, True):
            with self.subTest(software=software):
                completed = _run_python(
                    code.replace("__SOFTWARE__", repr(software)),
                    environment=(
                        {"SPEAKR_QT_SOFTWARE": "1"} if software else None
                    ),
                    qpa="windows",
                )
                if completed.returncode == 77:
                    self.skipTest("Windows focus/caret identity unavailable")
                self.assert_child_passed(completed)

    def test_required_main_gate_and_commit_order(self):
        qapp = mock.Mock()
        window = mock.Mock()
        window.isVisible.return_value = True
        window.isExposed.return_value = False
        self.assertFalse(
            qt_ui._wait_for_required_main_window(qapp, window, timeout_ms=0)
        )
        window.isExposed.return_value = True
        self.assertTrue(
            qt_ui._wait_for_required_main_window(qapp, window, timeout_ms=0)
        )

        completed = _run_python(
            """
            from speakr import native_window, qt_ui
            from speakr.interface_state import InterfaceState

            seen = []
            real_type = native_window.NativeWindowController
            def controller_factory(**kwargs):
                assert kwargs['software_renderer'] is True
                kwargs['platform_name'] = 'test'
                kwargs['adapter'] = native_window._NullAdapter()
                return real_type(**kwargs)
            qt_ui.NativeWindowController = controller_factory
            class App:
                enabled = True
                _qt_frontend = None
                interface_state = InterfaceState(
                    {'availability': 'ready', 'enabled': True}
                )
                @staticmethod
                def settings_snapshot():
                    return {'ui': {
                        'onboarding_complete': True,
                        'open_window_on_start': True,
                        'theme': 'system', 'visual_effects': 'full',
                        'density': 'comfortable', 'text_scale': 'system',
                        'reduced_motion': 'reduce', 'hud_visibility': 'off',
                        'hud_size': 'standard', 'hud_edge': 'bottom',
                        'hud_scale': 100, 'background_announcements': False,
                    }, 'hotkey': 'right ctrl', 'toggle_mode': False,
                    'app_tones': {}, 'hotkey_exclude_apps': []}
                practice_snapshot = staticmethod(lambda: {})
                list_manual_words = staticmethod(lambda: [])
                list_learned_words = staticmethod(lambda: [])
                subscribe_settings = staticmethod(lambda _cb: (lambda: None))
                subscribe_practice = staticmethod(lambda _cb: (lambda: None))
                def _frontend_committed(self, frontend):
                    window = self._qt_frontend._main_window
                    assert frontend == 'native'
                    assert window.isVisible() and window.isExposed()
                    seen.append('visible')
                    return True
                def _start_core(self):
                    assert seen == ['visible']
                    seen.append('core')
                    qt_ui._load_qt().QApplication.instance().quit()
            assert qt_ui.run_native_ui(App()) == 0
            assert seen == ['visible', 'core']
            print('native-commit-order-clean')
            """,
            environment={"SPEAKR_QT_SOFTWARE": "1"},
        )
        self.assert_child_passed(completed)


class PreparedHandoffTests(CleanChildMixin, unittest.TestCase):
    def setUp(self):
        app_module._release_single_instance()
        app_module._release_launch_gate()

    def tearDown(self):
        app_module._release_single_instance()
        app_module._release_launch_gate()

    def test_no_prepared_record_is_bounded_private_and_socket_free(self):
        process = mock.Mock(); process.poll.return_value = None
        release = mock.Mock()
        before_threads = {x.ident for x in threading.enumerate()}
        with mock.patch.object(
            app_module.socket, "socket", side_effect=AssertionError("network")
        ):
            handoff = app_module._RendererHandoffParent()
            directory = Path(handoff.address)
            if os.name == "posix":
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertFalse(
                handoff.wait_for_ready(
                    process,
                    timeout=0.03,
                    release_primary=release,
                    claim_is_exclusive=lambda: True,
                )
            )
            handoff.close()
        release.assert_not_called()
        self.assertFalse(directory.exists())
        self.assertEqual(
            before_threads, {x.ident for x in threading.enumerate()}
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows local-temp guard")
    def test_remote_or_reparse_temp_is_rejected_before_spawn(self):
        import ctypes

        logger = mock.Mock()
        with mock.patch.object(
            handoff_module, "_windows_temp_path", return_value=r"\\server\share"
        ), mock.patch.object(
            handoff_module.tempfile,
            "gettempdir",
            side_effect=AssertionError("probe"),
        ), mock.patch.object(
            app_module, "_acquire_launch_gate", return_value=True
        ), mock.patch.object(app_module.subprocess, "Popen") as popen:
            self.assertFalse(app_module._relaunch_with_software_renderer(logger))
        popen.assert_not_called()

        remote_kernel = mock.Mock()
        remote_kernel.GetDriveTypeW.return_value = 4  # DRIVE_REMOTE
        with mock.patch.object(
            handoff_module, "_windows_temp_path", return_value=r"Z:\Temp"
        ), mock.patch.object(
            ctypes.windll, "kernel32", remote_kernel
        ), mock.patch.object(
            handoff_module.os, "lstat", side_effect=AssertionError("remote stat")
        ):
            with self.assertRaises(OSError):
                handoff_module._local_temp_root()

        status = mock.Mock(st_file_attributes=0x400, st_mode=0o040000)
        with mock.patch.object(
            handoff_module,
            "_windows_temp_path",
            return_value=str(Path.cwd().anchor + "temp-link"),
        ), mock.patch.object(handoff_module.os, "lstat", return_value=status):
            with self.assertRaises(OSError):
                handoff_module._local_temp_root()

        hostile = {
            app_module._SOFTWARE_RELAUNCH_GUARD_ENV: "1",
            app_module._SOFTWARE_RELAUNCH_PARENT_ENV: str(os.getpid() + 1),
            app_module._SOFTWARE_RELAUNCH_ADDRESS_ENV: r"\\server\share\speakr-renderer-x",
            app_module._SOFTWARE_RELAUNCH_AUTH_ENV: "t" * 43,
            app_module._SOFTWARE_RELAUNCH_NONCE_ENV: "n" * 32,
        }
        with mock.patch.dict(os.environ, hostile, clear=True), mock.patch.object(
            handoff_module, "_local_temp_root", return_value=Path.cwd()
        ), mock.patch.object(
            handoff_module.os, "lstat", side_effect=AssertionError("remote stat")
        ):
            self.assertIsNone(
                app_module._RendererHandoffChild.from_environment()
            )

    def test_invalid_token_never_releases_primary(self):
        handoff = app_module._RendererHandoffParent()
        process = mock.Mock(pid=os.getpid()); process.poll.return_value = None
        real_replace = os.replace
        replace_calls = []
        def flaky_replace(source, destination):
            replace_calls.append(source)
            if len(replace_calls) == 1:
                raise PermissionError("sharing violation")
            return real_replace(source, destination)
        channel = handoff_module._Channel(
            handoff.address, handoff.nonce, "wrong-token"
        )
        with mock.patch.object(handoff_module.os, "replace", flaky_replace):
            channel.send(
                "child", "prepared", time.monotonic() + 1,
                pid=os.getpid(), frontend="legacy",
            )

        real_read = Path.read_bytes
        read_calls = []
        def flaky_read(path):
            if path.name == "child.json":
                read_calls.append(path)
                if len(read_calls) == 1:
                    raise PermissionError("sharing violation")
            return real_read(path)
        release = mock.Mock()
        with mock.patch.object(Path, "read_bytes", flaky_read):
            self.assertFalse(
                handoff.wait_for_ready(
                    process,
                    timeout=0.3,
                    release_primary=release,
                    claim_is_exclusive=lambda: True,
                )
            )
        self.assertEqual((len(replace_calls), len(read_calls)), (2, 2))
        release.assert_not_called(); handoff.close()

    def test_child_reject_releases_lock_and_cannot_try_second_frontend(self):
        child = app_module._RendererHandoffChild(
            "unused", "t" * 43, "n" * 32, 123
        )
        release = mock.Mock()
        with mock.patch.object(
            child._channel, "send"
        ), mock.patch.object(
            child._channel,
            "receive",
            side_effect=[{"parent_pid": 123}, ValueError("rejected")],
        ):
            self.assertFalse(
                child.prepare(
                    "native",
                    timeout=1,
                    acquire_primary=mock.Mock(return_value=True),
                    release_primary=release,
                )
            )
            self.assertFalse(
                child.prepare(
                    "legacy",
                    timeout=1,
                    acquire_primary=mock.Mock(return_value=True),
                    release_primary=release,
                )
            )
        release.assert_called_once_with()
        self.assertTrue(child.attempted)

    def test_three_process_prepared_transfer_fences_contender_and_keeps_wake(self):
        instance = f"SpeakrPrepared-{uuid.uuid4()}"
        gate = f"SpeakrPreparedGate-{uuid.uuid4()}"
        completed = _run_python(
            f"""
            import os, subprocess, sys, tempfile
            from pathlib import Path
            from speakr import app

            temp = tempfile.TemporaryDirectory(); root = Path(temp.name)
            wake = root / 'show.request'
            app.cfg_mod.ROOT = root; app.cfg_mod.SHOW_REQUEST_PATH = wake
            app._SINGLE_INSTANCE_MUTEX_NAME = {instance!r}
            app._LAUNCH_GATE_MUTEX_NAME = {gate!r}
            setup = (
                "from pathlib import Path\\nfrom speakr import app\\n"
                + "app.cfg_mod.ROOT=Path(" + repr(str(root)) + ")\\n"
                + "app.cfg_mod.SHOW_REQUEST_PATH=Path(" + repr(str(wake)) + ")\\n"
                + "app._SINGLE_INSTANCE_MUTEX_NAME=" + repr({instance!r}) + "\\n"
                + "app._LAUNCH_GATE_MUTEX_NAME=" + repr({gate!r}) + "\\n"
            )
            assert app._acquire_single_instance(); assert app._acquire_launch_gate()
            handoff = app._RendererHandoffParent(); env = os.environ.copy()
            env.update(handoff.environment())
            env[app._SOFTWARE_RELAUNCH_GUARD_ENV] = '1'
            env[app._SOFTWARE_RELAUNCH_PARENT_ENV] = str(os.getpid())
            designated_code = setup + (
                "import time\\n"
                "time.sleep(.2)\\n"
                "session=app._RendererHandoffChild.from_environment()\\n"
                "assert session and session.prepare(\\n"
                " 'legacy', timeout=app._SINGLE_INSTANCE_HANDOFF_SECONDS,\\n"
                " acquire_primary=app._acquire_single_instance,\\n"
                " release_primary=app._release_single_instance)\\n"
                "deadline=time.monotonic()+4\\n"
                "while not app.cfg_mod.SHOW_REQUEST_PATH.exists() and time.monotonic()<deadline: time.sleep(.02)\\n"
                "assert app.cfg_mod.SHOW_REQUEST_PATH.read_text(encoding='utf-8')=='wake'\\n"
                "app._release_single_instance()\\nprint('designated-ok',flush=True)\\n"
            )
            contender_code = setup + (
                "assert app._acquire_launch_gate(wait_seconds=5)\\n"
                "try: acquired=app._acquire_single_instance()\\n"
                "finally: app._release_launch_gate()\\n"
                "assert acquired is False\\n"
                "app.cfg_mod.SHOW_REQUEST_PATH.write_text('wake',encoding='utf-8')\\n"
                "print('contender-ok',flush=True)\\n"
            )
            designated = subprocess.Popen(
                [sys.executable,'-c',designated_code], cwd={str(REPO_ROOT)!r},
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            contender = subprocess.Popen(
                [sys.executable,'-c',contender_code], cwd={str(REPO_ROOT)!r},
                env=os.environ.copy(), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            assert handoff.wait_for_ready(
                designated, timeout=5,
                release_primary=app._release_single_instance,
                claim_is_exclusive=app._renderer_child_holds_primary,
            ), repr(handoff.last_error)
            if sys.platform == 'win32' and sys.prefix != sys.base_prefix:
                assert handoff.child_pid != designated.pid
            handoff.close(); app._release_launch_gate()
            co, ce = contender.communicate(timeout=6)
            do, de = designated.communicate(timeout=6)
            assert contender.returncode == 0, ce
            assert designated.returncode == 0, de
            assert not ce.strip() and not de.strip(), ce + de
            assert 'contender-ok' in co and 'designated-ok' in do
            assert wake.read_text(encoding='utf-8') == 'wake'
            print('prepared-three-process-clean')
            """
        )
        self.assert_child_passed(completed)

    def test_post_prepared_timeout_reclaims_parent_lock(self):
        instance = f"SpeakrPreparedTimeout-{uuid.uuid4()}"
        completed = _run_python(
            f"""
            import os, subprocess, sys, time
            from speakr import app
            app._SINGLE_INSTANCE_MUTEX_NAME = {instance!r}
            assert app._acquire_single_instance()
            handoff = app._RendererHandoffParent(); env = os.environ.copy()
            env.update(handoff.environment())
            env[app._SOFTWARE_RELAUNCH_GUARD_ENV] = '1'
            env[app._SOFTWARE_RELAUNCH_PARENT_ENV] = str(os.getpid())
            code = (
                "import time\\nfrom speakr import app\\n"
                + "app._SINGLE_INSTANCE_MUTEX_NAME=" + repr({instance!r}) + "\\n"
                + "s=app._RendererHandoffChild.from_environment()\\n"
                + "def acquire_primary(wait_seconds):\\n"
                + " assert app._acquire_single_instance(wait_seconds=wait_seconds)\\n"
                + " print('claimed',flush=True); time.sleep(30)\\n"
                + " return True\\n"
                + "s.prepare('legacy',timeout=5,acquire_primary=acquire_primary,"
                + "release_primary=app._release_single_instance)\\n"
            )
            child = subprocess.Popen(
                [sys.executable,'-c',code], cwd={str(REPO_ROOT)!r}, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            assert handoff.wait_for_ready(
                child, timeout=2,
                release_primary=app._release_single_instance,
                claim_is_exclusive=app._renderer_child_holds_primary,
            ) is False
            if sys.platform == 'win32' and sys.prefix != sys.base_prefix:
                assert handoff.child_pid != child.pid
            handoff.stop_child(child)
            handoff.close()
            out, err = child.communicate(timeout=5)
            assert 'claimed' in out and not err.strip(), err
            assert app._acquire_single_instance(wait_seconds=3)
            app._release_single_instance()
            print('prepared-timeout-reclaimed')
            """
        )
        self.assert_child_passed(completed)

    @staticmethod
    def _app_shell():
        app = SpeakrApp.__new__(SpeakrApp)
        app.log = mock.Mock(); app.config = mock.Mock()
        app.config.get.return_value = "right ctrl"
        app._core_started = False; app._fallback_active = False
        app._qt_frontend = None; app._renderer_handoff = None
        app._start_core = mock.Mock(); app._start_legacy_interface = mock.Mock()
        return app

    def test_frontend_commit_orders_prepare_before_core_and_aborts_once(self):
        app = SpeakrApp.__new__(SpeakrApp)
        app.log = mock.Mock(); app.interface_state = mock.Mock()
        app.webui = mock.Mock(port=None); app.open_panel = mock.Mock(return_value=True)
        app.tray = mock.Mock(); app._start_core = mock.Mock()
        events = []; handoff = mock.Mock(attempted=False)
        def prepared(frontend, **callbacks):
            self.assertEqual(
                callbacks["timeout"],
                app_module._SINGLE_INSTANCE_HANDOFF_SECONDS,
            )
            self.assertIs(
                callbacks["acquire_primary"],
                app_module._acquire_single_instance,
            )
            self.assertIs(
                callbacks["release_primary"],
                app_module._release_single_instance,
            )
            events.append(("prepared", frontend))
            return True
        handoff.prepare.side_effect = prepared
        app._renderer_handoff = handoff
        app.tray.run.side_effect = lambda *, setup: setup(mock.Mock())
        with mock.patch.object(app_module, "_instance_lock", None):
            app._start_legacy_interface()
        self.assertEqual(events, [("prepared", "legacy")])
        app._start_core.assert_called_once_with()

        rejected = self._app_shell(); rejected._renderer_handoff = mock.Mock()
        rejected._renderer_handoff.attempted = True
        error = qt_ui.QtUnavailable("prepared takeover rejected")
        with mock.patch.object(
            qt_ui, "_prefer_software_renderer", return_value=True
        ), mock.patch.object(qt_ui, "run_native_ui", side_effect=error):
            rejected.start()
        rejected._start_core.assert_not_called()
        rejected._start_legacy_interface.assert_not_called()

        before_prepared = self._app_shell()
        before_prepared._renderer_handoff = mock.Mock(attempted=False)
        with mock.patch.object(
            qt_ui, "_prefer_software_renderer", return_value=True
        ), mock.patch.object(qt_ui, "run_native_ui", side_effect=error):
            before_prepared.start()
        before_prepared._start_legacy_interface.assert_called_once_with()

        blocked = self._app_shell()
        retryable = qt_ui.QtUnavailable("runtime could not be stopped")
        retryable.renderer_retryable = True
        with mock.patch.object(
            qt_ui, "_prefer_software_renderer", return_value=False
        ), mock.patch.object(
            qt_ui, "run_native_ui", side_effect=retryable
        ), mock.patch.object(
            app_module, "_relaunch_with_software_renderer", return_value=True
        ):
            blocked.start()
        blocked._start_core.assert_not_called()
        blocked._start_legacy_interface.assert_not_called()

    def test_relaunch_success_and_failed_transfer_preserve_ownership_rules(self):
        logger = mock.Mock(); process = mock.Mock(pid=42)
        process.poll.return_value = None
        handoff = mock.Mock(); handoff.environment.return_value = {}
        handoff.primary_released = False
        def succeed(
            _process, *, timeout, release_primary, claim_is_exclusive
        ):
            release_primary(); handoff.primary_released = True; return True
        handoff.wait_for_ready.side_effect = succeed
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            app_module, "_RendererHandoffParent", return_value=handoff
        ), mock.patch.object(
            app_module.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            app_module, "_acquire_launch_gate", return_value=True
        ), mock.patch.object(
            app_module, "_release_launch_gate"
        ) as release_gate, mock.patch.object(
            app_module, "_release_single_instance"
        ) as release_primary:
            self.assertTrue(app_module._relaunch_with_software_renderer(logger))
        release_primary.assert_called_once_with(); release_gate.assert_called_once_with()

        failed = mock.Mock(); failed.environment.return_value = {}
        failed.primary_released = False
        failed.stop_child.return_value = True
        def fail(
            _process, *, timeout, release_primary, claim_is_exclusive
        ):
            release_primary(); failed.primary_released = True; return False
        failed.wait_for_ready.side_effect = fail
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            app_module, "_RendererHandoffParent", return_value=failed
        ), mock.patch.object(
            app_module.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            app_module, "_acquire_launch_gate", return_value=True
        ), mock.patch.object(
            app_module, "_release_launch_gate"
        ) as failed_gate, mock.patch.object(
            app_module, "_release_single_instance"
        ), mock.patch.object(
            app_module, "_acquire_single_instance", return_value=True
        ) as reacquire:
            self.assertFalse(app_module._relaunch_with_software_renderer(logger))
        failed.stop_child.assert_called_once_with(
            process,
        )
        reacquire.assert_called_once_with(
            wait_seconds=app_module._SINGLE_INSTANCE_HANDOFF_SECONDS
        )
        failed_gate.assert_not_called()

        unresolved = mock.Mock(); unresolved.environment.return_value = {}
        unresolved.primary_released = False
        unresolved.stop_child.return_value = False
        def leave_runtime(_process, **callbacks):
            callbacks["release_primary"]()
            unresolved.primary_released = True
            return False
        unresolved.wait_for_ready.side_effect = leave_runtime
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            app_module, "_RendererHandoffParent", return_value=unresolved
        ), mock.patch.object(
            app_module.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            app_module, "_acquire_launch_gate", return_value=True
        ), mock.patch.object(
            app_module, "_release_launch_gate"
        ) as unresolved_gate, mock.patch.object(
            app_module, "_release_single_instance"
        ), mock.patch.object(
            app_module, "_acquire_single_instance"
        ) as unsafe_reacquire:
            self.assertTrue(app_module._relaunch_with_software_renderer(logger))
        unsafe_reacquire.assert_not_called()
        unresolved_gate.assert_not_called()
        self.assertTrue(
            any(
                "suppressing a second frontend" in str(call)
                for call in logger.error.call_args_list
            )
        )

    def test_guarded_main_builds_frontend_without_touching_wake_or_primary(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "show.request"
            request.write_text("fresh", encoding="utf-8")
            handoff = mock.Mock(); application = mock.Mock()
            with mock.patch.object(
                app_module._RendererHandoffChild,
                "from_environment",
                return_value=handoff,
            ), mock.patch.object(
                app_module, "_acquire_single_instance"
            ) as acquire, mock.patch.object(
                app_module.cfg_mod, "SHOW_REQUEST_PATH", request
            ), mock.patch.object(
                app_module, "SpeakrApp", return_value=application
            ):
                app_module.main()
            acquire.assert_not_called()
            self.assertIs(application._renderer_handoff, handoff)
            application.start.assert_called_once_with()
            self.assertEqual(request.read_text(encoding="utf-8"), "fresh")

    def test_stop_child_never_throws_when_terminate_and_kill_fail(self):
        process = mock.Mock(); process.poll.return_value = None
        process.terminate.side_effect = OSError("denied")
        process.kill.side_effect = OSError("denied")
        process.wait.side_effect = subprocess.TimeoutExpired("child", 2)
        self.assertFalse(handoff_module._stop_process(process))
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
