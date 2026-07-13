"""Opt-in offline core-readiness proof for packaged release smoke tests.

The frozen entry point installs the socket guard before importing any Speakr
application modules.  Normal launches do not set ``CORE_PROOF_PATH_ENV`` and
therefore do not patch sockets, alter environment variables, start timers, or
write receipts.

The success receipt is intentionally a fixed vocabulary.  It contains no
audio, transcript, selection, clipboard, screen, window-title, configuration,
model name, username, or machine-path data.
"""

from __future__ import annotations

import errno
import ipaddress
import json
import os
import secrets
import socket
import threading
from pathlib import Path
from typing import Any


CORE_PROOF_PATH_ENV = "SPEAKR_RELEASE_CORE_PROOF_PATH"
CORE_PROOF_SCHEMA = 1
CORE_PROOF_TIMEOUT_SECONDS = 300.0

_OFFLINE_ENVIRONMENT = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def core_proof_requested() -> bool:
    return bool(str(os.environ.get(CORE_PROOF_PATH_ENV, "")).strip())


def _host_is_loopback(host: object) -> bool:
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    candidate = str(host or "").strip().casefold()
    if candidate == "localhost":
        return True
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(mapped is not None and mapped.is_loopback)


def _address_is_local(family: int, address: object) -> bool:
    """Return whether a socket destination is local-only.

    Unix-domain sockets never leave the machine.  Internet sockets require a
    literal loopback address or the special ``localhost`` name; arbitrary DNS
    names are rejected before resolution.
    """

    if family not in (socket.AF_INET, socket.AF_INET6):
        return True
    if not isinstance(address, tuple) or not address:
        return False
    return _host_is_loopback(address[0])


class LoopbackSocketGuard:
    """Process-wide Python socket guard used only by release proof mode."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocked_attempts = 0
        self._active = False
        self._originals: dict[str, Any] = {}
        self._original_getaddrinfo = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def blocked_attempts(self) -> int:
        with self._lock:
            return self._blocked_attempts

    def _blocked(self) -> None:
        with self._lock:
            self._blocked_attempts += 1

    def _require_local(self, sock: socket.socket, address: object) -> None:
        if _address_is_local(sock.family, address):
            return
        self._blocked()
        raise PermissionError(
            errno.EACCES,
            "release proof blocked a non-loopback socket destination",
        )

    def install(self) -> bool:
        if self._active:
            return True

        socket_type = socket.socket
        self._originals = {
            "connect": socket_type.connect,
            "connect_ex": socket_type.connect_ex,
            "sendto": socket_type.sendto,
        }
        self._original_getaddrinfo = socket.getaddrinfo
        if hasattr(socket_type, "sendmsg"):
            self._originals["sendmsg"] = socket_type.sendmsg

        guard = self

        def guarded_connect(sock, address):
            guard._require_local(sock, address)
            return guard._originals["connect"](sock, address)

        def guarded_connect_ex(sock, address):
            try:
                guard._require_local(sock, address)
            except PermissionError:
                return errno.EACCES
            return guard._originals["connect_ex"](sock, address)

        def guarded_sendto(sock, data, *args):
            if not args:
                raise TypeError("sendto requires a destination address")
            address = args[-1]
            guard._require_local(sock, address)
            return guard._originals["sendto"](sock, data, *args)

        def guarded_getaddrinfo(host, port, *args, **kwargs):
            # ``None`` is used for passive/local bind discovery and is not a
            # remote destination.  Every named destination must already be a
            # literal loopback address or exactly localhost, so rejected names never
            # reach the operating system's DNS resolver.
            if host is not None and not _host_is_loopback(host):
                guard._blocked()
                raise PermissionError(
                    errno.EACCES,
                    "release proof blocked non-loopback name resolution",
                )
            return guard._original_getaddrinfo(host, port, *args, **kwargs)

        socket_type.connect = guarded_connect
        socket_type.connect_ex = guarded_connect_ex
        socket_type.sendto = guarded_sendto
        socket.getaddrinfo = guarded_getaddrinfo

        if "sendmsg" in self._originals:
            def guarded_sendmsg(sock, buffers, *args, **kwargs):
                address = kwargs.get("address")
                if address is None and len(args) >= 3:
                    address = args[2]
                if address is not None:
                    guard._require_local(sock, address)
                return guard._originals["sendmsg"](
                    sock, buffers, *args, **kwargs
                )

            socket_type.sendmsg = guarded_sendmsg

        self._active = True
        return True

    def restore_for_tests(self) -> None:
        """Restore class methods after a focused unit test.

        Release processes keep the guard installed until process exit.
        """

        if not self._active:
            return
        socket_type = socket.socket
        for name, original in self._originals.items():
            setattr(socket_type, name, original)
        if self._original_getaddrinfo is not None:
            socket.getaddrinfo = self._original_getaddrinfo
        self._originals.clear()
        self._original_getaddrinfo = None
        self._active = False


class CoreReleaseProof:
    """Join real model and formatter readiness into one sanitized receipt."""

    def __init__(
        self,
        destination: Path,
        guard: LoopbackSocketGuard,
        *,
        timeout_seconds: float = CORE_PROOF_TIMEOUT_SECONDS,
    ) -> None:
        self._destination = Path(destination)
        self._guard = guard
        self._timeout_seconds = max(0.01, float(timeout_seconds))
        self._lock = threading.Lock()
        self._app = None
        self._timer: threading.Timer | None = None
        self._model_ready = False
        self._formatter_ready = False
        self._cleanup_path = ""
        self._finished = False

    def attach(self, app: object) -> bool:
        """Validate proof-only preconditions and arm the bounded smoke run."""

        config = getattr(app, "config", None)
        formatting = (
            config.get("formatting", default={})
            if config is not None and hasattr(config, "get")
            else {}
        ) or {}
        valid = (
            self._guard.active
            and all(os.environ.get(key) == value for key, value in _OFFLINE_ENVIRONMENT.items())
            and isinstance(formatting, dict)
            and formatting.get("enabled", True) is True
            and formatting.get("use_ollama", True) is False
            and formatting.get("autostart_ollama", True) is False
        )
        if not valid:
            self._finish_without_receipt(app)
            return False

        with self._lock:
            if self._finished:
                return False
            self._app = app
            timer = threading.Timer(self._timeout_seconds, self._timeout)
            timer.daemon = True
            self._timer = timer
            timer.start()
        return True

    def note_model_ready(self) -> None:
        with self._lock:
            if self._finished:
                return
            self._model_ready = True
        self._complete_if_ready()

    def note_formatter_ready(self, cleanup_path: object) -> None:
        with self._lock:
            if self._finished:
                return
            self._formatter_ready = True
            self._cleanup_path = str(cleanup_path or "").strip().casefold()
        self._complete_if_ready()

    def fail(self) -> None:
        with self._lock:
            app = self._app
        self._finish_without_receipt(app)

    def cancel(self) -> None:
        with self._lock:
            self._finished = True
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _timeout(self) -> None:
        with self._lock:
            app = self._app
        self._finish_without_receipt(app)

    def _complete_if_ready(self) -> None:
        with self._lock:
            if (
                self._finished
                or not self._model_ready
                or not self._formatter_ready
            ):
                return
            app = self._app
            success = (
                self._cleanup_path == "rules"
                and self._guard.active
                and self._guard.blocked_attempts == 0
                and self._write_success_receipt()
            )
            self._finished = True
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
        # A missing receipt is an intentional hard failure for the caller,
        # but the packaged application still exits cleanly in either case.
        self._request_quit(app)
        if not success:
            return

    def _finish_without_receipt(self, app: object) -> None:
        with self._lock:
            if self._finished:
                return
            self._finished = True
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
        self._request_quit(app)

    @staticmethod
    def _request_quit(app: object) -> None:
        quit_app = getattr(app, "quit", None)
        if callable(quit_app):
            quit_app()

    def _write_success_receipt(self) -> bool:
        payload = {
            "blocked_attempts": 0,
            "cleanup_path": "rules",
            "core_ready": True,
            "guard_active": True,
            "model_ready": True,
            "model_source": "preseeded_local",
            "network_policy": "loopback_only",
            "offline_mode": True,
            "ollama": "disabled",
            "schema": CORE_PROOF_SCHEMA,
        }
        destination = self._destination
        temporary = destination.with_name(
            f".{destination.name}.{secrets.token_hex(8)}.tmp"
        )
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(
                descriptor, "w", encoding="utf-8", newline="\n"
            ) as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            return True
        except (OSError, TypeError, ValueError):
            try:
                temporary.unlink()
            except OSError:
                pass
            return False


_active_proof: CoreReleaseProof | None = None


def install_core_proof_from_environment() -> CoreReleaseProof | None:
    """Install release proof controls before application-module imports."""

    global _active_proof
    raw_path = str(os.environ.get(CORE_PROOF_PATH_ENV, "")).strip()
    if not raw_path:
        return None
    if _active_proof is not None:
        return _active_proof
    for key, value in _OFFLINE_ENVIRONMENT.items():
        os.environ[key] = value
    guard = LoopbackSocketGuard()
    guard.install()
    _active_proof = CoreReleaseProof(Path(raw_path).expanduser(), guard)
    return _active_proof


def active_core_proof() -> CoreReleaseProof | None:
    return _active_proof


__all__ = [
    "CORE_PROOF_PATH_ENV",
    "CORE_PROOF_SCHEMA",
    "CoreReleaseProof",
    "LoopbackSocketGuard",
    "active_core_proof",
    "core_proof_requested",
    "install_core_proof_from_environment",
]
