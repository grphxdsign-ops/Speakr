"""Bounded local ownership transfer for a fresh Qt renderer process."""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


GUARD_ENV = "SPEAKR_QT_SOFTWARE_RELAUNCHED"
PARENT_ENV = "SPEAKR_QT_RELAUNCH_PARENT_PID"
ADDRESS_ENV = "SPEAKR_QT_RELAUNCH_ADDRESS"
TOKEN_ENV = "SPEAKR_QT_RELAUNCH_AUTH"
NONCE_ENV = "SPEAKR_QT_RELAUNCH_NONCE"
_POLL = 0.05
_PHASES = {"prepared", "released", "claimed", "ack", "complete", "rejected"}


def is_guarded():
    return os.environ.get(GUARD_ENV, "").strip().lower() in {"1", "true", "yes"}


def _parent_pid():
    if not is_guarded():
        return None
    try:
        pid = int(os.environ.get(PARENT_ENV, ""))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 and pid != os.getpid() else None


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("renderer handoff timed out")
    return remaining


def _sharing_error(error):
    return isinstance(error, PermissionError) or getattr(error, "winerror", 0) in {
        5, 32, 33,
    }


class _Channel:
    def __init__(self, directory, nonce, token):
        self.directory = Path(directory)
        self.nonce = nonce
        self.token = token

    def _path(self, owner):
        return self.directory / f"{owner}.json"

    def send(self, owner, phase, deadline, **values):
        path = self._path(owner)
        payload = json.dumps(
            {"phase": phase, "nonce": self.nonce, "token": self.token, **values},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        while True:
            remaining = _remaining(deadline)
            if not self.directory.is_dir():
                raise OSError("renderer handoff directory is unavailable")
            temporary = path.with_name(
                f".{path.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp"
            )
            descriptor = None
            try:
                descriptor = os.open(
                    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(descriptor, "wb") as handle:
                    descriptor = None
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
                return
            except OSError as exc:
                if not _sharing_error(exc):
                    raise
                time.sleep(min(_POLL, remaining))
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def receive(self, owner, phase, deadline, *, alive=None):
        path = self._path(owner)
        while True:
            if alive is not None and not alive():
                raise ChildProcessError("renderer child exited during handoff")
            remaining = _remaining(deadline)
            try:
                payload = path.read_bytes()
                if not 0 < len(payload) <= 4096:
                    raise ValueError("renderer handoff record has an invalid size")
                record = json.loads(payload)
                if not isinstance(record, dict):
                    raise ValueError("renderer handoff record is not a mapping")
                if (
                    record.get("nonce") != self.nonce
                    or record.get("token") != self.token
                ):
                    raise ValueError("renderer handoff authentication failed")
                current = record.get("phase")
                if current == phase:
                    return record
                if current not in _PHASES or current == "rejected":
                    raise ValueError(f"renderer handoff stopped in phase {current!r}")
            except FileNotFoundError:
                if not self.directory.is_dir():
                    raise OSError("renderer handoff directory was closed")
            except OSError as exc:
                if not _sharing_error(exc):
                    raise
            time.sleep(min(_POLL, remaining))


def _stop_process(process):
    if process is None:
        return True
    try:
        if process.poll() is not None:
            return True
        process.terminate()
        process.wait(timeout=2)
        return True
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    try:
        process.kill()
        process.wait(timeout=2)
        return True
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


class _Runtime:
    """Pinned authenticated runtime; Windows launchers may have another PID."""

    def __init__(self, pid, launcher):
        self.launcher = launcher
        self.handle = self.api = None
        if sys.platform != "win32":
            if pid != int(launcher.pid):
                raise ValueError("renderer child PID does not match Popen")
            return

        import ctypes
        from ctypes import wintypes

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
        ]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [
            wintypes.HANDLE, wintypes.DWORD
        ]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.TerminateProcess.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.OpenProcess(0x00100001, False, pid)
        if not self.handle:
            raise OSError(
                ctypes.get_last_error(), "could not pin renderer runtime"
            )

    def _exited(self, timeout):
        if self.handle is None:
            return self.launcher.poll() is not None
        result = int(self.api.WaitForSingleObject(self.handle, timeout))
        if result not in {0, 258}:
            raise OSError("could not query renderer runtime")
        return result == 0

    def alive(self):
        return not self._exited(0)

    def stop(self):
        if self.handle is None:
            return _stop_process(self.launcher)
        if self._exited(0):
            return True
        # REJECT is already visible, so denial still gets a cooperative wait.
        self.api.TerminateProcess(self.handle, 1)
        return self._exited(2000)

    def close(self):
        if self.handle is not None:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _windows_temp_path():
    """Read Windows temp without tempfile's create/write probe."""

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    function = getattr(kernel32, "GetTempPath2W", None) or kernel32.GetTempPathW
    function.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    function.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = int(function(len(buffer), buffer))
    if not 0 < length < len(buffer):
        raise OSError("Windows did not provide a bounded temporary path")
    return buffer.value


def _local_temp_root():
    if sys.platform != "win32":
        root = Path("/tmp")
        if not root.is_dir():
            raise OSError("local handoff storage is unavailable")
        return root

    import ctypes

    raw = _windows_temp_path()
    if raw.startswith(("\\\\", "//")):
        raise OSError("handoff temp cannot use a remote share")
    root = Path(os.path.abspath(raw))
    drive, _ = os.path.splitdrive(str(root))
    if not drive or ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") not in {3, 6}:
        raise OSError("handoff temp requires a local fixed drive")
    current = Path(root.anchor)
    status = os.lstat(current)
    for part in root.parts[1:]:
        current /= part
        status = os.lstat(current)
        if getattr(status, "st_file_attributes", 0) & 0x400:
            raise OSError("handoff temp contains a reparse point")
    if not stat.S_ISDIR(status.st_mode):
        raise OSError("handoff temp is not a directory")
    return root


def _validated_directory(address):
    root = _local_temp_root()
    candidate = Path(os.path.abspath(address))
    if candidate.parent != root or not candidate.name.startswith("speakr-renderer-"):
        raise OSError("handoff address is outside local temp")
    status = os.lstat(candidate)
    if getattr(status, "st_file_attributes", 0) & 0x400:
        raise OSError("handoff directory is a reparse point")
    if not stat.S_ISDIR(status.st_mode):
        raise OSError("handoff address is not a directory")
    return candidate


class RendererHandoffParent:
    def __init__(self):
        self.nonce = secrets.token_hex(16)
        self.token = secrets.token_urlsafe(32)
        self._temporary = tempfile.TemporaryDirectory(
            prefix="speakr-renderer-", dir=_local_temp_root()
        )
        self.address = self._temporary.name
        if os.name == "posix":
            os.chmod(self.address, 0o700)
        self._channel = _Channel(self.address, self.nonce, self.token)
        self._runtime = None
        self.child_pid = self.last_error = None
        self.primary_released = False

    def environment(self):
        return {ADDRESS_ENV: self.address, TOKEN_ENV: self.token, NONCE_ENV: self.nonce}

    def wait_for_ready(
        self, launcher, *, timeout, release_primary, claim_is_exclusive
    ):
        deadline = time.monotonic() + max(0.0, float(timeout))
        preflight_alive = None
        if sys.platform != "win32":
            preflight_alive = lambda: launcher.poll() is None
        try:
            prepared = self._channel.receive(
                "child", "prepared", deadline, alive=preflight_alive
            )
            pid = prepared.get("pid")
            if (
                not isinstance(pid, int)
                or pid <= 0
                or prepared.get("frontend") not in {"native", "legacy"}
            ):
                raise ValueError("renderer child sent invalid PREPARED")
            self._runtime = _Runtime(pid, launcher)
            self.child_pid = pid
            if not self._runtime.alive():
                raise ChildProcessError("renderer child exited before release")
            release_primary()
            self.primary_released = True
            self._channel.send(
                "parent", "released", deadline, parent_pid=os.getpid()
            )
            claimed = self._channel.receive(
                "child", "claimed", deadline, alive=self._runtime.alive
            )
            if claimed.get("pid") != pid or not claim_is_exclusive():
                raise ValueError("renderer child did not retain primary")
            self._channel.send("parent", "ack", deadline, parent_pid=os.getpid())
            complete = self._channel.receive(
                "child", "complete", deadline, alive=self._runtime.alive
            )
            if complete.get("pid") != pid:
                raise ValueError("renderer child completion PID changed")
            return True
        except (ChildProcessError, OSError, TimeoutError, ValueError) as exc:
            self.last_error = exc
            try:
                self._channel.send(
                    "parent", "rejected", time.monotonic() + 0.5,
                    parent_pid=os.getpid(),
                )
            except (OSError, TimeoutError):
                pass
            return False

    def stop_child(self, launcher):
        try:
            return (
                self._runtime.stop()
                if self._runtime is not None
                else _stop_process(launcher)
            )
        except OSError:
            return False

    def close(self):
        if self._runtime is not None:
            self._runtime.close()
        try:
            self._temporary.cleanup()
        except OSError:
            pass


class RendererHandoffChild:
    def __init__(self, address, token, nonce, parent):
        self._channel = _Channel(address, nonce, token)
        self.parent_pid = parent
        self._attempted = False

    @property
    def attempted(self):
        return self._attempted

    @classmethod
    def from_environment(cls):
        if not is_guarded():
            return None
        address = os.environ.get(ADDRESS_ENV, "").strip()
        nonce = os.environ.get(NONCE_ENV, "").strip()
        token = os.environ.get(TOKEN_ENV, "").strip()
        parent = _parent_pid()
        if not address or not nonce or len(token) < 32 or parent is None:
            return None
        try:
            address = _validated_directory(address)
        except OSError:
            return None
        return cls(address, token, nonce, parent)

    def prepare(
        self, frontend, *, timeout, acquire_primary, release_primary
    ):
        if self._attempted or frontend not in {"native", "legacy"}:
            return False
        self._attempted = True
        deadline = time.monotonic() + max(0.0, float(timeout))
        acquired = accepted = False
        try:
            self._channel.send(
                "child", "prepared", deadline,
                pid=os.getpid(), frontend=frontend,
            )
            released = self._channel.receive("parent", "released", deadline)
            if released.get("parent_pid") != self.parent_pid:
                return False
            acquired = acquire_primary(wait_seconds=_remaining(deadline))
            if not acquired:
                return False
            self._channel.send("child", "claimed", deadline, pid=os.getpid())
            ack = self._channel.receive("parent", "ack", deadline)
            if ack.get("parent_pid") != self.parent_pid:
                return False
            self._channel.send("child", "complete", deadline, pid=os.getpid())
            accepted = True
            return True
        except (OSError, TimeoutError, ValueError):
            return False
        finally:
            if acquired and not accepted:
                release_primary()

    def close(self):
        self._attempted = True
