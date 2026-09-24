"""Fail-closed analysis of ACT MuJoCo contact calibration cohorts.

The analyzer uses offline samples only to fit thresholds. Live samples and
negative controls are independent evaluation evidence. No function here can
activate a policy or drive a robot.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

from so101_demo.act.contact_policy import (
    canonical_policy_payload, policy_fingerprint, verify_activation,
)

REGIMES = (
    "no_contact", "bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold"
)
CONTROLS = ("table_only", "post_release", "left_only", "right_only")
_SAMPLE_KEYS = frozenset(
    {"sample_id", "source", "regime", "simulation_session_id", "reset_epoch",
     "scenario", "scenario_sha256", "frames", "collected_monotonic_s",
     "model_sha256", "scene_sha256", "motion_policy_sha256",
     "collector_sha256", "config_sha256", "clock_origin", "diagnostic_result"}
)
_FRAME_KEYS = frozenset(
    {"physics_step", "simulation_time_s", "ros_time_s", "received_monotonic_s",
     "left_contacts", "right_contacts", "other_contacts", "cup_position_m",
     "cup_velocity_m_s", "model_qpos", "model_qvel", "table_supported", "released"}
)
_SCENARIO_KEYS = frozenset(
    {"regime", "seed", "cup_start_m", "gripper_close_q6", "window_first_step", "window_last_step"}
)
_DIAGNOSTIC_KEYS = frozenset(
    {"status", "peak_force_n", "peak_displacement_m"}
)
_CONTACT_KEYS = frozenset(
    {"robot_geom", "object_body", "normal_force_n", "signed_distance_m"}
)
_METADATA_KEYS = frozenset(
    {"mujoco_version", "model_sha256", "scene_sha256", "motion_policy_sha256",
     "collector_sha256", "live_collector_sha256", "analyzer_sha256", "config_sha256", "evaluation",
     "diagnostic_limits", "policy_id", "allowed_other_contact_bodies"}
)
_LIMIT_KEYS = frozenset(
    {"maximum_force_n", "maximum_displacement_m", "maximum_ros_skew_s",
     "maximum_receipt_age_s"}
)


def _exact(value: Any, keys: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has missing or unknown fields")
    return value


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{name} must be finite and at least {minimum}")
    return result


def _integer(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _vector(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must be a three-vector")
    return tuple(_number(item, name) for item in value)


def _state_vector(value: Any, name: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a nonempty state vector")
    for item in value:
        _number(item, name)


def _contact_values(items: Any, name: str, maximum_force: float) -> tuple[float, float]:
    if not isinstance(items, list):
        raise ValueError(f"{name} must be a contact list")
    total_force = 0.0
    minimum_distance = 0.0
    for item in items:
        contact = _exact(item, _CONTACT_KEYS, name)
        for identity in ("robot_geom", "object_body"):
            if not isinstance(contact[identity], str) or not contact[identity]:
                raise ValueError(f"{name}.{identity} is missing")
        force = _number(contact["normal_force_n"], "normal_force_n", minimum=0)
        if force > maximum_force:
            raise ValueError("diagnostic hard force limit exceeded")
        total_force += force
        if total_force > maximum_force:
            raise ValueError("diagnostic hard force limit exceeded")
        minimum_distance = min(
            minimum_distance, _number(contact["signed_distance_m"], "signed_distance_m")
        )
    return total_force, minimum_distance


def _validated_sample(
    sample_value: Any, source: str, limits: dict[str, float], metadata: dict[str, Any]
) -> dict[str, Any]:
    sample = _exact(sample_value, _SAMPLE_KEYS, "calibration sample provenance")
    if sample["source"] != source or sample["regime"] not in (*REGIMES, *CONTROLS):
        raise ValueError("sample source or regime mismatch")
    if not isinstance(sample["sample_id"], str) or not sample["sample_id"]:
        raise ValueError("sample_id is missing")
    if not isinstance(sample["simulation_session_id"], str) or not sample["simulation_session_id"]:
        raise ValueError("simulation_session_id is missing")
    _integer(sample["reset_epoch"], "reset_epoch")
    for field in ("model_sha256", "scene_sha256", "motion_policy_sha256", "config_sha256"):
        if sample[field] != metadata[field]:
            raise ValueError(f"sample {field} provenance mismatch")
    expected_collector = metadata[
        "collector_sha256" if source == "offline" else "live_collector_sha256"]
    if sample["collector_sha256"] != expected_collector:
        raise ValueError("sample collector_sha256 provenance mismatch")
    expected_clock = "mujoco_simulated_ros" if source == "offline" else "ros_clock"
    if sample["clock_origin"] != expected_clock:
        raise ValueError("sample clock provenance mismatch")
    scenario = _exact(sample["scenario"], _SCENARIO_KEYS, "scenario")
    if scenario["regime"] != sample["regime"]:
        raise ValueError("scenario regime mismatch")
    _integer(scenario["seed"], "scenario.seed")
    _vector(scenario["cup_start_m"], "scenario.cup_start_m")
    _number(scenario["gripper_close_q6"], "scenario.gripper_close_q6")
    first_step = _integer(scenario["window_first_step"], "scenario.window_first_step")
    last_step = _integer(scenario["window_last_step"], "scenario.window_last_step")
    if last_step <= first_step:
        raise ValueError("scenario window is invalid")
    digest = sample["scenario_sha256"]
    if digest != hashlib.sha256(_canonical(scenario)).hexdigest():
        raise ValueError("scenario_sha256 does not match parameters")
    frames = sample["frames"]
    if not isinstance(frames, list) or len(frames) < 2:
        raise ValueError("raw contact stream must contain at least two frames")
    initial_position = None
    previous_step = -1
    previous_time = -math.inf
    previous_ros = -math.inf
    previous_receipt = -math.inf
    left_force = right_force = maximum_force = 0.0
    minimum_distance = 0.0
    maximum_speed = 0.0
    maximum_displacement = 0.0
    bilateral_times = []
    for frame_value in frames:
        frame = _exact(frame_value, _FRAME_KEYS, "contact frame")
        step = _integer(frame["physics_step"], "physics_step")
        if step < first_step or step > last_step:
            raise ValueError("frame is outside the declared scenario window")
        sim_time = _number(frame["simulation_time_s"], "simulation_time_s", minimum=0)
        ros_time = _number(frame["ros_time_s"], "ros_time_s", minimum=0)
        receipt = _number(frame["received_monotonic_s"], "received_monotonic_s", minimum=0)
        if step <= previous_step or sim_time <= previous_time or ros_time <= previous_ros or receipt <= previous_receipt:
            raise ValueError("stale, duplicated or reset contact stream")
        if abs(ros_time - sim_time) > limits["maximum_ros_skew_s"]:
            raise ValueError("ROS and MuJoCo clocks diverged")
        previous_step, previous_time, previous_ros, previous_receipt = step, sim_time, ros_time, receipt
        position = _vector(frame["cup_position_m"], "cup_position_m")
        if initial_position is None:
            initial_position = position
        if math.dist(position, initial_position) > limits["maximum_displacement_m"]:
            raise ValueError("diagnostic displacement limit exceeded")
        maximum_displacement = max(maximum_displacement, math.dist(position, initial_position))
        _state_vector(frame["model_qpos"], "model_qpos")
        _state_vector(frame["model_qvel"], "model_qvel")
        speed = math.sqrt(sum(v * v for v in _vector(frame["cup_velocity_m_s"], "cup_velocity_m_s")))
        maximum_speed = max(maximum_speed, speed)
        forces = []
        for field in ("left_contacts", "right_contacts", "other_contacts"):
            forces.append(_contact_values(frame[field], field, limits["maximum_force_n"]))
        if sum(force for force, _ in forces) > limits["maximum_force_n"]:
            raise ValueError("diagnostic hard force limit exceeded")
        maximum_force = max(maximum_force, sum(force for force, _ in forces))
        left_force = max(left_force, forces[0][0])
        right_force = max(right_force, forces[1][0])
        maximum_force = max(maximum_force, *(force for force, _ in forces))
        minimum_distance = min(minimum_distance, forces[0][1], forces[1][1])
        if frame["left_contacts"] and frame["right_contacts"]:
            bilateral_times.append(sim_time)
        if type(frame["table_supported"]) is not bool or type(frame["released"]) is not bool:
            raise ValueError("support/release status must be boolean")
        table_contact = any(
            item["robot_geom"] == "table_collision"
            for item in frame["other_contacts"]
        )
        if frame["table_supported"] != table_contact:
            raise ValueError("table support disagrees with raw contact stream")
    collected = _number(sample["collected_monotonic_s"], "collected_monotonic_s", minimum=0)
    if frames[0]["physics_step"] != first_step or frames[-1]["physics_step"] != last_step:
        raise ValueError("scenario window is not fully recorded")
    diagnostic = _exact(sample["diagnostic_result"], _DIAGNOSTIC_KEYS, "diagnostic result")
    if diagnostic["status"] != "PASS" or not math.isclose(
        _number(diagnostic["peak_force_n"], "diagnostic peak force", minimum=0),
        maximum_force, rel_tol=0, abs_tol=1e-9,
    ) or not math.isclose(
        _number(diagnostic["peak_displacement_m"], "diagnostic peak displacement", minimum=0),
        maximum_displacement, rel_tol=0, abs_tol=1e-9,
    ):
        raise ValueError("diagnostic result disagrees with raw stream")
    if collected < previous_receipt or collected - previous_receipt > limits["maximum_receipt_age_s"]:
        raise ValueError("last contact receipt is stale")
    last = frames[-1]
    left = bool(last["left_contacts"])
    right = bool(last["right_contacts"])
    regime = sample["regime"]
    if regime in {"no_contact", "table_only", "post_release"} and (left or right):
        raise ValueError("negative control contains fingertip contact")
    if regime == "left_only" and (not left or right):
        raise ValueError("left-only control has wrong contact shape")
    if regime == "right_only" and (left or not right):
        raise ValueError("right-only control has wrong contact shape")
    if regime in {"bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold"} and not (left and right):
        raise ValueError("positive regime lacks bilateral contact")
    if regime == "table_only" and not last["table_supported"]:
        raise ValueError("table-only control lacks table support")
    if regime == "post_release" and (not last["released"] or not last["table_supported"]):
        raise ValueError("post-release control lacks release/support")
    if regime in {"micro_lift_slip", "stable_hold"} and last["table_supported"]:
        raise ValueError("off-table regime still has table support")
    if regime == "bilateral_touch" and not last["table_supported"]:
        raise ValueError("table-contact regime lacks support")
    duration = bilateral_times[-1] - bilateral_times[0] if len(bilateral_times) >= 2 else 0.0
    return {
        "sample_id": sample["sample_id"], "source": source, "regime": regime,
        "bilateral_force_n": min(left_force, right_force),
        "maximum_normal_force_n": maximum_force,
        "maximum_compression_distance_m": -minimum_distance,
        "maximum_linear_speed_m_s": maximum_speed,
        "bilateral_duration_s": duration,
        "left_contact": left, "right_contact": right,
    }


def _separating(negative: list[float], positive: list[float], name: str) -> float:
    if not negative or not positive:
        raise ValueError(f"{name} has no fitting samples")
    lower, upper = max(negative), min(positive)
    if lower >= upper:
        raise ValueError(f"{name} distributions overlap")
    return (lower + upper) / 2


def _classify(sample: dict[str, Any], thresholds: dict[str, float]) -> str:
    if not sample["left_contact"] and not sample["right_contact"]:
        return "no_contact"
    if sample["left_contact"] and not sample["right_contact"]:
        return "left_only"
    if sample["right_contact"] and not sample["left_contact"]:
        return "right_only"
    if (sample["maximum_compression_distance_m"] >= thresholds["maximum_compression_distance_m"]
            or sample["maximum_normal_force_n"] >= thresholds["maximum_safe_force_n"]):
        return "over_compression"
    if sample["maximum_linear_speed_m_s"] >= thresholds["maximum_hold_linear_speed_m_s"]:
        return "micro_lift_slip"
    if sample["bilateral_duration_s"] >= thresholds["minimum_stable_hold_duration_s"]:
        return "stable_hold"
    return "bilateral_touch"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def analyze_evidence(offline: dict[str, Any], live: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Fit on 20 deterministic samples and evaluate on five isolated live samples per regime."""

    meta = _exact(metadata, _METADATA_KEYS, "calibration metadata")
    limits = _exact(meta["diagnostic_limits"], _LIMIT_KEYS, "diagnostic limits")
    checked_limits = {name: _number(value, name, minimum=0) for name, value in limits.items()}
    if any(value == 0 for value in checked_limits.values()):
        raise ValueError("diagnostic limits must be positive")
    # This is a diagnostic hard-stop contract, not a proposed threshold.
    grouped = {}
    ids = set()
    sessions = set()
    for source, cohort, expected in (("offline", offline, 20), ("live", live, 5)):
        item = _exact(cohort, frozenset({"source", "samples"}), f"{source} cohort")
        if item["source"] != source or not isinstance(item["samples"], list):
            raise ValueError("cohort source mismatch")
        parsed = [_validated_sample(sample, source, checked_limits, meta) for sample in item["samples"]]
        for original in item["samples"]:
            if original["sample_id"] in ids or original["simulation_session_id"] in sessions:
                raise ValueError("offline/live sample or session identity reused")
            ids.add(original["sample_id"])
            sessions.add(original["simulation_session_id"])
        counts = Counter(sample["regime"] for sample in parsed)
        if any(counts[name] != expected for name in REGIMES):
            raise ValueError("five regimes require exact independent 20/5 cohorts")
        if any(counts[name] < 1 for name in CONTROLS):
            raise ValueError("table, release and unilateral negative controls are required")
        grouped[source] = {name: [sample for sample in parsed if sample["regime"] == name]
                           for name in (*REGIMES, *CONTROLS)}
    fit = grouped["offline"]
    bilateral = [sample for name in REGIMES[1:] for sample in fit[name]]
    normal = [sample for name in ("bilateral_touch", "micro_lift_slip", "stable_hold") for sample in fit[name]]
    negatives = [sample for name in ("no_contact", *CONTROLS) for sample in fit[name]]
    thresholds = {
        "minimum_bilateral_force_n": _separating(
            [s["bilateral_force_n"] for s in negatives], [s["bilateral_force_n"] for s in bilateral], "bilateral force"),
        "maximum_compression_distance_m": _separating(
            [s["maximum_compression_distance_m"] for s in normal],
            [s["maximum_compression_distance_m"] for s in fit["over_compression"]], "compression"),
        "maximum_safe_force_n": _separating(
            [s["maximum_normal_force_n"] for s in normal],
            [s["maximum_normal_force_n"] for s in fit["over_compression"]], "safe force"),
        "maximum_hold_linear_speed_m_s": _separating(
            [s["maximum_linear_speed_m_s"] for s in fit["stable_hold"]],
            [s["maximum_linear_speed_m_s"] for s in fit["micro_lift_slip"]], "hold speed"),
        "minimum_stable_hold_duration_s": _separating(
            [s["bilateral_duration_s"] for s in fit["bilateral_touch"]],
            [s["bilateral_duration_s"] for s in fit["stable_hold"]], "stable duration"),
    }
    confusion = {regime: {predicted: 0 for predicted in (*REGIMES, "left_only", "right_only")}
                 for regime in REGIMES}
    for regime in REGIMES:
        for sample in grouped["live"][regime]:
            confusion[regime][_classify(sample, thresholds)] += 1
    controls = {name: [_classify(sample, thresholds) for sample in grouped["live"][name]]
                for name in CONTROLS}
    if any(confusion[regime][regime] != 5 for regime in REGIMES):
        raise ValueError("live hold/compression classification has false results")
    if any(pred == "stable_hold" for values in controls.values() for pred in values):
        raise ValueError("negative control was classified as stable hold")
    for side in ("left_only", "right_only"):
        if any(pred != side for pred in controls[side]):
            raise ValueError("unilateral rejection contract failed")
    source_hash = hashlib.sha256(_canonical({"offline": offline, "live": live})).hexdigest()
    payload = {
        "schema_version": 1, "policy_id": meta["policy_id"],
        "thresholds": thresholds, "evaluation": meta["evaluation"],
        "allowed_other_contact_bodies": meta["allowed_other_contact_bodies"],
        "mujoco_version": meta["mujoco_version"],
        "model_sha256": meta["model_sha256"], "scene_sha256": meta["scene_sha256"],
        "motion_policy_sha256": meta["motion_policy_sha256"],
        "source_evidence_sha256": source_hash,
        "collector_sha256": meta["collector_sha256"],
        "live_collector_sha256": meta["live_collector_sha256"],
        "analyzer_sha256": meta["analyzer_sha256"],
        "config_sha256": meta["config_sha256"],
    }
    canonical_policy_payload(payload)
    result = {
        "status": "DISABLED", "payload": payload,
        "policy_fingerprint": policy_fingerprint(payload),
        "source_evidence_sha256": source_hash,
        "counts": {name: {"offline": 20, "live": 5} for name in REGIMES},
        "negative_controls": controls, "confusion_matrix": confusion,
        "false_positive_rate": 0.0, "false_negative_rate": 0.0,
    }
    result["proposal_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        _fsync_directory(path.parent)


def seal_cohort(root: Path, cohort: dict[str, Any]) -> Path:
    """Create an immutable raw-cohort file and hash manifest with directory fsync."""

    source = cohort.get("source") if isinstance(cohort, dict) else None
    if source not in {"offline", "live"} or set(cohort) != {"source", "samples"}:
        raise ValueError("cohort source or schema is invalid")
    if not isinstance(cohort["samples"], list):
        raise ValueError("cohort samples must be a list")
    root = Path(root)
    root.mkdir(mode=0o750)
    _fsync_directory(root.parent)
    raw = _canonical(cohort) + b"\n"
    digest = hashlib.sha256(raw).hexdigest()
    _write_exclusive(root / "raw.json", raw)
    manifest = {
        "schema_version": 1,
        "source": source,
        "raw_filename": "raw.json",
        "raw_sha256": digest,
        "sample_count": len(cohort["samples"]),
    }
    manifest_path = root / "manifest.json"
    _write_exclusive(manifest_path, _canonical(manifest) + b"\n")
    return manifest_path


def _read_cohort(manifest_path: Path, expected_source: str) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or manifest_path.name != "manifest.json":
        raise ValueError("manifest identity is invalid")
    manifest = _exact(
        json.loads(manifest_path.read_bytes()),
        frozenset({"schema_version", "source", "raw_filename", "raw_sha256", "sample_count"}),
        "cohort manifest",
    )
    if manifest["schema_version"] != 1 or manifest["source"] != expected_source:
        raise ValueError("cohort manifest source mismatch")
    if manifest["raw_filename"] != "raw.json":
        raise ValueError("raw evidence path is not the sealed cohort file")
    raw_path = manifest_path.parent / "raw.json"
    if raw_path.is_symlink():
        raise ValueError("raw evidence symlink is forbidden")
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["raw_sha256"]:
        raise ValueError("raw evidence hash mismatch")
    cohort = _exact(json.loads(raw), frozenset({"source", "samples"}), "sealed cohort")
    if cohort["source"] != expected_source or len(cohort["samples"]) != manifest["sample_count"]:
        raise ValueError("raw evidence count or source mismatch")
    return cohort


def analyze_manifests(
    offline_manifest: Path, live_manifest: Path, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Read only the two explicitly supplied sealed cohorts; never scan directories."""

    return analyze_evidence(
        _read_cohort(offline_manifest, "offline"),
        _read_cohort(live_manifest, "live"),
        metadata,
    )


def verify_disabled_proposal(proposal: dict[str, Any]) -> None:
    """Validate the entire envelope, distinct from the canonical payload hash."""

    item = _exact(
        proposal,
        frozenset({"status", "payload", "policy_fingerprint", "source_evidence_sha256",
                   "counts", "negative_controls", "confusion_matrix",
                   "false_positive_rate", "false_negative_rate", "proposal_sha256"}),
        "disabled proposal",
    )
    if item["status"] != "DISABLED":
        raise ValueError("proposal is not disabled")
    canonical_policy_payload(item["payload"])
    if item["policy_fingerprint"] != policy_fingerprint(item["payload"]):
        raise ValueError("proposal payload fingerprint mismatch")
    if item["source_evidence_sha256"] != item["payload"]["source_evidence_sha256"]:
        raise ValueError("proposal evidence hash mismatch")
    if item["counts"] != {name: {"offline": 20, "live": 5} for name in REGIMES}:
        raise ValueError("proposal cohort counts are incomplete")
    for name in REGIMES:
        row = item["confusion_matrix"].get(name)
        if not isinstance(row, dict) or row.get(name) != 5 or sum(row.values()) != 5:
            raise ValueError("proposal live confusion matrix is incomplete")
    controls = item["negative_controls"]
    if not isinstance(controls, dict) or set(controls) != set(CONTROLS):
        raise ValueError("proposal negative controls are incomplete")
    for name in CONTROLS:
        values = controls[name]
        expected = name if name in {"left_only", "right_only"} else "no_contact"
        if not isinstance(values, list) or not values or any(value != expected for value in values):
            raise ValueError("proposal negative control failed")
    if item["false_positive_rate"] != 0 or item["false_negative_rate"] != 0:
        raise ValueError("proposal false classification rate is nonzero")
    expected_hash = hashlib.sha256(_canonical({key: value for key, value in item.items()
                                               if key != "proposal_sha256"})).hexdigest()
    if item["proposal_sha256"] != expected_hash:
        raise ValueError("proposal envelope hash mismatch")


def make_activation_receipt(
    proposal: dict[str, Any], approved_fingerprint: str, *, approved_by: str,
    approval_reference: str, evidence_root: Path, approved_at: str,
) -> dict[str, Any]:
    """Build a separate receipt only for the exact externally approved fingerprint."""

    verify_disabled_proposal(proposal)
    if approved_fingerprint != proposal["policy_fingerprint"]:
        raise ValueError("approved fingerprint does not match proposal payload")
    receipt = {
        "policy_fingerprint": approved_fingerprint,
        "source_evidence_sha256": proposal["source_evidence_sha256"],
        "approved_by": approved_by,
        "approval_reference": approval_reference,
        "approved_at": approved_at,
        "evidence_root": str(evidence_root),
    }
    verify_activation(proposal["payload"], receipt)
    return receipt
