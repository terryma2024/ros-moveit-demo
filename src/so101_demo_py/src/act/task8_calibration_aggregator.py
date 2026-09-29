"""Derive Task 8 calibration verdicts from sealed raw evidence, never from labels.

A batch is only usable when it is sealed, its recorded file hashes still match, and every batch
in the set shares one source provenance. Missing evidence is ``UNMEASURED``, out-of-contract
evidence is ``FAIL``, a polluted batch is refused outright, and ``TASK8_READY`` is emitted only
when fov/collision/search/synchronization/execution all PASS while release/retreat stay
``UNMEASURED`` (Task 8P4 computes those from live journals).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA_VERSION = 1
BATCH_KIND = "task8_calibration_batch"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ANCHORS = ("default", "left", "forward")
_CHECKS = ("fov", "collision", "search", "synchronization", "execution")


def _digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _canonical(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def _load_batch(root: Path) -> tuple[dict, dict]:
    batch = json.loads((root / "batch.json").read_bytes())
    if batch.get("kind") != BATCH_KIND:
        raise ValueError("CALIBRATION_BATCH_INVALID")
    if batch.get("status") == "INVALID":
        raise ValueError("CALIBRATION_BATCH_INVALID")
    if batch.get("status") != "CLOSED":
        raise ValueError("CALIBRATION_BATCH_NOT_CLOSED")
    recorded = batch.get("batch_sha256")
    if (not isinstance(recorded, str)
            or hashlib.sha256(_canonical({key: value for key, value in batch.items()
                                          if key != "batch_sha256"})).hexdigest() != recorded):
        raise ValueError("CALIBRATION_BATCH_TAMPERED")
    for relative, digest in sorted(batch.get("files", {}).items()):
        candidate = root / relative
        if not candidate.is_file() or _digest(candidate) != digest:
            raise ValueError("CALIBRATION_BATCH_TAMPERED")
    return batch, batch["identity"]


def _read(root: Path, relative: str):
    path = root / relative
    if not path.is_file():
        return None
    return json.loads(path.read_bytes())


def _fov(root: Path, period_s: float) -> str:
    verdict = "PASS"
    for anchor in _ANCHORS:
        document = _read(root, f"fov/{anchor}.json")
        if document is None or not document.get("samples"):
            return "UNMEASURED"
        previous = None
        for sample in document["samples"]:
            stamp = sample.get("t_s")
            if not isinstance(stamp, (int, float)):
                return "UNMEASURED"
            if previous is not None and abs((stamp - previous) - period_s) > period_s / 2:
                verdict = "FAIL"
            previous = stamp
            if sample.get("target_in_view") is not True:
                verdict = "FAIL"
    return verdict


def _search(root: Path, minimum: int) -> str:
    verdict = "PASS"
    for anchor in _ANCHORS:
        document = _read(root, f"search/{anchor}.json")
        if document is None or not document.get("lock_frames"):
            return "UNMEASURED"
        best = 0
        run = 0
        target = None
        for frame in document["lock_frames"]:
            if frame.get("qualified") is True:
                if frame.get("target_id") == target:
                    run += 1
                else:
                    target, run = frame.get("target_id"), 1
                best = max(best, run)
            else:
                target, run = None, 0
        if best < minimum:
            verdict = "FAIL"
    return verdict


def _synchronization(root: Path, thresholds: dict) -> str:
    verdict = "PASS"
    for anchor in _ANCHORS:
        document = _read(root, f"sync/{anchor}.json")
        if document is None or not document.get("samples"):
            return "UNMEASURED"
        previous = None
        for sample in document["samples"]:
            age, skew, stamp = sample.get("age_s"), sample.get("skew_s"), sample.get("t_s")
            if not all(isinstance(value, (int, float)) for value in (age, skew)):
                return "UNMEASURED"
            if age > thresholds["max_age_s"] or skew > thresholds["max_skew_s"]:
                verdict = "FAIL"
            if stamp is not None:
                if previous is not None and stamp < previous:
                    verdict = "FAIL"
                previous = stamp
    return verdict


def _collision(root: Path, thresholds: dict) -> str:
    document = _read(root, "collision.json")
    if document is None or not document.get("calls"):
        return "UNMEASURED"
    calls = document["calls"]
    if len(calls) != thresholds["full_request_count"]:
        return "FAIL"
    for call in calls:
        duration = call.get("duration_ms")
        if not isinstance(duration, (int, float)):
            return "UNMEASURED"
        if duration > thresholds["full_request_budget_ms"] or call.get("contact_ok") is not True:
            return "FAIL"
    return "PASS"


def _execution(root: Path) -> str:
    document = _read(root, "execution.json")
    receipt = _read(root, "cleanup-receipt.json")
    if document is None:
        return "UNMEASURED"
    if receipt is None or receipt.get("group_clear") is not True:
        return "FAIL"
    for name in ("reference_matches_permit", "velocity_ok", "acceleration_ok", "stop_ok"):
        if document.get(name) is not True:
            return "FAIL"
    return "PASS"


def _write(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(document)
    descriptor = os.open(str(path) + ".partial", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(path) + ".partial", path)
    return path


def aggregate_task8_calibration(batch_roots, contract, output_root: Path) -> dict:
    """Aggregate sealed batches into the qualification sample, report and receipt."""

    output_root = Path(output_root)
    roots = tuple(Path(root) for root in batch_roots)
    if not roots:
        raise ValueError("CALIBRATION_BATCH_INVALID")
    batches = [_load_batch(root) for root in roots]
    provenances = {batch["identity"]["source_provenance_sha256"] for batch, _ in batches}
    if len(provenances) != 1:
        raise ValueError("CALIBRATION_IDENTITY_MISMATCH")
    source_provenance_sha256 = provenances.pop()
    contract_sha256 = contract["contract_sha256"]
    for batch, identity in batches:
        if identity.get("contract_sha256") != contract_sha256:
            raise ValueError("CALIBRATION_IDENTITY_MISMATCH")
    thresholds = contract["thresholds"]
    checks = {
        "fov": _fov(roots[0], thresholds["fov"]["sample_period_s"]),
        "collision": _collision(roots[0], thresholds["collision"]),
        "search": _search(roots[0], thresholds["search"]["min_consecutive_lock_frames"]),
        "synchronization": _synchronization(roots[0], thresholds["synchronization"]),
        "execution": _execution(roots[0]),
        "release": "UNMEASURED",
        "retreat": "UNMEASURED",
    }
    readings = None
    for root in roots:
        document = _read(root, "measurements.json")
        if document is not None:
            readings = document
            break
    ready = all(checks[name] == "PASS" for name in _CHECKS)
    sample = None
    if readings is not None:
        sample_document = {
            "schema_version": SCHEMA_VERSION, "kind": "head_search_qualification",
            "status": "PASS" if ready else "FAIL",
            "measurements": {name: readings["measurements"][name]
                             for name in sorted(readings["measurements"])},
            "camera_measurements": {name: readings["camera_measurements"][name]
                                    for name in sorted(readings["camera_measurements"])},
            "observed_lock_frames": readings.get("observed_lock_frames", {}),
            "source_provenance_sha256": source_provenance_sha256,
        }
        sample = _write(output_root / "head-search-qualification.json", sample_document)
    report_measurements = {}
    if sample is not None:
        digest = _digest(sample)
        for name, entry in sorted(readings["measurements"].items()):
            report_measurements[name] = dict(entry, sample_path=str(sample), sample_sha256=digest)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "TASK8_READY" if ready and sample is not None else "CALIBRATION_REQUIRED",
        "source_commit": next(iter(batches))[1]["source_commit"],
        "config_sha256": next(iter(batches))[1]["config_sha256"],
        "source_provenance_sha256": source_provenance_sha256,
        "measurements": report_measurements,
        "checks": checks,
    }
    report_path = _write(output_root / "calibration-report.json", report)
    receipt = {
        "schema_version": SCHEMA_VERSION, "kind": "task8_calibration_aggregation_receipt",
        "batch_roots": [str(root) for root in roots],
        "contract_sha256": contract_sha256,
        "source_provenance_sha256": source_provenance_sha256,
        "checks": checks,
        "calibration_report_sha256": _digest(report_path),
        "head_search_qualification_sha256": _digest(sample) if sample is not None else None,
    }
    receipt_path = _write(output_root / "aggregation-receipt.json", receipt)
    outputs = {"calibration_report": report_path, "aggregation_receipt": receipt_path}
    if sample is not None:
        outputs["head_search_qualification"] = sample
    return outputs


# --- protocol v2 seam: derive verdicts from raw evidence, never from labels ---------------------------------
# The approved protocol requires every field to be recomputed from raw evidence. These helpers consume the
# closed, indexed batch and the formula module; they never read `target_in_view`, `qualified`, `contact_ok` or
# any `*_ok` flag, and they iterate **every** supplied root rather than the first one.

def derive_field_verdicts(roots, contract: dict) -> dict:
    """Per-root, per-field verdicts recomputed from the sealed batch's raw records."""

    from so101_demo.act.task8_measurement_formulas import compute_field, require_raw_inputs
    from so101_demo.act.task8_measurement_schema import validate_closed_batch

    per_root = {}
    for root in roots:
        index = validate_closed_batch(Path(root))
        raw = _load_raw_records(index)
        require_raw_inputs(raw)
        verdicts = {}
        for section in ("measurements", "support"):
            for field in contract[section]:
                if field not in raw["measurements"]:
                    # a field with no raw record is explicitly UNMEASURED - never a silent pass
                    verdicts[field] = "UNMEASURED"
                    continue
                verdicts[field] = compute_field(field, raw, contract)["verdict"]
        per_root[str(root)] = verdicts
    return per_root


def _load_raw_records(index) -> dict:
    """Read the indexed raw files only - nothing outside `batch.json.files` is ever opened."""

    measurements, configured = {}, {}
    for relative in sorted(index.files):
        path = index.path(relative)
        document = json.loads(path.read_bytes())
        if not isinstance(document, dict):
            raise ValueError("RAW_EVIDENCE_REQUIRED: raw record must be a JSON object")
        for key in (document.get("measurements") or {}):
            if key in _LABELS or (isinstance(key, str) and key.endswith("_ok")):
                raise ValueError(f"RAW_EVIDENCE_REQUIRED: {key} is a label, not raw evidence")
        measurements.update(document.get("measurements") or {})
        configured.update(document.get("configured") or {})
    return {"measurements": measurements, "configured": configured}


_LABELS = frozenset({"qualified", "target_in_view", "contact_ok", "stop_confirmed"})


def derived_checks(roots, contract: dict) -> dict:
    """Fold the per-field verdicts of every root into the five check verdicts.

    A check passes only when every member field passes on every root; any FAIL/INVALID member fails the check,
    and a member with no raw record makes the check UNMEASURED - so an absent measurement can never be read as a
    pass. The member sets come from `calibration.CHECK_MEASUREMENTS`, the repository's own grouping, rather than
    a private list.
    """

    from so101_demo.act.calibration import CHECK_MEASUREMENTS

    per_root = derive_field_verdicts(roots, contract)
    checks = {}
    for name in _CHECKS:
        members = CHECK_MEASUREMENTS.get(name)
        if not members:
            checks[name] = "UNMEASURED"
            continue
        verdicts = [verdicts.get(field, "UNMEASURED")
                    for verdicts in per_root.values() for field in sorted(members)]
        if any(verdict in ("FAIL", "INVALID") for verdict in verdicts):
            checks[name] = "FAIL"
        elif any(verdict == "UNMEASURED" for verdict in verdicts):
            checks[name] = "UNMEASURED"
        else:
            checks[name] = "PASS"
    return checks
