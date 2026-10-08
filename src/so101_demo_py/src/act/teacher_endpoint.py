"""The Teacher endpoint rule ``teacher_endpoint_v2`` and the Teacher execution policy (pure, standalone).

Task success is answered by one start pose and one end pose read from the executed world against frozen
targets. This module owns the two closed policy documents and the pure judgement; it reads no runtime state.
Missing or untrustworthy observations give ``UNCONFIRMED`` and never ``PASS``; there is no best-of-history
selection, and yaw about the cup axis is not restricted.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import yaml

ENDPOINT_KIND = "ACT_TEACHER_ENDPOINT_POLICY"
EXECUTION_KIND = "ACT_TEACHER_EXECUTION_POLICY"
SCHEMA_VERSION = 1
RULE_VERSION = "teacher_endpoint_v2"
ENDPOINT_FIELDS = frozenset({"kind", "schema_version", "rule_version", "tolerances"})
TOLERANCE_UNITS = {
    "initial_position_m": "m",
    "initial_axis_rad": "rad",
    "final_xy_m": "m",
    "final_z_m": "m",
    "final_axis_rad": "rad",
    "settle_s": "s",
}
EXECUTION_FIELDS = frozenset({
    "kind", "schema_version", "state_max_age_s", "state_unavailable_stop_s", "execution_deadline_s",
    "gripper_close_target_rad", "carry_max_velocity_scaling", "carry_max_acceleration_scaling",
    "place_descend_offset_m",
})
EXECUTION_VALUES = ("state_max_age_s", "state_unavailable_stop_s", "execution_deadline_s")
QUATERNION_NORM_TOLERANCE = 1e-6
WORLD_FRAME = "world"


def _load_document(source, code: str):
    try:
        raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
        return yaml.safe_load(raw)
    except (OSError, yaml.YAMLError, ValueError, TypeError) as error:
        raise ValueError(f"{code}: cannot read the document: {error}") from error


def _real(value, key: str, code: str, *, allow_zero: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{code}: {key} is not a number")
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{code}: {key} is not finite and {'non-negative' if allow_zero else 'positive'}")
    return float(value)


def _sha256(document: dict) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_teacher_endpoint_policy(source) -> dict:
    """Load and validate the endpoint policy from YAML bytes or a path; the result carries its sha256."""

    code = "TEACHER_ENDPOINT_POLICY_INVALID"
    document = _load_document(source, code)
    if not isinstance(document, dict) or set(document) != ENDPOINT_FIELDS:
        raise ValueError(f"{code}: not the closed policy document")
    if (document["kind"] != ENDPOINT_KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != SCHEMA_VERSION or document["rule_version"] != RULE_VERSION):
        raise ValueError(f"{code}: unknown kind, schema version or rule version")
    tolerances = document["tolerances"]
    if not isinstance(tolerances, dict) or set(tolerances) != set(TOLERANCE_UNITS):
        raise ValueError(f"{code}: tolerances are not the closed six-field schema")
    clean = {}
    for key, unit in TOLERANCE_UNITS.items():
        value = _real(tolerances[key], key, code, allow_zero=key == "settle_s")
        if unit == "rad" and value > math.pi:
            raise ValueError(f"{code}: {key} exceeds pi radians")
        clean[key] = value
    policy = {"kind": ENDPOINT_KIND, "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
              "tolerances": clean}
    return {**policy, "policy_sha256": _sha256(policy)}


def load_teacher_execution_policy(source) -> dict:
    """Load and validate the Teacher execution policy from YAML bytes or a path, with its sha256."""

    code = "TEACHER_EXECUTION_POLICY_INVALID"
    document = _load_document(source, code)
    if not isinstance(document, dict) or set(document) != EXECUTION_FIELDS:
        raise ValueError(f"{code}: not the closed policy document")
    if (document["kind"] != EXECUTION_KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != SCHEMA_VERSION):
        raise ValueError(f"{code}: unknown kind or schema version")
    policy = {"kind": EXECUTION_KIND, "schema_version": SCHEMA_VERSION}
    for key in EXECUTION_VALUES:
        policy[key] = _real(document[key], key, code, allow_zero=False)
    target = document["gripper_close_target_rad"]
    if (isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target)
            or not -0.1 <= target <= 0.1):
        raise ValueError(f"{code}: gripper_close_target_rad is not a finite angle within 0.1 rad of zero")
    policy["gripper_close_target_rad"] = float(target)
    for key in ("carry_max_velocity_scaling", "carry_max_acceleration_scaling"):
        value = document[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or not 0 < value <= 1):
            raise ValueError(f"{code}: {key} is not a finite scaling in (0, 1]")
        policy[key] = float(value)
    offset = document["place_descend_offset_m"]
    if (isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset)
            or not -0.05 <= offset <= 0.05):
        raise ValueError(f"{code}: place_descend_offset_m is not a finite offset within 0.05 m")
    policy["place_descend_offset_m"] = float(offset)
    return {**policy, "policy_sha256": _sha256(policy)}


def _quaternion(value):
    """Return a validated (x, y, z, w) tuple or None when it is not finite and unit-norm."""

    if not isinstance(value, dict) or set(value) != {"x", "y", "z", "w"}:
        return None
    parts = []
    for key in ("x", "y", "z", "w"):
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            return None
        parts.append(float(item))
    if abs(math.sqrt(sum(p * p for p in parts)) - 1.0) > QUATERNION_NORM_TOLERANCE:
        return None
    return tuple(parts)


def _position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            return None
        out.append(float(item))
    return tuple(out)


def _body_axis(q) -> tuple:
    """Body +Z rotated into the world frame by the xyzw quaternion."""

    x, y, z, w = q
    return (2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y))


def _angle(a, b) -> float:
    dot = sum(i * j for i, j in zip(a, b))
    return math.acos(max(-1.0, min(1.0, dot)))


def _tilt(q) -> float:
    return _angle(_body_axis(q), (0.0, 0.0, 1.0))


def _target(value, label: str):
    if not isinstance(value, dict):
        raise ValueError(f"TEACHER_ENDPOINT_TARGET_INVALID: {label} is not a pose")
    position, quaternion = _position(value.get("position")), _quaternion(value.get("orientation"))
    if position is None or quaternion is None:
        raise ValueError(f"TEACHER_ENDPOINT_TARGET_INVALID: {label} position or quaternion is invalid")
    return position, quaternion


def validate_task_targets(policy: dict, start_target: dict, end_target: dict) -> None:
    """Refuse targets that cannot describe a real transfer that ends upright."""

    tol = policy["tolerances"]
    start_position, _ = _target(start_target, "start_target")
    end_position, end_quaternion = _target(end_target, "end_target")
    if _tilt(end_quaternion) > tol["final_axis_rad"]:
        raise ValueError("TEACHER_ENDPOINT_TARGET_NOT_UPRIGHT: end target axis tilt exceeds final_axis_rad")
    distance = math.hypot(end_position[0] - start_position[0], end_position[1] - start_position[1])
    if not distance > tol["initial_position_m"] + tol["final_xy_m"]:
        raise ValueError("TEACHER_ENDPOINT_TARGETS_COINCIDENT: start and end XY distance is not above "
                         "initial_position_m + final_xy_m")


def _observation(value):
    """Return (parsed or None, problem or None) for one observation."""

    if value is None:
        return None, "observation is missing"
    if not isinstance(value, dict):
        return None, "observation is not a mapping"
    position, quaternion = _position(value.get("position")), _quaternion(value.get("orientation"))
    time_s = value.get("simulation_time_s")
    if position is None:
        return None, "position is not finite"
    if quaternion is None:
        return None, "quaternion is not finite and unit-norm"
    if isinstance(time_s, bool) or not isinstance(time_s, (int, float)) or not math.isfinite(time_s):
        return None, "simulation time is not finite"
    if value.get("frame_id") != WORLD_FRAME:
        return None, "frame is not world"
    for key in ("object_id", "session_id"):
        if not isinstance(value.get(key), str) or not value[key]:
            return None, f"{key} is missing"
    if isinstance(value.get("reset_epoch"), bool) or not isinstance(value.get("reset_epoch"), int):
        return None, "reset_epoch is missing"
    return {"position": position, "quaternion": quaternion, "time": float(time_s)}, None


def evaluate_teacher_endpoint(policy: dict, *, start_target: dict, end_target: dict,
                              start_observation, end_observation) -> dict:
    """Judge one start and one end observation against the frozen targets.

    Targets are validated first and raise ``ValueError``. Observation problems give ``UNCONFIRMED``;
    otherwise any exceeded tolerance gives ``FAIL``.
    """

    validate_task_targets(policy, start_target, end_target)
    tol = policy["tolerances"]
    start_position, start_quaternion = _target(start_target, "start_target")
    end_position, _ = _target(end_target, "end_target")
    unconfirmed: list[str] = []
    start, problem = _observation(start_observation)
    if problem:
        unconfirmed.append(f"START_OBSERVATION_UNCONFIRMED: {problem}")
    end, problem = _observation(end_observation)
    if problem:
        unconfirmed.append(f"END_OBSERVATION_UNCONFIRMED: {problem}")
    if start and end:
        for key in ("object_id", "session_id", "reset_epoch"):
            if start_observation[key] != end_observation[key]:
                unconfirmed.append(f"OBSERVATION_IDENTITY_MISMATCH: {key} differs between start and end")
        if not end["time"] > start["time"]:
            unconfirmed.append("OBSERVATION_TIME_ORDER_INVALID: end simulation time is not after start")
    measured = {key: None for key in (
        "initial_position_error_m", "initial_axis_angle_rad", "final_xy_error_m", "final_z_error_m",
        "final_axis_tilt_rad")}
    failures: list[str] = []
    if start:
        measured["initial_position_error_m"] = math.dist(start["position"], start_position)
        measured["initial_axis_angle_rad"] = _angle(_body_axis(start["quaternion"]),
                                                    _body_axis(start_quaternion))
        if measured["initial_position_error_m"] > tol["initial_position_m"]:
            failures.append("INITIAL_POSITION_OUT_OF_TOLERANCE")
        if measured["initial_axis_angle_rad"] > tol["initial_axis_rad"]:
            failures.append("INITIAL_AXIS_OUT_OF_TOLERANCE")
    if end:
        measured["final_xy_error_m"] = math.hypot(end["position"][0] - end_position[0],
                                                  end["position"][1] - end_position[1])
        measured["final_z_error_m"] = abs(end["position"][2] - end_position[2])
        measured["final_axis_tilt_rad"] = _tilt(end["quaternion"])
        if measured["final_xy_error_m"] > tol["final_xy_m"]:
            failures.append("FINAL_XY_OUT_OF_TOLERANCE")
        if measured["final_z_error_m"] > tol["final_z_m"]:
            failures.append("FINAL_Z_OUT_OF_TOLERANCE")
        if measured["final_axis_tilt_rad"] > tol["final_axis_rad"]:
            failures.append("FINAL_AXIS_OUT_OF_TOLERANCE")
    if unconfirmed:
        result, reasons = "UNCONFIRMED", unconfirmed + failures
    elif failures:
        result, reasons = "FAIL", failures
    else:
        result, reasons = "PASS", []
    return {
        "rule_version": RULE_VERSION,
        "policy_sha256": policy["policy_sha256"],
        "result": result,
        "reasons": reasons,
        "measured": measured,
        "start_target": start_target,
        "end_target": end_target,
        "start_observation": start_observation,
        "end_observation": end_observation,
    }
