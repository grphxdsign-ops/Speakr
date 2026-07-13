"""Path-safe, deterministic source identity for local verification evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SOURCE_IDENTITY_SCHEMA = 1
FINGERPRINT_ALGORITHM = "sha256:git-head-diff+relevant-untracked-v1"

_UNTRACKED_SOURCE_ROOTS = ("speakr", "tests", "scripts", "assets")
_UNTRACKED_SOURCE_SUFFIXES = frozenset(
    {
        ".bat",
        ".cfg",
        ".css",
        ".html",
        ".ico",
        ".ini",
        ".iss",
        ".js",
        ".json",
        ".md",
        ".mjs",
        ".plist",
        ".png",
        ".ps1",
        ".py",
        ".pyi",
        ".qml",
        ".qmltypes",
        ".sh",
        ".svg",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
_UNTRACKED_SOURCE_NAMES = frozenset({"qmldir"})
_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        ".venv-gguf",
        ".venv-train",
        "__pycache__",
        "build",
        "dist",
    }
)
_PRIVATE_RUNTIME_NAMES = frozenset(
    {
        ".speakr.lock",
        "config.json",
        "dictionary.txt",
        "learned_words.json",
        "panel.url",
        "show.request",
        "speakr.log",
    }
)
_TRACKED_SOURCE_PATHS = (
    ".",
    ":(exclude)config.json",
    ":(exclude)speakr.log",
    ":(exclude).speakr.lock",
    ":(exclude)panel.url",
    ":(exclude)show.request",
    ":(exclude)dictionary.txt",
    ":(exclude)learned_words.json",
    ":(exclude,glob)build/**",
    ":(exclude,glob)dist/**",
    ":(exclude,glob).venv/**",
    ":(exclude,glob).venv-*/**",
    ":(exclude,glob)**/__pycache__/**",
    ":(exclude,glob)*.spec",
    ":(exclude)icon.ico",
    ":(exclude,glob)training/*.jsonl",
    ":(exclude,glob)training/adapter/**",
    ":(exclude,glob)training/adapter_final/**",
    ":(exclude,glob)training/merged/**",
    ":(exclude,glob)training/gguf/**",
    ":(exclude,glob)training/smoke_out/**",
)


class SourceIdentityError(RuntimeError):
    """Raised when a repository cannot provide trustworthy source identity."""


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        operation = arguments[0] if arguments else "command"
        raise SourceIdentityError(
            f"git {operation} failed with exit code {completed.returncode}"
        )
    return completed.stdout


def _split_nul(value: bytes) -> list[bytes]:
    return [item for item in value.split(b"\0") if item]


def _is_relevant_untracked(path_bytes: bytes) -> bool:
    text = path_bytes.decode("utf-8", errors="surrogateescape").replace("\\", "/")
    parts = tuple(part.casefold() for part in text.split("/") if part)
    if not parts or parts[0] not in _UNTRACKED_SOURCE_ROOTS:
        return False
    if any(part in _EXCLUDED_PARTS for part in parts):
        return False
    name = parts[-1]
    if name in _PRIVATE_RUNTIME_NAMES:
        return False
    suffix = Path(name).suffix.casefold()
    return suffix in _UNTRACKED_SOURCE_SUFFIXES or name in _UNTRACKED_SOURCE_NAMES


def _hash_untracked_file(digest, root: Path, path_bytes: bytes) -> None:
    relative_text = path_bytes.decode("utf-8", errors="surrogateescape")
    candidate = root / Path(relative_text)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise SourceIdentityError("relevant untracked source escaped repository") from exc

    digest.update(b"untracked\0")
    digest.update(path_bytes.replace(b"\\", b"/"))
    digest.update(b"\0")
    if candidate.is_symlink():
        try:
            target = os.readlink(candidate)
        except OSError as exc:
            raise SourceIdentityError("could not read relevant source link") from exc
        digest.update(b"symlink\0")
        digest.update(os.fsencode(target))
        digest.update(b"\0")
        return
    if not candidate.is_file():
        raise SourceIdentityError("relevant untracked source was not a regular file")
    digest.update(b"file\0")
    try:
        with candidate.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise SourceIdentityError("could not read relevant untracked source") from exc
    digest.update(b"\0")


def collect_source_identity(root: Path) -> dict[str, Any]:
    """Return source identity without exposing repository or file paths.

    The HEAD commit is immutable. The second digest binds staged and unstaged
    tracked changes plus source-like, non-ignored untracked files under the
    product, test, and verification-script roots. Ignored build/runtime/private
    files never enter the digest or metadata.
    """

    root = Path(root).resolve()
    head_sha = _git(root, "rev-parse", "--verify", "HEAD").decode(
        "ascii", errors="strict"
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise SourceIdentityError("HEAD did not resolve to a full commit SHA")

    tracked_diff = _git(
        root,
        "-c",
        "core.quotepath=false",
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "HEAD",
        "--",
        *_TRACKED_SOURCE_PATHS,
    )
    tracked_names = _split_nul(
        _git(
            root,
            "diff",
            "--name-only",
            "-z",
            "HEAD",
            "--",
            *_TRACKED_SOURCE_PATHS,
        )
    )
    untracked = sorted(
        path
        for path in _split_nul(
            _git(
                root,
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *_UNTRACKED_SOURCE_ROOTS,
            )
        )
        if _is_relevant_untracked(path)
    )

    digest = hashlib.sha256()
    digest.update(FINGERPRINT_ALGORITHM.encode("ascii"))
    digest.update(b"\0head\0")
    digest.update(head_sha.encode("ascii"))
    digest.update(b"\0tracked-diff\0")
    digest.update(tracked_diff)
    digest.update(b"\0")
    for path_bytes in untracked:
        _hash_untracked_file(digest, root, path_bytes)

    tracked_change_count = len(tracked_names)
    untracked_count = len(untracked)
    clean = tracked_change_count == 0 and untracked_count == 0
    return {
        "schema_version": SOURCE_IDENTITY_SCHEMA,
        "head_sha": head_sha,
        "working_tree_fingerprint": f"sha256:{digest.hexdigest()}",
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "working_tree": "clean" if clean else "dirty",
        "clean": clean,
        "tracked_change_count": tracked_change_count,
        "relevant_untracked_source_count": untracked_count,
    }


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    """Replace a JSON artifact atomically so old PASS cannot survive a tear."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
