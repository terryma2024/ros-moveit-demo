"""Task 2: pure formulas for the 21 head-search and seven support fields.

Everything here consumes only already validated, indexed raw records - no filesystem guessing and no runtime
imports. Each field returns its configured limit, an observed summary, the reported value and the raw references
the aggregation receipt cites, so a verdict is always recomputed from raw evidence rather than read from a
label. Boolean labels (`qualified`, `target_in_view`, `contact_ok`, any `*_ok` flag) are refused outright.

The formula identifiers are read from the frozen contract v2 rather than duplicated here, so the contract stays
the single source of truth. The numeric implementations are registered in `_FORMULAS` field by field, with each
one landing together with its boundary-pass and single-point-violation cases.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType

FORBIDDEN_INPUT_LABELS = frozenset({"qualified", "target_in_view", "contact_ok", "stop_confirmed"})
_SHA256 = hashlib.sha256
_CONTRACT = Path(__file__).resolve().parents[2] / "config/act/task8-calibration-measurement-contract-v2.json"
#: field -> pure implementation; filled per field together with that field's boundary and violation cases
_FORMULAS: dict[str, object] = {}


class FieldResultSet(dict):
    """Per-field results, kept as a plain mapping so callers can serialise them canonically."""


def _load_contract(path: Path | None = None) -> dict:
    target = Path(path) if path is not None else _CONTRACT
    return json.loads(target.read_bytes())


def _formula_ids() -> MappingProxyType:
    document = _load_contract()
    identifiers = {name: entry["formula_id"] for name, entry in document["measurements"].items()}
    identifiers.update({name: entry["formula_id"] for name, entry in document["support"].items()})
    return MappingProxyType(identifiers)


FORMULA_IDS = _formula_ids()


def require_raw_inputs(payload: object) -> dict:
    """Refuse a payload that offers labels instead of raw evidence, or offers nothing at all."""

    if type(payload) is not dict or not payload.get("measurements"):
        raise ValueError("RAW_EVIDENCE_REQUIRED: no raw measurements in payload")
    offered = payload["measurements"]
    if type(offered) is not dict:
        raise ValueError("RAW_EVIDENCE_REQUIRED: measurements must be a mapping of raw records")
    for name in offered:
        if name in FORBIDDEN_INPUT_LABELS or (isinstance(name, str) and name.endswith("_ok")):
            raise ValueError(f"RAW_EVIDENCE_REQUIRED: {name} is a label, not raw evidence")
    return payload


def _compute(section: str, raw: object, contract: dict) -> FieldResultSet:
    require_raw_inputs(raw)
    results = FieldResultSet()
    for name, entry in contract[section].items():
        implementation = _FORMULAS.get(name)
        if implementation is None:
            raise ValueError(f"FORMULA_NOT_IMPLEMENTED: {name}")
        results[name] = implementation(raw, entry)
    return results


def compute_field(field: str, raw: object, contract: dict) -> dict:
    """Evaluate one field from its own raw evidence - the unit the per-field cases use."""

    require_raw_inputs(raw)
    section = "measurements" if field in contract["measurements"] else "support"
    if field not in contract[section]:
        raise ValueError(f"FIELD_UNKNOWN: {field}")
    implementation = _FORMULAS.get(field)
    if implementation is None:
        raise ValueError(f"FORMULA_NOT_IMPLEMENTED: {field}")
    return implementation(raw, contract[section][field])


def compute_head_search_fields(raw: object, contract: dict) -> FieldResultSet:
    return _compute("measurements", raw, contract)


def compute_support_fields(raw: object, contract: dict) -> FieldResultSet:
    return _compute("support", raw, contract)


def _sample(kind: str, payload: dict, *, source_commit: str, config_sha256: str,
            source_provenance_sha256: str) -> dict:
    if len(str(source_commit)) != 40 or len(str(config_sha256)) != 64 or len(str(source_provenance_sha256)) != 64:
        raise ValueError("CLOSED_SAMPLE_IDENTITY_INVALID")
    return {"schema_version": 1, "kind": kind, "status": "CLOSED", **payload,
            "source_commit": source_commit, "config_sha256": config_sha256,
            "source_provenance_sha256": source_provenance_sha256}


def build_head_closed_sample(*, head_search, observed_lock_frames, measurements, camera_measurements,
                             source_commit: str, config_sha256: str, source_provenance_sha256: str) -> dict:
    """The head closed sample carries bare reported values, never nested result objects."""

    for section in (measurements, camera_measurements):
        for name, value in section.items():
            if isinstance(value, dict):
                raise ValueError(f"CLOSED_SAMPLE_VALUE_INVALID: {name} must be a bare value")
    return _sample("task8_head_search_closed_sample",
                   {"head_search": dict(head_search), "observed_lock_frames": list(observed_lock_frames),
                    "measurements": dict(measurements), "camera_measurements": dict(camera_measurements)},
                   source_commit=source_commit, config_sha256=config_sha256,
                   source_provenance_sha256=source_provenance_sha256)


def build_support_closed_sample(*, support, source_commit: str, config_sha256: str,
                                source_provenance_sha256: str) -> dict:
    for name, value in support.items():
        if isinstance(value, dict):
            raise ValueError(f"CLOSED_SAMPLE_VALUE_INVALID: {name} must be a bare value")
    return _sample("task8_ready_support_sample", {"support": dict(support)}, source_commit=source_commit,
                   config_sha256=config_sha256, source_provenance_sha256=source_provenance_sha256)


def build_field_report(sample: dict, root: Path) -> dict:
    """Write one sample file per field and cite it, so the receipt can be re-checked later."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    report = {}
    for section in ("measurements", "camera_measurements", "support"):
        for name, value in sample.get(section, {}).items():
            target = root / f"{name}.json"
            payload = json.dumps({"field": name, "value": value}, sort_keys=True,
                                 separators=(",", ":")).encode()
            target.write_bytes(payload)
            report[name] = {"value": value, "unit": _unit_for(name),
                            "sample_path": str(target), "sample_sha256": _SHA256(payload).hexdigest()}
    return report


def _unit_for(name: str) -> str:
    document = _load_contract()
    for section in ("measurements", "support"):
        if name in document[section]:
            return document[section][name]["unit"]
    raise ValueError(f"FIELD_UNKNOWN: {name}")


# --- raw evidence shape ------------------------------------------------------------------------------------
# Every implementation reads only `raw["measurements"][field]` (the field's own raw records) and the field's
# configured limit from `raw["configured"][field]`. A missing configured limit is refused rather than defaulted,
# because the approved candidate document that supplies those limits is still pending approval (CP-879).

def _limit(raw: dict, field: str):
    configured = raw.get("configured")
    if type(configured) is not dict or field not in configured:
        raise ValueError(f"CONFIGURED_LIMIT_REQUIRED: {field}")
    return configured[field]


#: fields whose formula reads its evidence as a DOCUMENT (`evidence["K02"]`, `evidence["bboxes"]`) rather than as a
#: list. P1-2 (rereview 5) needed this because a driver cannot present one shape for both families; the tuple is
#: asserted against the formulas' own behaviour by `test_act_task8_measurement_formulas_shapes.py`, so it is a
#: declaration that cannot drift from the code it describes.
DOCUMENT_EVIDENCE_FIELDS = ("center_deadband_px", "horizontal_fov_rad")   # both read `evidence[...]`, not a list

#: fields whose formula reads the evidence as a LIST OF BBOXES through `_bboxes` - the one family a producing driver
#: can honestly fill from a detection. A behavioural probe (CP-1794) found five fields that merely TOLERATE a list
#: (`max_fine_corrections` counts its items, `search_timeout_s` sums durations), so tolerance is not the test: these
#: three are the ones the bboxes are actually about. The probe test asserts that distinction.
BBOX_EVIDENCE_FIELDS = ("min_area_px2", "min_bbox_aspect", "vertical_bounds_px")


def _evidence(raw: dict, field: str):
    evidence = raw["measurements"].get(field)
    if evidence is None:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field}")
    return evidence


def _bboxes(raw: dict, field: str, *, accepted_only: bool = True) -> list:
    boxes = list(_evidence(raw, field))
    if accepted_only:
        boxes = [box for box in boxes if box.get("accepted", True)]
    if not boxes:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no accepted bbox")
    return boxes


def _result(field: str, *, configured, observed, reported, verdict, refs=()) -> dict:
    if verdict in ("PASS", "FAIL", "INVALID", "UNMEASURED"):
        status = verdict
    else:
        status = "PASS" if verdict else "FAIL"
    return {"field": field, "configured_limit": configured, "observed_summary": observed,
            "reported_value": reported, "verdict": status, "raw_refs": list(refs)}


def _aspect(box) -> float:
    width = box["x2"] - box["x1"]
    if width <= 0:
        raise ValueError("RAW_EVIDENCE_REQUIRED: degenerate bbox width")
    return (box["y2"] - box["y1"]) / width


def _f_min_bbox_aspect(raw, entry):
    boxes = _bboxes(raw, "min_bbox_aspect")
    observed = min(_aspect(box) for box in boxes)
    limit = _limit(raw, "min_bbox_aspect")
    return _result("min_bbox_aspect", configured=limit, observed=observed, reported=limit,
                   verdict=observed >= limit)


def _f_min_area_px2(raw, entry):
    boxes = _bboxes(raw, "min_area_px2")
    observed = min((box["x2"] - box["x1"]) * (box["y2"] - box["y1"]) for box in boxes)
    limit = _limit(raw, "min_area_px2")
    return _result("min_area_px2", configured=limit, observed=observed, reported=limit,
                   verdict=observed >= limit)


def _f_center_deadband_px(raw, entry):
    field = "center_deadband_px"
    evidence = _evidence(raw, field)
    k02 = evidence["K02"]
    observed = max(abs((box["x1"] + box["x2"]) / 2 - k02) for box in evidence["bboxes"])
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed <= limit)


def _f_vertical_bounds_px(raw, entry):
    field = "vertical_bounds_px"
    centers = [(box["y1"] + box["y2"]) / 2 for box in _bboxes(raw, field)]
    observed = [min(centers), max(centers)]
    lower, upper = _limit(raw, field)
    verdict = all(lower <= center <= upper for center in centers)
    return _result(field, configured=[lower, upper], observed=observed, reported=[lower, upper],
                   verdict=verdict)


def _f_tracking_iou(raw, entry):
    field = "tracking_iou"
    pairs = [pair for pair in _evidence(raw, field) if pair.get("inherited", True)]
    if not pairs:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no inherited pair")
    observed = min(_iou(pair["previous"], pair["current"]) for pair in pairs)
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed >= limit)


def _iou(left, right) -> float:
    x1, y1 = max(left["x1"], right["x1"]), max(left["y1"], right["y1"])
    x2, y2 = min(left["x2"], right["x2"]), min(left["y2"], right["y2"])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_left = (left["x2"] - left["x1"]) * (left["y2"] - left["y1"])
    area_right = (right["x2"] - right["x1"]) * (right["y2"] - right["y1"])
    union = area_left + area_right - intersection
    if union <= 0:
        raise ValueError("RAW_EVIDENCE_REQUIRED: degenerate bbox union")
    return intersection / union


def _f_max_age_s(raw, entry):
    field = "max_age_s"
    ages = [item["decision_monotonic_s"] - item["received_monotonic_s"]
            for item in _evidence(raw, field)]
    observed = max(ages)
    limit = _limit(raw, field)
    verdict = all(0.0 <= age <= limit for age in ages)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=verdict)


def _f_max_skew_s(raw, entry):
    field = "max_skew_s"
    spreads = [max(item["stamps"]) - min(item["stamps"]) for item in _evidence(raw, field)]
    observed = max(spreads)
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=all(spread <= limit for spread in spreads))


def _f_submit_lead_s(raw, entry):
    field = "submit_lead_s"
    leads = [item["first_target_sim_s"] - item["submit_snapshot_sim_s"] for item in _evidence(raw, field)]
    observed = min(leads)
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed >= limit)


def _f_stop_latency_s(raw, entry):
    field = "stop_latency_s"
    latencies = [item["third_confirming_receive_monotonic_s"] - item["stop_request_monotonic_s"]
                 for item in _evidence(raw, field)]
    observed = max(latencies)
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=all(latency <= limit for latency in latencies))


def _f_stop_velocity_rad_s(raw, entry):
    field = "stop_velocity_rad_s"
    samples = list(_evidence(raw, field))
    if len(samples) != 3:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} needs three confirming samples")
    stamps = [sample["receive_monotonic_s"] for sample in samples]
    if not stamps[0] < stamps[1] < stamps[2]:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} samples must strictly increase")
    observed = max(max(abs(value) for value in sample["velocity_rad_s"]) for sample in samples)
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed <= limit)


def _f_path_step_s(raw, entry):
    field = "path_step_s"
    steps = list(_evidence(raw, field))
    deltas = [later - earlier for earlier, later in zip(steps, steps[1:])]
    if not deltas:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} needs adjacent grid stamps")
    limit = _limit(raw, field)
    verdict = all(0 < delta <= limit for delta in deltas)
    return _result(field, configured=limit, observed=max(deltas), reported=limit, verdict=verdict)


def _f_min_confidence(raw, entry):
    field = "min_confidence"
    observed = min(_evidence(raw, field))
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed >= limit)


def _f_max_fine_corrections(raw, entry):
    field = "max_fine_corrections"
    observed = len(list(_evidence(raw, field)))
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed <= limit)


def _f_max_fine_total_rad(raw, entry):
    field = "max_fine_total_rad"
    observed = sum(abs(delta) for delta in _evidence(raw, field))
    limit = _limit(raw, field)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=observed <= limit)


_FORMULAS.update({
    "min_bbox_aspect": _f_min_bbox_aspect,
    "min_area_px2": _f_min_area_px2,
    "center_deadband_px": _f_center_deadband_px,
    "vertical_bounds_px": _f_vertical_bounds_px,
    "tracking_iou": _f_tracking_iou,
    "max_age_s": _f_max_age_s,
    "max_skew_s": _f_max_skew_s,
    "submit_lead_s": _f_submit_lead_s,
    "stop_latency_s": _f_stop_latency_s,
    "stop_velocity_rad_s": _f_stop_velocity_rad_s,
    "path_step_s": _f_path_step_s,
    "min_confidence": _f_min_confidence,
    "max_fine_corrections": _f_max_fine_corrections,
    "max_fine_total_rad": _f_max_fine_total_rad,
})


def _f_horizontal_fov_rad(raw, entry):
    field = "horizontal_fov_rad"
    evidence = _evidence(raw, field)
    frames = []
    for frame in evidence["frames"]:
        fx, cx, width = frame["fx"], frame["cx"], frame["width"]
        if not fx or not width:
            raise ValueError("RAW_EVIDENCE_REQUIRED: degenerate camera intrinsics")
        value = math.atan(cx / fx) + math.atan((width - cx) / fx)
        if not math.isfinite(value):
            raise ValueError("RAW_EVIDENCE_REQUIRED: non-finite fov")
        frames.append(value)
    if not frames:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no valid frame")
    observed = min(frames)
    limit = _limit(raw, field)
    tolerance = evidence["tolerance_rad"]
    drift = max(frames) - observed
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=abs(observed - evidence["model_fov_rad"]) <= tolerance and drift <= tolerance)


def _f_search_timeout_s(raw, entry):
    field = "search_timeout_s"
    limit = _limit(raw, field)
    anchors = list(_evidence(raw, field))
    if not anchors:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no anchor")
    elapsed = []
    for anchor in anchors:
        terminal = anchor.get("terminal_monotonic_s")
        if terminal is None:
            return _result(field, configured=limit, observed=None, reported=limit, verdict="INVALID",
                           refs=[anchor.get("anchor", "?")])
        elapsed.append(terminal - anchor["started_monotonic_s"])
    observed = max(elapsed)
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=all(value <= limit for value in elapsed))


def _f_coarse_step_rad(raw, entry):
    field = "coarse_step_rad"
    limit = _limit(raw, field)
    events = list(_evidence(raw, field))
    if not events:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no state event")
    steps = [event["coarse_accumulator_after"] - event["coarse_accumulator_before"] for event in events]
    full, final = steps[:-1], steps[-1]
    observed = min(steps)
    verdict = (all(step == limit for step in full)
               and 0 < final <= limit)
    return _result(field, configured=limit, observed=observed, reported=limit, verdict=verdict)


_FORMULAS.update({
    "horizontal_fov_rad": _f_horizontal_fov_rad,
    "search_timeout_s": _f_search_timeout_s,
    "coarse_step_rad": _f_coarse_step_rad,
})


# --- camera and TF group: head and wrist share one implementation each --------------------------------------

def _median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _wrap_pi(angle: float) -> float:
    wrapped = math.fmod(angle + math.pi, 2 * math.pi)
    if wrapped <= 0:
        wrapped += 2 * math.pi
    return wrapped - math.pi


def _circular_median(angles: list) -> float:
    """The angle minimising the total circular distance to the samples, tie-broken by smallest value."""

    if not angles:
        raise ValueError("RAW_EVIDENCE_REQUIRED: no angle samples")
    def total(candidate):
        return sum(abs(_wrap_pi(sample - candidate)) for sample in angles)
    best = min(angles, key=lambda candidate: (total(candidate), candidate))
    return _wrap_pi(best)


def _zyx_from_quaternion(quaternion) -> tuple:
    x, y, z, w = quaternion
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if not math.isfinite(norm) or abs(norm - 1.0) > 1e-6:
        raise ValueError("RAW_EVIDENCE_REQUIRED: quaternion is not unit length")
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def _f_intrinsics(field):
    def compute(raw, entry):
        evidence = _evidence(raw, field)
        frames = list(evidence["frames"])
        if not frames:
            raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no frame")
        limit = _limit(raw, field)
        tolerance = evidence["tolerance_px"]
        modelled = []
        components = []
        for frame in frames:
            if (frame["width"], frame["height"]) != (640, 480):
                return _result(field, configured=limit, observed=None, reported=limit, verdict="FAIL")
            components.append(list(frame["K"]))
            fx = (frame["height"] / 2) / math.tan(frame["fovy_rad"] / 2)
            modelled.append([fx, fx, frame["width"] / 2, frame["height"] / 2])
        observed = [_median([row[index] for row in components]) for index in range(4)]
        spread = max(max(row[index] for row in components) - min(row[index] for row in components)
                     for index in range(4))
        cross_check = max(abs(observed[index] - modelled[0][index]) for index in range(4))
        return _result(field, configured=limit, observed=observed, reported=limit,
                       verdict=spread <= tolerance and cross_check <= tolerance)
    return compute


def _f_translation(field):
    def compute(raw, entry):
        evidence = _evidence(raw, field)
        samples = list(evidence["samples"])
        if not samples:
            raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no sample")
        limit = _limit(raw, field)
        observed = [_median([sample[index] for sample in samples]) for index in range(3)]
        expected = evidence["expected"]
        tolerance = evidence["tolerance_m"]
        verdict = all(abs(observed[index] - expected[index]) <= tolerance for index in range(3))
        return _result(field, configured=limit, observed=observed, reported=limit, verdict=verdict)
    return compute


def _f_rpy(field):
    def compute(raw, entry):
        evidence = _evidence(raw, field)
        quaternions = list(evidence["quaternions"])
        if not quaternions:
            raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no sample")
        limit = _limit(raw, field)
        decomposed = [_zyx_from_quaternion(quaternion) for quaternion in quaternions]
        observed = [_wrap_pi(_median([row[index] for row in decomposed])) for index in range(3)]
        expected = evidence.get("expected")
        tolerance = evidence.get("tolerance_rad", 0.0)
        verdict = True if expected is None else all(
            abs(_wrap_pi(observed[index] - expected[index])) <= tolerance for index in range(3))
        return _result(field, configured=limit, observed=observed, reported=limit, verdict=verdict)
    return compute


def _f_yaw_bearing(field):
    def compute(raw, entry):
        evidence = _evidence(raw, field)
        rotations = list(evidence["rotations"])
        if not rotations:
            raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no sample")
        limit = _limit(raw, field)
        bearings = []
        for rotation in rotations:
            forward_z = [rotation[2], rotation[5], rotation[8]]        # R * [0, 0, 1]
            magnitude = math.hypot(forward_z[0], forward_z[1])
            if magnitude == 0.0:
                raise ValueError("RAW_EVIDENCE_REQUIRED: degenerate forward axis")
            bearings.append(_wrap_pi(math.atan2(forward_z[1], forward_z[0])))
        observed = _circular_median(bearings)
        expected = evidence.get("expected")
        tolerance = evidence.get("tolerance_rad", 0.0)
        verdict = True if expected is None else abs(_wrap_pi(observed - expected)) <= tolerance
        return _result(field, configured=limit, observed=observed, reported=limit, verdict=verdict)
    return compute


for _name in ("head_intrinsics_px", "wrist_intrinsics_px"):
    _FORMULAS[_name] = _f_intrinsics(_name)
for _name in ("head_translation_m", "wrist_translation_m"):
    _FORMULAS[_name] = _f_translation(_name)
for _name in ("head_rpy_rad", "wrist_rpy_rad"):
    _FORMULAS[_name] = _f_rpy(_name)
_FORMULAS["yaw_zero_bearing_rad"] = _f_yaw_bearing("yaw_zero_bearing_rad")


# --- the remaining four: neck interval, installed limits, path clearance -----------------------------------

def _f_lock_valid_neck_rad(raw, entry):
    """Select the unique safe connected component that contains 0 and every anchor start."""

    field = "lock_valid_neck_rad"
    evidence = _evidence(raw, field)
    lower, upper = evidence["bounds_rad"]
    starts = list(evidence["anchor_starts_rad"])
    if not starts:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no anchor start")
    unsafe = sorted(tuple(bound) for bound in evidence["unsafe_intervals_rad"])
    safe, cursor = [], lower
    for start, stop in unsafe:
        if start > cursor:
            safe.append((cursor, start))
        cursor = max(cursor, stop)
    if cursor < upper:
        safe.append((cursor, upper))
    containing_zero = [span for span in safe if span[0] <= 0.0 <= span[1]]
    if any(span[0] <= 0.0 <= span[1] for span in safe) is False:
        return _result(field, configured=[lower, upper], observed=None, reported=None, verdict="FAIL")
    viable = [span for span in containing_zero if all(span[0] <= start <= span[1] for start in starts)]
    if len(viable) != 1:
        return _result(field, configured=[lower, upper], observed=[span for span in viable],
                       reported=None, verdict="FAIL")
    shrink = evidence["shrink_rad"]
    span_lower, span_upper = viable[0]
    return _result(field, configured=[lower, upper],
                   observed=[span_lower, span_upper],
                   reported=[span_lower + shrink, span_upper - shrink], verdict="PASS")


def _f_velocity_limit_rad_s(raw, entry):
    field = "velocity_limit_rad_s"
    evidence = _evidence(raw, field)
    limit = list(_limit(raw, field))
    samples = list(evidence["samples"])
    if not samples:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no sample")
    dimensions = len(limit)
    observed = [0.0] * dimensions
    for sample in samples:
        if sample["dt_s"] <= 0:
            return _result(field, configured=limit, observed=None, reported=limit, verdict="INVALID")
        for index in range(dimensions):
            rate = abs(sample["dq_rad"][index]) / sample["dt_s"]
            observed[index] = max(observed[index], rate)
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=all(observed[index] <= limit[index] for index in range(dimensions)))


def _f_acceleration_limit_rad_s2(raw, entry):
    field = "acceleration_limit_rad_s2"
    evidence = _evidence(raw, field)
    limit = list(_limit(raw, field))
    samples = list(evidence["samples"])
    if len(samples) < 3:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} needs at least three samples")
    dimensions = len(limit)
    velocities = []
    for previous, current in zip(samples, samples[1:]):
        interval = current["time_s"] - previous["time_s"]
        if interval <= 0:
            return _result(field, configured=limit, observed=None, reported=limit, verdict="INVALID")
        velocities.append([(current["position_rad"][index] - previous["position_rad"][index]) / interval
                           for index in range(dimensions)])
    observed = [0.0] * dimensions
    for previous, current in zip(velocities, velocities[1:]):
        interval = samples[velocities.index(current) + 1]["time_s"] - samples[velocities.index(previous) + 1]["time_s"]
        if interval <= 0:
            return _result(field, configured=limit, observed=None, reported=limit, verdict="INVALID")
        for index in range(dimensions):
            observed[index] = max(observed[index], abs(current[index] - previous[index]) / interval)
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=all(observed[index] <= limit[index] for index in range(dimensions)))


def _f_path_clearance_m(raw, entry):
    field = "path_clearance_m"
    evidence = _evidence(raw, field)
    limit = _limit(raw, field)
    rows = list(evidence["rows"])
    if not rows:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no grid row")
    allowlist = {tuple(pair) for pair in evidence.get("allowlisted_contacts", [])}
    adjudicated = []
    for row in rows:
        pair = row.get("contact_pair")
        if pair is not None and tuple(pair) in allowlist:
            adjudicated.append(row)                      # explicit allowlisted contact: adjudicated per phase
            continue
        if pair is not None:
            return _result(field, configured=limit, observed=row["signed_distance_m"], reported=limit,
                           verdict="FAIL")
    distances = [row["signed_distance_m"] for row in rows if row.get("contact_pair") is None]
    if not distances:
        raise ValueError(f"RAW_EVIDENCE_REQUIRED: {field} has no non-contact row")
    observed = min(distances)
    return _result(field, configured=limit, observed=observed, reported=limit,
                   verdict=observed >= limit,
                   refs=[f"allowlisted_contacts={len(adjudicated)}"])


_FORMULAS.update({
    "lock_valid_neck_rad": _f_lock_valid_neck_rad,
    "velocity_limit_rad_s": _f_velocity_limit_rad_s,
    "acceleration_limit_rad_s2": _f_acceleration_limit_rad_s2,
    "path_clearance_m": _f_path_clearance_m,
})
