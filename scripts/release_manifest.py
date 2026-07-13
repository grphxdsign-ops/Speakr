#!/usr/bin/env python3
"""Create and verify sanitized evidence manifests for exact release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_release_core_receipt import (
    validate_receipt as validate_core_receipt,
)
from scripts.validate_release_receipt import (
    ALLOWED_FIELDS as UI_ALLOWED_FIELDS,
    EXACT_FIELDS as UI_EXACT_FIELDS,
    EXPECTED_KEYS as UI_EXPECTED_KEYS,
)


SCHEMA = 1
PLATFORMS = {"windows", "macos"}
ARCHITECTURES = {"x86_64", "arm64"}
SIGNATURE_KINDS = {"authenticode", "developer_id", "ad_hoc", "unsigned"}
_SHA = re.compile(r"^[0-9a-f]{40}$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,79}$")
_TAG = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[-.][0-9A-Za-z.-]+)?$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency_lock_sha256(path: Path) -> str:
    """Hash the checked-in lock content independent of checkout line endings."""

    text = path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _ui_receipt_errors(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["native receipt must be a JSON object"]
    errors = []
    if set(payload) != UI_EXPECTED_KEYS:
        errors.append("native receipt does not use the exact schema")
    for key, expected in UI_EXACT_FIELDS.items():
        if payload.get(key) != expected:
            errors.append(f"native receipt has invalid {key}")
    for key, allowed in UI_ALLOWED_FIELDS.items():
        if payload.get(key) not in allowed:
            errors.append(f"native receipt has invalid {key}")
    if type(payload.get("native_material_available")) is not bool:
        errors.append("native receipt has invalid native_material_available")
    return errors


def _safe_public_identity(value: str, fallback: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return fallback
    if len(candidate) > 300 or "\n" in candidate or "\r" in candidate:
        raise ValueError("signer evidence must be a single line of at most 300 characters")
    return candidate


def create_manifest(
    *,
    artifact: Path,
    dependency_lock: Path,
    native_receipt: Path,
    core_receipt: Path,
    source_sha: str,
    tag: str,
    version: str,
    platform: str,
    architecture: str,
    signed: bool,
    notarized: bool,
    signature_kind: str,
    signer_identity: str,
    signer_team: str,
) -> dict[str, object]:
    source_sha = source_sha.strip().casefold()
    tag = tag.strip()
    if not _SHA.fullmatch(source_sha):
        raise ValueError("source SHA must be a full 40-character lowercase commit SHA")
    if not _VERSION.fullmatch(version):
        raise ValueError("release version has an invalid format")
    if tag and not _TAG.fullmatch(tag):
        raise ValueError("release tag has an invalid format")
    if platform not in PLATFORMS:
        raise ValueError("unsupported release platform")
    if architecture not in ARCHITECTURES:
        raise ValueError("unsupported release architecture")
    if platform == "windows" and architecture != "x86_64":
        raise ValueError("Windows release architecture must be x86_64")
    if platform == "macos" and architecture != "arm64":
        raise ValueError("macOS release architecture must be arm64")
    if signature_kind not in SIGNATURE_KINDS:
        raise ValueError("unsupported signature kind")
    if notarized and (platform != "macos" or not signed):
        raise ValueError("only a signed macOS artifact can be notarized")
    if signed and signature_kind not in {"authenticode", "developer_id"}:
        raise ValueError("distribution-signed evidence needs a distribution signature kind")
    if not signed and signature_kind not in {"ad_hoc", "unsigned"}:
        raise ValueError("proof-only evidence needs an ad-hoc or unsigned signature kind")

    native_payload = _read_json(native_receipt)
    core_payload = _read_json(core_receipt)
    receipt_errors = _ui_receipt_errors(native_payload) + validate_core_receipt(
        core_payload
    )
    if receipt_errors:
        raise ValueError("; ".join(receipt_errors))

    artifact = artifact.resolve(strict=True)
    dependency_lock = dependency_lock.resolve(strict=True)
    if platform == "windows" and artifact.name != "Speakr-Setup.exe":
        raise ValueError("Windows artifact name must be Speakr-Setup.exe")
    if platform == "macos" and artifact.name != "Speakr.dmg":
        raise ValueError("macOS artifact name must be Speakr.dmg")
    if dependency_lock.name != "requirements-release.txt":
        raise ValueError("dependency lock must be requirements-release.txt")
    return {
        "schema": SCHEMA,
        "source": {
            "sha": source_sha,
            "tag": tag or None,
            "version": version,
        },
        "platform": platform,
        "architecture": architecture,
        "artifact": {
            "name": artifact.name,
            "sha256": _sha256(artifact),
        },
        "dependency_lock": {
            "name": dependency_lock.name,
            "sha256": _dependency_lock_sha256(dependency_lock),
        },
        "signature": {
            "signed": bool(signed),
            "notarized": bool(notarized),
            "kind": signature_kind,
            "identity": _safe_public_identity(
                signer_identity, signature_kind
            ),
            "team": _safe_public_identity(signer_team, "none"),
        },
        "scan": {
            "pre_wrap": "passed",
            "installed_or_copied": "passed",
        },
        "runtime": {
            "native": native_payload,
            "core": core_payload,
        },
    }


def write_manifest(destination: Path, payload: dict[str, object]) -> None:
    destination = destination.resolve()
    temporary = destination.with_name(
        f".{destination.name}.{secrets.token_hex(8)}.tmp"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def verify_manifest(
    manifest: Path,
    *,
    artifact: Path,
    dependency_lock: Path,
    source_sha: str,
    tag: str,
) -> list[str]:
    try:
        payload = _read_json(manifest)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["manifest is unreadable"]
    if not isinstance(payload, dict):
        return ["manifest must be a JSON object"]
    expected_top = {
        "schema",
        "source",
        "platform",
        "architecture",
        "artifact",
        "dependency_lock",
        "signature",
        "scan",
        "runtime",
    }
    errors = []
    if set(payload) != expected_top:
        errors.append("manifest does not use the exact top-level schema")
    if payload.get("schema") != SCHEMA:
        errors.append("manifest schema is unsupported")

    source = payload.get("source")
    if not isinstance(source, dict) or set(source) != {"sha", "tag", "version"}:
        errors.append("source evidence is malformed")
    else:
        if source.get("sha") != source_sha.strip().casefold():
            errors.append("source SHA does not match")
        if not isinstance(source.get("sha"), str) or not _SHA.fullmatch(
            source["sha"]
        ):
            errors.append("source SHA is malformed")
        if source.get("tag") != (tag.strip() or None):
            errors.append("source tag does not match")
        if not isinstance(source.get("version"), str) or not _VERSION.fullmatch(
            source["version"]
        ):
            errors.append("source version is malformed")
        if source.get("tag") is not None and (
            not isinstance(source.get("tag"), str)
            or not _TAG.fullmatch(source["tag"])
        ):
            errors.append("source tag is malformed")

    artifact_record = payload.get("artifact")
    if not isinstance(artifact_record, dict) or set(artifact_record) != {"name", "sha256"}:
        errors.append("artifact evidence is malformed")
    else:
        if artifact_record.get("name") != artifact.name:
            errors.append("artifact name does not match")
        if artifact_record.get("sha256") != _sha256(artifact):
            errors.append("artifact hash does not match")

    lock_record = payload.get("dependency_lock")
    if not isinstance(lock_record, dict) or set(lock_record) != {"name", "sha256"}:
        errors.append("dependency lock evidence is malformed")
    else:
        if lock_record.get("name") != dependency_lock.name:
            errors.append("dependency lock name does not match")
        if lock_record.get("sha256") != _dependency_lock_sha256(dependency_lock):
            errors.append("dependency lock hash does not match")

    runtime = payload.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"native", "core"}:
        errors.append("runtime evidence is malformed")
    else:
        errors.extend(_ui_receipt_errors(runtime.get("native")))
        errors.extend(validate_core_receipt(runtime.get("core")))

    signature = payload.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "signed", "notarized", "kind", "identity", "team"
    }:
        errors.append("signature evidence is malformed")
    elif type(signature.get("signed")) is not bool or type(
        signature.get("notarized")
    ) is not bool:
        errors.append("signature booleans are malformed")
    else:
        kind = signature.get("kind")
        identity = signature.get("identity")
        team = signature.get("team")
        if kind not in SIGNATURE_KINDS:
            errors.append("signature kind is malformed")
        if not isinstance(identity, str) or not identity or len(identity) > 300:
            errors.append("signer identity is malformed")
        elif "\n" in identity or "\r" in identity:
            errors.append("signer identity is malformed")
        if not isinstance(team, str) or not team or len(team) > 300:
            errors.append("signer team is malformed")
        elif "\n" in team or "\r" in team:
            errors.append("signer team is malformed")
        if tag:
            if payload.get("platform") == "windows" and (
                signature.get("signed") is not True
                or signature.get("notarized") is not False
                or kind != "authenticode"
            ):
                errors.append("tagged Windows evidence is not Authenticode signed")
            if payload.get("platform") == "macos" and (
                signature.get("signed") is not True
                or signature.get("notarized") is not True
                or kind != "developer_id"
            ):
                errors.append("tagged macOS evidence is not signed and notarized")

    if payload.get("platform") not in PLATFORMS:
        errors.append("platform evidence is malformed")
    if payload.get("architecture") not in ARCHITECTURES:
        errors.append("architecture evidence is malformed")
    if payload.get("platform") == "windows" and payload.get("architecture") != "x86_64":
        errors.append("Windows architecture evidence is malformed")
    if payload.get("platform") == "macos" and payload.get("architecture") != "arm64":
        errors.append("macOS architecture evidence is malformed")
    if payload.get("platform") == "windows" and artifact.name != "Speakr-Setup.exe":
        errors.append("Windows artifact name is not canonical")
    if payload.get("platform") == "macos" and artifact.name != "Speakr.dmg":
        errors.append("macOS artifact name is not canonical")
    if dependency_lock.name != "requirements-release.txt":
        errors.append("dependency lock name is not canonical")
    if payload.get("scan") != {
        "pre_wrap": "passed",
        "installed_or_copied": "passed",
    }:
        errors.append("scan evidence is malformed")
    return errors


def _bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--artifact", type=Path, required=True)
    create.add_argument("--dependency-lock", type=Path, required=True)
    create.add_argument("--native-receipt", type=Path, required=True)
    create.add_argument("--core-receipt", type=Path, required=True)
    create.add_argument("--source-sha", required=True)
    create.add_argument("--tag", default="")
    create.add_argument("--version", required=True)
    create.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    create.add_argument("--architecture", choices=sorted(ARCHITECTURES), required=True)
    create.add_argument("--signed", type=_bool, required=True)
    create.add_argument("--notarized", type=_bool, required=True)
    create.add_argument("--signature-kind", choices=sorted(SIGNATURE_KINDS), required=True)
    create.add_argument("--signer-identity", default="")
    create.add_argument("--signer-team", default="")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--artifact", type=Path, required=True)
    verify.add_argument("--dependency-lock", type=Path, required=True)
    verify.add_argument("--source-sha", required=True)
    verify.add_argument("--tag", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "create":
        try:
            payload = create_manifest(
                artifact=args.artifact,
                dependency_lock=args.dependency_lock,
                native_receipt=args.native_receipt,
                core_receipt=args.core_receipt,
                source_sha=args.source_sha,
                tag=args.tag,
                version=args.version,
                platform=args.platform,
                architecture=args.architecture,
                signed=args.signed,
                notarized=args.notarized,
                signature_kind=args.signature_kind,
                signer_identity=args.signer_identity,
                signer_team=args.signer_team,
            )
            write_manifest(args.output, payload)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(
                "release manifest creation failed during local evidence I/O "
                f"({type(exc).__name__})"
            )
            return 1
        except ValueError as exc:
            print(f"release manifest creation failed: {exc}")
            return 1
        print("release evidence manifest created")
        return 0

    errors = verify_manifest(
        args.manifest,
        artifact=args.artifact,
        dependency_lock=args.dependency_lock,
        source_sha=args.source_sha,
        tag=args.tag,
    )
    if errors:
        print("release evidence manifest invalid: " + "; ".join(errors))
        return 1
    print("release evidence manifest valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
