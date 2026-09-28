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


def validate_evidence_grid(samples, *, period_s: float, tolerance_s: float) -> int:
    """Require the frozen causal grid: no missing point, duplicate or time regression.

    A gap is evidence loss, not occlusion, so callers must treat any failure here as INVALID
    rather than interpolating across it.
    """

    if not samples:
        raise ValueError("TASK8_LIVE_EVIDENCE_GRID_EMPTY")
    previous = None
    for sample in samples:
        stamp = sample.get("sim_time_s") if isinstance(sample, dict) else None
        if not _finite(stamp):
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        if previous is not None:
            delta = stamp - previous
            if delta <= 0:
                raise ValueError("TASK8_LIVE_EVIDENCE_GRID_REGRESSION")
            if abs(delta - period_s) > tolerance_s:
                raise ValueError("TASK8_LIVE_EVIDENCE_GRID_GAP")
        previous = stamp
    return len(samples)


def build_live_evidence_sample(*, identity: dict, phase: str, physics_step: int,
                              sim_time_s: float, source_stamps_s: dict,
                              source_received_monotonic_s: dict, raw_records: dict,
                              holding_state: str, frame: dict, contact: dict,
                              measurements: dict) -> dict:
    """Assemble one canonical sample from explicit readback inputs.

    The port and readback adapters own the values; this function owns the shape, so both call
    sites cannot drift apart. ``frame`` carries ``wrist_frame_valid``/``wrist_target_visible``,
    ``contact`` carries the four contact booleans plus ``observation_valid``, and ``measurements``
    carries the unit-bearing scalars and vectors.
    """

    if type(identity) is not dict or set(identity) != {
            "case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch"}:
        raise ValueError("TASK8_LIVE_EVIDENCE_IDENTITY_INVALID")
    if type(frame) is not dict or set(frame) != {"wrist_frame_valid", "wrist_target_visible"}:
        raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
    if type(contact) is not dict or set(contact) != {
            "observation_valid", "bilateral_contact", "no_fingertip_contact", "cup_supported",
            "released", "placement_stable"}:
        raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
    if type(measurements) is not dict or set(measurements) != {
            "cup_support_distance_m", "end_effector_position_m", "cup_position_m",
            "cup_orientation_xyzw"}:
        raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
    return {
        "case_id": identity["case_id"], "session_id": identity["session_id"],
        "attempt_id": identity["attempt_id"], "reset_epoch": identity["reset_epoch"],
        "release_epoch": identity["release_epoch"], "physics_step": physics_step,
        "sim_time_s": sim_time_s, "phase": phase,
        "source_stamps_s": dict(source_stamps_s),
        "source_received_monotonic_s": dict(source_received_monotonic_s),
        "raw_records": dict(raw_records), "holding_state": holding_state,
        "wrist_frame_valid": frame["wrist_frame_valid"],
        "wrist_target_visible": frame["wrist_target_visible"],
        "contact_observation_valid": contact["observation_valid"],
        "bilateral_contact": contact["bilateral_contact"],
        "no_fingertip_contact": contact["no_fingertip_contact"],
        "cup_supported": contact["cup_supported"], "released": contact["released"],
        "placement_stable": contact["placement_stable"],
        "cup_support_distance_m": measurements["cup_support_distance_m"],
        "end_effector_position_m": list(measurements["end_effector_position_m"]),
        "cup_position_m": list(measurements["cup_position_m"]),
        "cup_orientation_xyzw": list(measurements["cup_orientation_xyzw"]),
    }


_CASE_ID = re.compile(r"[a-z]+-[0-9]{2}\Z")


def resolve_case_journal_path(run_root: Path, case_id: str) -> Path:
    """The only legal journal path for a case, refusing anything that already exists.

    Journals live strictly under ``<run-root>/task8-live/cases/`` so a resumed run cannot splice
    old cases into a continuation and a first failure cannot be papered over by reusing a journal.
    """

    run_root = Path(run_root)
    if not run_root.is_absolute() or ".." in run_root.parts or not run_root.is_dir() \
            or run_root.is_symlink():
        raise ValueError("TASK8_JOURNAL_RUN_ROOT_INVALID")
    if type(case_id) is not str or _CASE_ID.fullmatch(case_id) is None:
        raise ValueError("TASK8_JOURNAL_CASE_ID_INVALID")
    root = run_root / "task8-live" / "cases"
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("TASK8_JOURNAL_ROOT_INVALID")
    journal = root / f"{case_id}.json"
    if journal.exists() or journal.is_symlink():
        raise ValueError("TASK8_JOURNAL_EXISTS")
    summary = run_root / "task8-live" / "campaign-result.json"
    if summary.exists() or summary.is_symlink():
        raise ValueError("TASK8_CAMPAIGN_JOURNAL_EXISTS")
    return journal


_JOURNAL_KEYS = frozenset({
    "case_id", "mode", "status", "live_evidence_path", "live_evidence_sha256",
    "child_retirement_receipt_path", "child_retirement_receipt_sha256",
    "stack_retirement_receipt_path", "stack_retirement_receipt_sha256",
    "source_provenance_sha256", "runtime_config_sha256", "contact_policy_fingerprint",
    "manifest_document_sha256",
})


def require_case_journal_row(row: dict, *, mode: str) -> dict:
    """A journal row is publishable only with its evidence and both retirement receipts.

    A prefix row must carry **no** live evidence artifact; a full row must carry a sealed one.
    Nothing here trusts a pre-filled status: the caller may only write PASSED once every required
    digest is present and well formed.
    """

    if mode not in ("phase_prefix", "full"):
        raise ValueError("TASK8_JOURNAL_MODE_INVALID")
    if type(row) is not dict or set(row) != _JOURNAL_KEYS:
        raise ValueError("TASK8_JOURNAL_ROW_INVALID")
    if type(row["case_id"]) is not str or _CASE_ID.fullmatch(row["case_id"]) is None:
        raise ValueError("TASK8_JOURNAL_CASE_ID_INVALID")
    if row["mode"] != mode:
        raise ValueError("TASK8_JOURNAL_MODE_INVALID")
    if row["status"] not in ("PASSED", "FAILED"):
        raise ValueError("TASK8_JOURNAL_STATUS_INVALID")
    for name in ("live_evidence_sha256", "child_retirement_receipt_sha256",
                 "stack_retirement_receipt_sha256", "source_provenance_sha256",
                 "runtime_config_sha256", "contact_policy_fingerprint",
                 "manifest_document_sha256"):
        if _SHA.fullmatch(str(row[name])) is None:
            raise ValueError("TASK8_JOURNAL_HASH_INVALID")
    # both owned processes must always name a receipt; only a full row names an artifact
    for name in ("child_retirement_receipt_path", "stack_retirement_receipt_path"):
        value = row[name]
        if not isinstance(value, str) or not value:
            raise ValueError("TASK8_JOURNAL_PATH_INVALID")
    if mode == "phase_prefix":
        if row["live_evidence_path"] != "" or row["live_evidence_sha256"] != "0" * 64:
            raise ValueError("TASK8_PREFIX_EVIDENCE_FORBIDDEN")
    elif not isinstance(row["live_evidence_path"], str) or not row["live_evidence_path"]:
        raise ValueError("TASK8_JOURNAL_PATH_INVALID")
    return dict(row)


def require_campaign_cases(manifest: dict, *, prefix_count: int = 9,
                           full_count: int = 5) -> tuple[str, ...]:
    """The exact ordered case list a canonical run must execute in one production call.

    The list comes from the frozen manifest, never from a caller: nine prefixes in phase order
    followed by five full cases, every id unique, so a run cannot drop, repeat or reorder a case.
    """

    if type(manifest) is not dict:
        raise ValueError("TASK8_CAMPAIGN_MANIFEST_INVALID")
    prefixes = manifest.get("prefix_cases")
    fulls = manifest.get("full_cases")
    if not isinstance(prefixes, list) or not isinstance(fulls, list):
        raise ValueError("TASK8_CAMPAIGN_MANIFEST_INVALID")
    if len(prefixes) != prefix_count or len(fulls) != full_count:
        raise ValueError("TASK8_CAMPAIGN_CASE_COUNT_INVALID")
    ids = []
    for case in (*prefixes, *fulls):
        case_id = case.get("case_id") if isinstance(case, dict) else None
        if type(case_id) is not str or _CASE_ID.fullmatch(case_id) is None:
            raise ValueError("TASK8_CAMPAIGN_CASE_ID_INVALID")
        ids.append(case_id)
    if len(set(ids)) != len(ids):
        raise ValueError("TASK8_CAMPAIGN_CASE_DUPLICATE")
    if any(not case_id.startswith("prefix-") for case_id in ids[:prefix_count]) or \
            any(not case_id.startswith("full-") for case_id in ids[prefix_count:]):
        raise ValueError("TASK8_CAMPAIGN_CASE_ORDER_INVALID")
    return tuple(ids)


def plan_campaign_journals(bundle_root: Path, manifest: dict) -> tuple[tuple[str, Path], ...]:
    """Resolve every case's journal path up front, before the single production call starts.

    Runs the frozen case-list rule and the single-legal-path rule together, so a run either has a
    complete, non-conflicting journal plan for all fourteen cases or it fails before doing anything.
    """

    bundle_root = Path(bundle_root)
    if not bundle_root.is_absolute() or ".." in bundle_root.parts \
            or not bundle_root.is_dir() or bundle_root.is_symlink():
        raise ValueError("TASK8_CAMPAIGN_BUNDLE_ROOT_INVALID")
    return tuple((case_id, resolve_case_journal_path(bundle_root, case_id))
                 for case_id in require_campaign_cases(manifest))


_ROW_IDENTITY = {
    "source_provenance_sha256": "source_provenance_sha256",
    "runtime_config_sha256": "runtime_config_sha256",
    "contact_policy_fingerprint": "contact_policy_fingerprint",
}


def require_case_row_matches_bundle(row: dict, *, identities: dict,
                                    manifest_document_sha256: str) -> dict:
    """A journal row may only describe the bundle it was produced under.

    Every identity digest in the row must equal the bundle's, so a row from another bundle (or a
    row written after a controlled identity change) is refused instead of being counted.
    """

    if type(row) is not dict or type(identities) is not dict:
        raise ValueError("TASK8_JOURNAL_IDENTITY_MISMATCH")
    for row_key, identity_key in _ROW_IDENTITY.items():
        if identity_key not in identities or row.get(row_key) != identities[identity_key]:
            raise ValueError("TASK8_JOURNAL_IDENTITY_MISMATCH")
    if row.get("manifest_document_sha256") != manifest_document_sha256:
        raise ValueError("TASK8_JOURNAL_IDENTITY_MISMATCH")
    return dict(row)
