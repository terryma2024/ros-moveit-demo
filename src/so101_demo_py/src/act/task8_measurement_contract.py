"""Bind the Task 8 measurement contract to frozen identities before any measurement runs.

The repository template is a closed threshold document with no identity. Binding copies it into
the evidence root, records the raw hash of every threshold source, and stamps the contract hash;
the unbound template is never accepted as a contract for a run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

SCHEMA_VERSION = 1
KIND = "task8_calibration_measurement_contract"
TEMPLATE_KIND = "task8_calibration_measurement_contract_template"
BATCH_KIND = "task8_calibration_batch"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITIES = ("source_provenance_sha256", "runtime_config_sha256", "anchors_sha256",
               "contact_policy_fingerprint", "act_profile_sha256")
_TEMPLATE_KEYS = ("schema_version", "kind", "anchors", "measurements", "camera_measurements",
                  "thresholds", "verdicts")
_BOUND_KEYS = ("schema_version", "kind", "identities", "source_hashes", "anchors",
               "measurements", "camera_measurements", "thresholds", "verdicts",
               "contract_sha256")


def _digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _regular(path: Path, code: str) -> None:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(code) from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(code)


def _canonical(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def _contract_sha256(document: dict) -> str:
    payload = {key: value for key, value in document.items() if key != "contract_sha256"}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def bind_measurement_contract(template_path: Path, identities: dict, output: Path) -> Path:
    """Publish a bound contract for this run; an existing target is never overwritten."""

    template_path, output = Path(template_path), Path(output)
    _regular(template_path, "MEASUREMENT_CONTRACT_TEMPLATE_MISSING")
    if (type(identities) is not dict or tuple(sorted(identities)) != tuple(sorted(_IDENTITIES))
            or any(_SHA.fullmatch(str(value)) is None for value in identities.values())):
        raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_INVALID")
    try:
        template = json.loads(template_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("MEASUREMENT_CONTRACT_TEMPLATE_INVALID") from error
    if (type(template) is not dict or tuple(sorted(template)) != tuple(sorted(_TEMPLATE_KEYS))
            or template["schema_version"] != SCHEMA_VERSION
            or template["kind"] != TEMPLATE_KIND):
        raise ValueError("MEASUREMENT_CONTRACT_TEMPLATE_INVALID")
    document = {
        "schema_version": SCHEMA_VERSION, "kind": KIND, "identities": dict(identities),
        "source_hashes": {"template": _digest(template_path)},
        "anchors": list(template["anchors"]), "measurements": dict(template["measurements"]),
        "camera_measurements": dict(template["camera_measurements"]),
        "thresholds": dict(template["thresholds"]), "verdicts": list(template["verdicts"]),
    }
    document["contract_sha256"] = _contract_sha256(document)
    payload = _canonical(document)
    partial = Path(str(output) + ".partial")
    descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(str(partial), str(output))
    except FileExistsError as error:
        os.unlink(str(partial))
        raise ValueError("MEASUREMENT_CONTRACT_OUTPUT_EXISTS") from error
    os.unlink(str(partial))
    return output


def load_measurement_contract(path: Path, *, expected_hashes: dict) -> dict:
    """Return the bound contract, refusing the unbound template or a foreign identity."""

    path = Path(path)
    _regular(path, "MEASUREMENT_CONTRACT_MISSING")
    try:
        document = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID") from error
    if type(document) is not dict:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    if tuple(sorted(document)) != tuple(sorted(_BOUND_KEYS)):
        if document.get("kind") == TEMPLATE_KIND:
            raise ValueError("MEASUREMENT_CONTRACT_UNBOUND")
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    if document["schema_version"] != SCHEMA_VERSION or document["kind"] != KIND:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    if document["contract_sha256"] != _contract_sha256(document):
        raise ValueError("MEASUREMENT_CONTRACT_HASH_INVALID")
    if (type(expected_hashes) is not dict
            or document["identities"] != dict(expected_hashes)):
        raise ValueError("MEASUREMENT_CONTRACT_IDENTITY_MISMATCH")
    if type(document["source_hashes"]) is not dict or not document["source_hashes"]:
        raise ValueError("MEASUREMENT_CONTRACT_INVALID")
    return document


def close_measurement_batch(root: Path, identity: dict, *, status: str = "CLOSED") -> Path:
    """Seal one raw measurement batch with every raw file hash; never reopened."""

    root = Path(root)
    if type(identity) is not dict or not identity:
        raise ValueError("MEASUREMENT_BATCH_IDENTITY_INVALID")
    if status not in ("CLOSED", "INVALID"):
        raise ValueError("MEASUREMENT_BATCH_STATUS_INVALID")
    for name in ("source_provenance_sha256", "contract_sha256"):
        if _SHA.fullmatch(str(identity.get(name))) is None:
            raise ValueError("MEASUREMENT_BATCH_IDENTITY_INVALID")
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "batch.json":
            files[path.relative_to(root).as_posix()] = _digest(path)
    document = {"schema_version": SCHEMA_VERSION, "kind": BATCH_KIND, "status": status,
                "identity": dict(identity), "files": files,
                "anchors": ["default", "left", "forward"]}
    # the batch document seals itself too, so its identity and status cannot be edited later
    document["batch_sha256"] = hashlib.sha256(
        _canonical({key: value for key, value in document.items()
                    if key != "batch_sha256"})).hexdigest()
    target = root / "batch.json"
    descriptor = os.open(str(target) + ".partial", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(_canonical(document))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(str(target) + ".partial", target)
    except FileExistsError as error:
        os.unlink(str(target) + ".partial")
        raise ValueError("MEASUREMENT_BATCH_ALREADY_CLOSED") from error
    os.unlink(str(target) + ".partial")
    return target
