"""Collect one Task 8 full case's live evidence as a closed 10 Hz causal record.

Every gap that is not "valid frame and the target is genuinely not visible" is evidence loss and
is refused here rather than degraded into a bounded occlusion. The canonical index written by
``seal()`` is the only publish point: until it exists the case has no live evidence artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

SCHEMA_VERSION = 1
_SOURCES = ("world", "scene", "contact", "head", "wrist", "arm", "neck")
_SAMPLE_KEYS = (
    "case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
    "sim_time_s", "phase", "source_stamps_s", "source_received_monotonic_s", "raw_records",
    "holding_state", "wrist_frame_valid", "wrist_target_visible", "contact_observation_valid",
    "bilateral_contact", "no_fingertip_contact", "cup_supported", "released",
    "placement_stable", "cup_support_distance_m", "end_effector_position_m", "cup_position_m",
    "cup_orientation_xyzw",
)
_BOOLEANS = ("wrist_frame_valid", "wrist_target_visible", "contact_observation_valid",
             "bilateral_contact", "no_fingertip_contact", "cup_supported", "released",
             "placement_stable")
_VECTORS = {"end_effector_position_m": 3, "cup_position_m": 3, "cup_orientation_xyzw": 4}
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _canonical(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def _finite(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Task8LiveEvidenceRecorder:
    """Append canonical samples for one case and seal them into one artifact."""

    def __init__(self, *, case_id: str, evidence_root: Path, session_id: str,
                 attempt_id: str) -> None:
        if not all(isinstance(value, str) and value
                   for value in (case_id, session_id, attempt_id)):
            raise ValueError("TASK8_LIVE_EVIDENCE_IDENTITY_INVALID")
        self.case_id = case_id
        self.session_id = session_id
        self.attempt_id = attempt_id
        self.evidence_root = Path(evidence_root)
        if not self.evidence_root.is_dir() or self.evidence_root.is_symlink():
            raise ValueError("TASK8_LIVE_EVIDENCE_ROOT_INVALID")
        self._staging = self.evidence_root / "live-evidence-staging"
        self._staging.mkdir(mode=0o700, exist_ok=True)
        self._entries: list[dict] = []
        self._identity: dict | None = None
        self._sealed: Path | None = None

    def append(self, sample: dict) -> None:
        """Validate and persist one canonical sample; never accept a lossy frame."""

        if self._sealed is not None:
            raise ValueError("TASK8_LIVE_EVIDENCE_ALREADY_SEALED")
        if type(sample) is not dict or set(sample) != set(_SAMPLE_KEYS):
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        if (sample["case_id"] != self.case_id or sample["session_id"] != self.session_id
                or sample["attempt_id"] != self.attempt_id):
            raise ValueError("TASK8_LIVE_EVIDENCE_IDENTITY_MISMATCH")
        for name in ("reset_epoch", "release_epoch", "physics_step"):
            if type(sample[name]) is not int or sample[name] < 0:
                raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        if not _finite(sample["sim_time_s"]) or not isinstance(sample["phase"], str) \
                or not sample["phase"]:
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        if any(type(sample[name]) is not bool for name in _BOOLEANS):
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        if sample["contact_observation_valid"] is not True or sample["wrist_frame_valid"] is not True:
            # a missing frame or an invalid contact observation is evidence loss, not occlusion
            raise ValueError("TASK8_LIVE_EVIDENCE_LOSS")
        if not _finite(sample["cup_support_distance_m"]):
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        for name, length in _VECTORS.items():
            values = sample[name]
            if (not isinstance(values, list) or len(values) != length
                    or not all(_finite(value) for value in values)):
                raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        if not isinstance(sample["holding_state"], str) or not sample["holding_state"]:
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        for name in ("source_stamps_s", "source_received_monotonic_s"):
            stamps = sample[name]
            if (type(stamps) is not dict or tuple(sorted(stamps)) != tuple(sorted(_SOURCES))
                    or not all(_finite(value) for value in stamps.values())):
                raise ValueError("TASK8_LIVE_EVIDENCE_SOURCE_MISSING")
        records = sample["raw_records"]
        if type(records) is not dict or tuple(sorted(records)) != tuple(sorted(_SOURCES)):
            raise ValueError("TASK8_LIVE_EVIDENCE_SOURCE_MISSING")
        for source, record in records.items():
            if type(record) is not dict or set(record) != {"relative_path", "sha256"}:
                raise ValueError("TASK8_LIVE_EVIDENCE_RAW_RECORD_INVALID")
            relative = record["relative_path"]
            if (type(relative) is not str or relative.startswith("/")
                    or ".." in Path(relative).parts):
                raise ValueError("TASK8_LIVE_EVIDENCE_RAW_RECORD_INVALID")
            raw = self.evidence_root / relative
            try:
                info = raw.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError("TASK8_LIVE_EVIDENCE_RAW_RECORD_MISSING") from error
            if not stat.S_ISREG(info.st_mode) or _SHA.fullmatch(str(record["sha256"])) is None \
                    or _digest(raw) != record["sha256"]:
                raise ValueError("TASK8_LIVE_EVIDENCE_RAW_RECORD_INVALID")
        relative = f"sample-{len(self._entries):06d}.json"
        target = self._staging / relative
        payload = _canonical(sample)
        descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._entries.append({
            "relative_path": f"{self._staging.name}/{relative}",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "physics_step": sample["physics_step"], "phase": sample["phase"],
            "sim_time_s": sample["sim_time_s"],
            "wrist_target_visible": sample["wrist_target_visible"],
            "release_epoch": sample["release_epoch"], "reset_epoch": sample["reset_epoch"],
        })

    def seal(self, identity: dict) -> dict:
        """Publish the canonical index once; the index is the artifact's only commit point."""

        if self._sealed is not None:
            raise ValueError("TASK8_LIVE_EVIDENCE_ALREADY_SEALED")
        if type(identity) is not dict or set(identity) != {
                "case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch"}:
            raise ValueError("TASK8_LIVE_EVIDENCE_IDENTITY_INVALID")
        if (identity["case_id"] != self.case_id or identity["session_id"] != self.session_id
                or identity["attempt_id"] != self.attempt_id):
            raise ValueError("TASK8_LIVE_EVIDENCE_IDENTITY_MISMATCH")
        if not self._entries:
            raise ValueError("TASK8_LIVE_EVIDENCE_EMPTY")
        for entry in self._entries:
            if (entry["reset_epoch"] != identity["reset_epoch"]
                    or entry["release_epoch"] != identity["release_epoch"]):
                raise ValueError("TASK8_LIVE_EVIDENCE_EPOCH_MISMATCH")
        index = {
            "schema_version": SCHEMA_VERSION, "kind": "task8_live_evidence",
            "identity": dict(identity), "sample_count": len(self._entries),
            "samples": [dict(entry) for entry in self._entries],
        }
        target = self.evidence_root / f"{self.case_id}-live-evidence.json"
        partial = Path(str(target) + ".partial")
        descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical(index))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(str(partial), str(target))
        except FileExistsError as error:
            os.unlink(str(partial))
            raise ValueError("TASK8_LIVE_EVIDENCE_ALREADY_SEALED") from error
        os.unlink(str(partial))
        _fsync_dir(self._staging)
        _fsync_dir(self.evidence_root)
        self._sealed = target
        return {"path": str(target), "sha256": _digest(target), "schema_version": SCHEMA_VERSION}
