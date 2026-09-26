"""Closed, content-addressed pick-place validation live case manifest."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .pick_place_runner import PickPlaceRunner


ANCHOR_NAMES = ("default", "left", "forward")
FULL_ANCHOR_ORDER = ("default", "left", "forward", "default", "left")
_HASH_KEYS = (
    "source_sha256", "runtime_config_sha256", "collection_config_sha256",
    "contact_policy_fingerprint",
)
_KEYS = frozenset({
    "schema_version", "kind", "backend", "anchors", "anchors_sha256",
    *_HASH_KEYS, "prefix_cases", "full_cases", "manifest_sha256",
})


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_hash(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("TASK8_HASH_INVALID")
    return value


def _require_anchors(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != set(ANCHOR_NAMES):
        raise ValueError("TASK8_ANCHORS_INVALID")
    for anchor in value.values():
        if not isinstance(anchor, dict) or set(anchor) != {"cup_start_m", "neck_start_rad"}:
            raise ValueError("TASK8_ANCHORS_INVALID")
        cup = anchor["cup_start_m"]
        if not isinstance(cup, list) or len(cup) != 3:
            raise ValueError("TASK8_ANCHORS_INVALID")
        if any(type(number) not in (int, float) or not math.isfinite(number) for number in (
            *cup, anchor["neck_start_rad"],
        )):
            raise ValueError("TASK8_ANCHORS_INVALID")
        if not (0.05 <= cup[2] <= 0.35 and all(abs(v) <= 1.0 for v in cup[:2])
                and abs(anchor["neck_start_rad"]) <= math.pi):
            raise ValueError("TASK8_ANCHORS_INVALID")
    return value


def _prefix_cases() -> list[dict]:
    return [
        {"case_id": f"prefix-{index:02d}", "mode": "phase_prefix",
         "anchor": "default", "stop_after": phase, "lifecycle": "FULL_RESTART"}
        for index, phase in enumerate(PickPlaceRunner.PHASES, 1)
    ]


def _full_cases() -> list[dict]:
    return [
        {"case_id": f"full-{index:02d}", "mode": "full",
         "anchor": anchor, "stop_after": None, "lifecycle": "FULL_RESTART"}
        for index, anchor in enumerate(FULL_ANCHOR_ORDER, 1)
    ]


def build_pick_place_validation_manifest(
    anchors: dict, *, source_sha256: str, runtime_config_sha256: str,
    collection_config_sha256: str, contact_policy_fingerprint: str,
) -> dict:
    _require_anchors(anchors)
    hashes = {name: _require_hash(value) for name, value in (
        ("source_sha256", source_sha256),
        ("runtime_config_sha256", runtime_config_sha256),
        ("collection_config_sha256", collection_config_sha256),
        ("contact_policy_fingerprint", contact_policy_fingerprint),
    )}
    # Copy through canonical bytes so later caller mutations cannot alter this manifest.
    frozen_anchors = json.loads(_canonical(anchors))
    document = {
        "schema_version": 1, "kind": "ACT_TASK8_LIVE", "backend": "mujoco",
        "anchors": frozen_anchors, "anchors_sha256": _sha(frozen_anchors),
        **hashes, "prefix_cases": _prefix_cases(), "full_cases": _full_cases(),
    }
    document["manifest_sha256"] = _sha(document)
    return require_pick_place_validation_manifest(document)


def require_pick_place_validation_manifest(value: object, *, expected_anchors_sha256: str | None = None) -> dict:
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise ValueError("TASK8_MANIFEST_SCHEMA")
    if value["schema_version"] != 1 or value["kind"] != "ACT_TASK8_LIVE" or value["backend"] != "mujoco":
        raise ValueError("TASK8_MANIFEST_ROLE_INVALID")
    _require_anchors(value["anchors"])
    for key in (*_HASH_KEYS, "anchors_sha256", "manifest_sha256"):
        _require_hash(value[key])
    if (value["anchors_sha256"] != _sha(value["anchors"])
            or expected_anchors_sha256 is not None
            and value["anchors_sha256"] != _require_hash(expected_anchors_sha256)):
        raise ValueError("TASK8_ANCHORS_HASH_MISMATCH")
    if value["prefix_cases"] != _prefix_cases() or value["full_cases"] != _full_cases():
        raise ValueError("TASK8_CASES_INVALID")
    if value["manifest_sha256"] != _sha({key: item for key, item in value.items()
                                         if key != "manifest_sha256"}):
        raise ValueError("TASK8_MANIFEST_HASH_MISMATCH")
    return value


def write_new_manifest(path: Path, document: dict) -> Path:
    """Publish a verified manifest atomically without replacing an existing one."""
    require_pick_place_validation_manifest(document)
    path = Path(path)
    if not path.is_absolute() or not path.parent.is_dir():
        raise ValueError("TASK8_MANIFEST_PATH_INVALID")
    data = _canonical(document) + b"\n"
    fd, staging_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging_name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(staging_name)
    return path


# Legacy API for validated version-one manifests.
build_task8_live_manifest = build_pick_place_validation_manifest
require_task8_live_manifest = require_pick_place_validation_manifest
