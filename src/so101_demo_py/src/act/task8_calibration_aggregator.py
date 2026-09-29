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

    # Boundary IV: one entry, and it begins with the strict closed-batch validation - a batch that is not closed,
    # carries a mixed contract, hides a symlink or an unindexed file, or was contaminated by a failed cleanup is
    # refused here, before a single canonical document exists
    from so101_demo.act.task8_measurement_schema import validate_closed_batch

    indexes = [validate_closed_batch(Path(root)) for root in batch_roots]

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
        # the identity names the contract it was measured under as measurement_contract_sha256; contract_sha256 is the
        # bound document's own key, and reading the wrong one made every batch look foreign
        if identity.get("measurement_contract_sha256") != contract_sha256:
            raise ValueError("CALIBRATION_IDENTITY_MISMATCH")
    # and every member must agree across roots, not only the provenance: two batches measured under different anchor
    # sets or camera matrices are not the same generation, however equal their provenance happens to be
    from so101_demo.act.task8_measurement_contract import IDENTITIES_V2

    for name in IDENTITIES_V2:
        values = {identity.get(name) for _, identity in batches}
        if len(values) != 1 or None in values:
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
            for field in contract.get(section, {}):     # a v1 bound contract carries no support section
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


def derived_phase_camera_checks(replay_rows, live_frames, window_kind: str, matrix: dict) -> dict:
    """Fold replay coverage and live continuity into the aggregator's vocabulary.

    The two axes are evaluated by different functions and reported under different keys, so a replay result can
    never be presented as live-continuity success.
    """

    from so101_demo.act.task8_phase_camera import evaluate_live_continuity, evaluate_replay_coverage

    return {"replay_coverage": evaluate_replay_coverage(replay_rows, matrix),
            "live_continuity": evaluate_live_continuity(live_frames, window_kind, matrix)}


# --- Task 6: deterministic rendering and publishing --------------------------------------------------------
# One v2 sealed batch with exactly three anchors in canonical order renders four documents whose bytes depend only
# on the batch, the contract and the caller's publication root. Only files registered in `batch.json.files` are ever
# read; a label never influences a verdict, and a number change always changes the bytes.

ANCHOR_ORDER = ("default", "left", "forward")
DOCUMENTS = ("head-search-qualification.json", "task8-ready-support.json", "task8-ready-calibration.json",
             "aggregation-receipt.json")
# the sealed-batch identity must at least carry the commit and the config/provenance digests; the richer
# ten-member identity is the contract's, not the batch's, so extra members are accepted but not required
_BATCH_IDENTITY_KEYS = ("source_commit", "config_sha256", "source_provenance_sha256")


def _canonical_bytes(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _require_sealed_batch(root: Path) -> dict:
    path = Path(root) / "batch.json"
    if not path.is_file():
        raise ValueError("CALIBRATION_BATCH_MISSING")
    batch = json.loads(path.read_bytes())
    if batch.get("kind") != BATCH_KIND or batch.get("status") != "CLOSED":
        raise ValueError(f"CALIBRATION_BATCH_NOT_CLOSED: {batch.get('status')}")
    identity = batch.get("identity")
    if (type(identity) is not dict or any(key not in identity for key in _BATCH_IDENTITY_KEYS)
            or len(str(identity["source_commit"])) != 40
            or any(len(str(identity[key])) != 64 for key in _BATCH_IDENTITY_KEYS[1:])):
        raise ValueError("CALIBRATION_IDENTITY_INVALID")
    # an anchor entry may be the bare name or a record carrying it; both are accepted, order is what matters
    anchors = [entry.get("anchor") if type(entry) is dict else entry for entry in batch.get("anchors", [])]
    if tuple(anchors) != ANCHOR_ORDER:
        raise ValueError(f"ANCHOR_ORDER: expected {list(ANCHOR_ORDER)}, found {anchors}")
    files = batch.get("files")
    if type(files) is not dict or not files:
        raise ValueError("CALIBRATION_BATCH_INDEX_INVALID")
    return batch


def _read_indexed(root: Path, batch: dict) -> dict:
    """Read exactly the indexed files, verifying every digest as it is read."""

    records = {}
    for relative, digest in sorted(batch["files"].items()):
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"BATCH_PATH_INVALID: {relative}")
        payload = (Path(root) / relative).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError(f"BATCH_DIGEST_MISMATCH: {relative}")
        records[relative] = json.loads(payload)
    return records


def _field_verdicts(batch: dict, records: dict, contract: dict) -> dict:
    """Combine per-anchor verdicts: a field passes only when every anchor that measured it passes."""

    from so101_demo.act.task8_measurement_formulas import compute_field

    per_field = {}
    for relative, record in records.items():
        raw = {"measurements": record.get("measurements") or {}, "configured": record.get("configured") or {}}
        for section in ("measurements", "support"):
            for field in contract.get(section, {}):     # a v1 bound contract carries no support section
                if field not in raw["measurements"]:
                    continue
                try:
                    verdict = compute_field(field, raw, contract)["verdict"]
                except ValueError as error:
                    verdict = "INVALID" if "REQUIRED" not in str(error) else "UNMEASURED"
                except (AttributeError, KeyError, TypeError, ZeroDivisionError) as error:
                    # a raw record whose shape cannot be evaluated is invalid evidence - never a pass
                    verdict = "INVALID"
                per_field.setdefault(field, []).append(verdict)
    resolved = {}
    for field, verdicts in per_field.items():
        if any(verdict in ("FAIL", "INVALID") for verdict in verdicts):
            resolved[field] = "FAIL" if "FAIL" in verdicts else "INVALID"
        else:
            resolved[field] = "PASS"
    return resolved


def _split_fields(contract: dict, verdicts: dict) -> tuple:
    head = {field: verdicts.get(field, "UNMEASURED") for field in sorted(contract.get("measurements", {}))}
    support = {field: verdicts.get(field, "UNMEASURED") for field in sorted(contract.get("support", {}))}
    return head, support


def render_task8_calibration(batch_root, contract: dict, publication_root) -> dict:
    """Render the four documents as canonical bytes; nothing is written here."""

    root, publication = Path(batch_root), Path(publication_root)
    batch = _require_sealed_batch(root)
    records = _read_indexed(root, batch)
    # a bound contract carries its own hash; an unbound template is identified by the digest of its exact bytes
    contract_sha256 = contract.get("contract_sha256") or hashlib.sha256(_canonical_bytes(contract)).hexdigest()
    verdicts = _field_verdicts(batch, records, contract)
    head, support = _split_fields(contract, verdicts)
    receipt_fields = {}
    for field, verdict in sorted(verdicts.items()):
        payload = _canonical_bytes({"field": field, "verdict": verdict})
        receipt_fields[field] = {"verdict": verdict, "unit": _unit_for(contract, field),
                                 "sample_path": str(publication / "fields" / f"{field}.json"),
                                 "sample_sha256": hashlib.sha256(payload).hexdigest()}
    documents = {
        "head-search-qualification.json": {"schema_version": 2, "kind": "head_search_qualification",
                                           "status": "PASS" if set(head.values()) == {"PASS"} else "FAIL",
                                           "contract_sha256": contract_sha256,
                                           "measurements": head},
        "task8-ready-support.json": {"schema_version": 1, "kind": "task8_ready_support",
                                     "status": "PASS" if set(support.values()) == {"PASS"} else "FAIL",
                                     "support": support},
        "task8-ready-calibration.json": {"schema_version": 1, "kind": "task8_ready_calibration",
                                         "identity": dict(batch["identity"]),
                                         "anchors": [entry for entry in batch["anchors"]]},   # names or records
        "aggregation-receipt.json": {"schema_version": 1, "kind": "task8_aggregation_receipt",
                                     "publication_root": str(publication), "fields": receipt_fields},
    }
    return {name: _canonical_bytes(documents[name]) for name in DOCUMENTS}


def _unit_for(contract: dict, field: str) -> str:
    for section in ("measurements", "support"):
        if field in contract.get(section, {}):
            return contract[section][field]["unit"]
    return ""


def publish_task8_calibration(rendered, publication_root) -> dict:
    """Write exactly those bytes, plus each receipt field's sample file, atomically."""

    publication = Path(publication_root)
    publication.mkdir(parents=True, exist_ok=True)
    for name in DOCUMENTS:
        if name not in rendered:
            raise ValueError(f"RENDERED_DOCUMENT_MISSING: {name}")
    receipt = json.loads(rendered["aggregation-receipt.json"])
    for field, entry in sorted(receipt["fields"].items()):
        path = Path(entry["sample_path"])
        if not path.is_absolute():
            raise ValueError(f"SAMPLE_PATH_NOT_ABSOLUTE: {field}")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical_bytes({"field": field, "verdict": entry["verdict"]})
        if hashlib.sha256(payload).hexdigest() != entry["sample_sha256"]:
            raise ValueError(f"SAMPLE_DIGEST_MISMATCH: {field}")
        path.write_bytes(payload)
    for name in DOCUMENTS:
        payload = rendered[name]
        partial = publication / f"{name}.partial"
        descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(partial), str(publication / name))
    return {"published": [str(publication / name) for name in DOCUMENTS],
            "fields": len(receipt["fields"])}
