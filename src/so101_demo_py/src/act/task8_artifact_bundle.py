"""Publish and verify a self-contained Task 8 artifact bundle.

A bundle is admitted only through its atomically published ``preparation-receipt.json``: the
receipt records every business artifact's bundled and source hash plus the frozen identities, and
verification reads the bundle's own copies, so the source evidence tree may become unavailable
after preparation without weakening admission.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, fields as dataclass_fields
from pathlib import Path

SCHEMA_VERSION = 2
KIND = "task8_preparation_receipt"
RECEIPT_NAME = "preparation-receipt.json"
MANIFEST_NAME = "manifest.json"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ARTIFACTS = ("source_provenance", "runtime_config", "collection_config", "calibration_report",
              "head_search_qualification", "measurement_contract", "anchors", "proposal",
              "activation_receipt")
_IDENTITIES = ("source_provenance_sha256", "runtime_config_sha256", "anchors_sha256",
               "contact_policy_fingerprint", "act_profile_sha256")


@dataclass(frozen=True)
class Task8ArtifactInputs:
    source_root: Path
    install_overlay: Path
    source_provenance: Path
    runtime_config: Path
    collection_config: Path
    calibration_report: Path
    head_search_qualification: Path
    measurement_contract: Path
    anchors: Path
    proposal: Path
    activation_receipt: Path
    manifest: Path
    identities: dict


@dataclass(frozen=True)
class PreparedTask8Bundle:
    receipt: Path
    source_provenance: Path
    manifest: Path
    runtime_config: Path
    collection_config: Path
    calibration_report: Path
    proposal: Path
    activation_receipt: Path
    head_search_qualification: Path
    measurement_contract: Path
    anchors: Path
    identities: dict


def _digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _regular(path: Path, code: str) -> None:
    try:
        info = Path(path).stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(code) from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(code)


def _canonical(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def _receipt_sha256(document: dict) -> str:
    payload = {key: value for key, value in document.items() if key != "receipt_sha256"}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _publish_receipt(document: dict, target: Path) -> Path:
    """Atomically publish the receipt; an existing receipt is never overwritten."""

    target = Path(target)
    partial = Path(str(target) + ".partial")
    descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(_canonical(document))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(str(partial), str(target))
    except FileExistsError as error:
        os.unlink(str(partial))
        raise ValueError("TASK8_PREPARATION_ALREADY_COMMITTED") from error
    os.unlink(str(partial))
    return target


def prepare_task8_bundle(inputs: Task8ArtifactInputs, bundle_root: Path) -> Path:
    """Copy every business artifact into one bundle and commit its receipt."""

    if not isinstance(inputs, Task8ArtifactInputs):
        raise ValueError("TASK8_PREPARATION_INPUTS_INVALID")
    if (type(inputs.identities) is not dict
            or tuple(sorted(inputs.identities)) != tuple(sorted(_IDENTITIES))
            or any(_SHA.fullmatch(str(value)) is None for value in inputs.identities.values())):
        raise ValueError("TASK8_PREPARATION_IDENTITY_INVALID")
    bundle_root = Path(bundle_root)
    if bundle_root.exists() and any(bundle_root.iterdir()):
        raise ValueError("TASK8_PREPARATION_DESTINATION_IN_USE")
    bundle_root.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name in _ARTIFACTS:
        source = Path(getattr(inputs, name))
        _regular(source, "TASK8_PREPARATION_ARTIFACT_MISSING")
        target = bundle_root / f"{name}{source.suffix or '.json'}"
        target.write_bytes(source.read_bytes())
        artifacts[name] = {"relative_path": target.name, "sha256": _digest(target),
                           "source_sha256": _digest(source)}
    manifest_source = Path(inputs.manifest)
    _regular(manifest_source, "TASK8_PREPARATION_ARTIFACT_MISSING")
    manifest = json.loads(manifest_source.read_bytes())
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["calibration_report_path"] = artifacts["calibration_report"]["relative_path"]
    manifest["calibration_report_sha256"] = artifacts["calibration_report"]["sha256"]
    manifest.pop("manifest_document_sha256", None)
    manifest["manifest_document_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    manifest_target = bundle_root / MANIFEST_NAME
    manifest_target.write_bytes(_canonical(manifest))
    document = {
        "schema_version": SCHEMA_VERSION, "kind": KIND,
        "bundle_root": str(bundle_root.resolve()),
        "manifest_path": manifest_target.name,
        "manifest_sha256": _digest(manifest_target),
        "manifest_source_sha256": _digest(manifest_source),
        "artifacts": artifacts,
        "identities": dict(inputs.identities),
    }
    document["receipt_sha256"] = _receipt_sha256(document)
    return _publish_receipt(document, bundle_root / RECEIPT_NAME)


def verify_prepared_task8_bundle(receipt_path: Path) -> PreparedTask8Bundle:
    """Re-derive the bundle from its own copies; the source evidence tree is not consulted."""

    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    _regular(receipt_path, "TASK8_PREPARATION_REQUIRED")
    try:
        document = json.loads(receipt_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TASK8_PREPARATION_REQUIRED") from error
    if (type(document) is not dict or document.get("kind") != KIND
            or document.get("schema_version") != SCHEMA_VERSION):
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    if document.get("receipt_sha256") != _receipt_sha256(document):
        raise ValueError("TASK8_PREPARATION_RECEIPT_INVALID")
    if tuple(sorted(document.get("artifacts", {}))) != tuple(sorted(_ARTIFACTS)):
        raise ValueError("TASK8_PREPARATION_RECEIPT_INVALID")
    if tuple(sorted(document.get("identities", {}))) != tuple(sorted(_IDENTITIES)):
        raise ValueError("TASK8_PREPARATION_RECEIPT_INVALID")
    bundle_root = receipt_path.parent
    if Path(document["bundle_root"]) != bundle_root.resolve():
        raise ValueError("TASK8_PREPARATION_BUNDLE_MISMATCH")
    resolved = {}
    for name, entry in document["artifacts"].items():
        if tuple(sorted(entry)) != ("relative_path", "sha256", "source_sha256"):
            raise ValueError("TASK8_PREPARATION_RECEIPT_INVALID")
        relative = entry["relative_path"]
        if (type(relative) is not str or Path(relative).name != relative
                or "/" in relative or relative in ("", ".", "..")):
            raise ValueError("TASK8_PREPARATION_RECEIPT_INVALID")
        target = bundle_root / relative
        _regular(target, "TASK8_PREPARATION_ARTIFACT_MISSING")
        if _digest(target) != entry["sha256"]:
            raise ValueError("TASK8_PREPARATION_ARTIFACT_DIRTY")
        resolved[name] = target
    manifest_target = bundle_root / document["manifest_path"]
    _regular(manifest_target, "TASK8_PREPARATION_ARTIFACT_MISSING")
    if _digest(manifest_target) != document["manifest_sha256"]:
        raise ValueError("TASK8_PREPARATION_ARTIFACT_DIRTY")
    return PreparedTask8Bundle(
        receipt=receipt_path, manifest=manifest_target,
        identities=dict(document["identities"]), **resolved)


def validate_task8_startup_artifacts(payload) -> PreparedTask8Bundle:
    """Pure read-only validation: no lease, no worker, no broker, no ROS child."""

    if not isinstance(payload, dict):
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    path = payload.get("preparation_receipt_path")
    digest = payload.get("preparation_receipt_sha256")
    if type(path) is not str or not path:
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    receipt_path = Path(path)
    if not receipt_path.is_absolute() or ".." in receipt_path.parts:
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    if _SHA.fullmatch(str(digest)) is None:
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    _regular(receipt_path, "TASK8_PREPARATION_REQUIRED")
    if _digest(receipt_path) != digest:
        raise ValueError("TASK8_PREPARATION_RECEIPT_INVALID")
    return verify_prepared_task8_bundle(receipt_path)


def task8_bundle_payload(receipt_path: Path) -> dict:
    """The two production payload fields a Task 8 run carries for its committed bundle.

    The receipt is verified first, so a payload can never point at an uncommitted or tampered
    bundle; the digest is taken over the receipt's raw bytes, which is what admission re-checks.
    """

    receipt_path = Path(receipt_path)
    if not receipt_path.is_absolute() or ".." in receipt_path.parts:
        raise ValueError("TASK8_PREPARATION_REQUIRED")
    verify_prepared_task8_bundle(receipt_path)
    return {"preparation_receipt_path": str(receipt_path),
            "preparation_receipt_sha256": _digest(receipt_path)}
